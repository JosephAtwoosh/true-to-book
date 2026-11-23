"""Command line.

    python -m true_to_book check shots.json --out qc/            # file + pixel checks
    python -m true_to_book check shots.json --out qc/ --files-only   # no Blender/ffmpeg needed
    python -m true_to_book probe clip.mp4
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from . import __version__
from .filecheck import check_file
from .frames import extract, frame_paths
from .mp4info import probe
from .pixels import measure
from .score import score
from .spec import load_spec


def _markdown(rows: list[dict], meta: dict) -> str:
    n = {v: sum(r["verdict"] == v for r in rows) for v in ("fail", "suspect", "ok")}
    out = [f"# true-to-book report", "",
           f"{meta['generated']} · {len(rows)} shots · **{n['fail']} fail**, "
           f"**{n['suspect']} suspect**, {n['ok']} ok · z ≥ {meta['z']}", "",
           "| # | shot | verdict | score | reasons |", "|---|---|---|---|---|"]
    for i, r in enumerate(x for x in rows if x["verdict"] != "ok"):
        out.append(f"| {i + 1} | {r['id']} | {r['verdict']} | {r['score']} | "
                   + "; ".join(r["reasons"]).replace("|", "/") + " |")
    return "\n".join(out) + "\n"


def cmd_check(a) -> int:
    shots = load_spec(a.spec)
    os.makedirs(a.out, exist_ok=True)
    frames_root = a.frames or os.path.join(a.out, "frames")
    results = {s.id: {"file": check_file(s), "pixels": None, "extract": None} for s in shots}
    print(f"file checks: {sum(bool(r['file']['failures']) for r in results.values())} "
          f"of {len(shots)} shots fail")

    if not a.files_only:
        readable = [s for s in shots if results[s.id]["file"]["probe"]]
        jobs = [(s.clip, os.path.join(frames_root, s.id)) for s in readable]
        status = extract(jobs, width=a.width, backend=a.backend)
        for s in readable:
            out = os.path.join(frames_root, s.id)
            results[s.id]["extract"] = status.get(out)
            paths = frame_paths(out)
            if paths:
                results[s.id]["pixels"] = measure(paths, s.start_image)
        print(f"pixel checks: {sum(r['pixels'] is not None for r in results.values())} shots measured")

    meta = {"tool": "true-to-book", "version": __version__,
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "spec": os.path.abspath(a.spec), "z": a.z,
            "passes": ["files"] + ([] if a.files_only else ["pixels"])}
    rows = score(shots, results, z=a.z)
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({**meta, "shots": rows}, f, indent=1, ensure_ascii=False)
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(_markdown(rows, meta))
    flagged = [r for r in rows if r["verdict"] != "ok"]
    print(f"{len(flagged)} shots to look at -> {os.path.join(a.out, 'report.md')}")
    for r in flagged[:a.top]:
        print(f"  {r['id']:<10} {r['verdict']:<8} {r['score']:>8}  {'; '.join(r['reasons'])}")
    return 1 if any(r["verdict"] == "fail" for r in rows) else 0


def cmd_probe(a) -> int:
    print(json.dumps(probe(a.clip), indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="true_to_book", description=__doc__.split("\n")[0])
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check the shots listed in a spec file")
    c.add_argument("spec")
    c.add_argument("--out", required=True, help="folder for report.json / report.md")
    c.add_argument("--frames", help="frame cache folder (default: OUT/frames)")
    c.add_argument("--width", type=int, default=224, help="frame width for analysis")
    c.add_argument("--backend", choices=["auto", "ffmpeg", "blender"], default="auto")
    c.add_argument("--files-only", action="store_true", help="skip frame extraction")
    c.add_argument("--z", type=float, default=3.0, help="how unusual a shot must be to flag")
    c.add_argument("--top", type=int, default=25, help="suspects to print")
    c.set_defaults(fn=cmd_check)
    pr = sub.add_parser("probe", help="print frame count, size and fps of a clip")
    pr.add_argument("clip")
    pr.set_defaults(fn=cmd_probe)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
