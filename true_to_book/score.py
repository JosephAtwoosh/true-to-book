"""Turn per-shot measurements into a ranked suspect list.

Each measurement is compared with the same measurement on the other shots of the run
(robust z-score: distance from the median in units of the median absolute deviation),
so "unusual for this film" is what gets flagged, not a fixed number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .spec import Shot


def _dialogue(s: Shot) -> bool:
    return bool(s.audio_drives_motion) or (s.kind or "").lower() == "dialogue"


@dataclass
class Rule:
    metric: str
    side: str                 # "high" or "low": which side is suspicious
    reason: str               # shown to the reviewer; {v} value, {typ} typical, {f} frame
    floor: float              # smallest spread used for the z-score
    applies: Callable[[Shot], bool] = lambda s: True
    weight: Callable[[Shot], float] = lambda s: 1.0


RULES = [
    Rule("motion_median", "low", "barely moves (motion {v}, typical {typ})", 0.5,
         weight=lambda s: 1.5 if _dialogue(s) else 1.0),
    Rule("longest_still_run", "high", "freezes for {v} frames", 2.0),
    Rule("jump_ratio", "high", "sudden jump at frame {f} ({v}x the usual change)", 0.5),
    Rule("luma_jump_max", "high", "brightness jump of {v} (flash or fade?)", 1.0),
    Rule("drift_colour_max", "high",
         "colours drift from the start frame ({v}, typical {typ}): something vanished, "
         "appeared or changed look?", 2.0),
    Rule("drift_pixels_end", "high",
         "ends far from the start frame ({v}, typical {typ}) although the camera is locked", 2.0,
         applies=lambda s: (s.camera or "").lower() == "locked"),
    Rule("start_mismatch_pixels", "high",
         "first frame does not match the start picture ({v}, typical {typ})", 2.0),
]


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def score(shots: list[Shot], results: dict[str, dict], z: float = 3.0) -> list[dict]:
    """results[id] = {'file': {...}, 'pixels': {...} | None, 'extract': str}"""
    by_id = {s.id: s for s in shots}
    stats = {}
    for r in RULES:
        vals = [results[s.id]["pixels"][r.metric] for s in shots
                if r.applies(s) and results[s.id].get("pixels")
                and r.metric in results[s.id]["pixels"]]
        if len(vals) >= 5:
            med = _median(vals)
            mad = _median([abs(v - med) for v in vals])
            stats[r.metric] = (med, max(1.4826 * mad, r.floor))

    rows = []
    for sid, res in results.items():
        s = by_id[sid]
        fails = list(res["file"]["failures"])
        if res.get("extract") not in (None, "ok", "cached"):
            fails.append(f"frames could not be extracted: {res['extract']}")
        px = res.get("pixels") or {}
        reasons, zs, total = [], {}, 0.0
        for r in RULES:
            if r.metric not in px or r.metric not in stats or not r.applies(s):
                continue
            med, spread = stats[r.metric]
            zz = (px[r.metric] - med) / spread
            if r.side == "low":
                zz = -zz
            zs[r.metric] = round(zz, 2)
            if zz >= z:
                total += r.weight(s) * (zz - z + 1)
                reasons.append(r.reason.format(v=px[r.metric], typ=round(med, 2),
                                               f=px.get("jump_frame")))
        verdict = "fail" if fails else ("suspect" if reasons else "ok")
        rows.append({
            "id": sid,
            "verdict": verdict,
            "score": round(1000 + total if fails else total, 2),
            "reasons": fails + reasons,
            "clip": s.clip,
            "kind": s.kind,
            "camera": s.camera,
            "file": res["file"]["probe"],
            "pixels": px or None,
            "z": zs,
        })
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return rows
