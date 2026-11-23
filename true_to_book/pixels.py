"""Pass 2: pixel measurements on a clip's frames (Pillow only).

All differences are mean absolute differences on 0-255 channel values.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageStat

STILL = 0.5          # frame-to-frame change below this counts as "not moving"
HIST_EVERY = 4       # colour histograms on every Nth frame (and the last)


def _mad(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def _hist(im: Image.Image) -> list[float]:
    """Joint 8x8x8 colour histogram, normalised."""
    small = im.resize((64, max(1, round(64 * im.height / im.width))))
    q = small.point(lambda v: v >> 5)
    h = [0] * 512
    for x, y, z in q.getdata():
        h[x * 64 + y * 8 + z] += 1
    n = float(q.width * q.height)
    return [v / n for v in h]


def _hdist(a: list[float], b: list[float]) -> float:
    """0 = same colours, 100 = no colours in common."""
    return 50.0 * sum(abs(x - y) for x, y in zip(a, b))


def measure(paths: list[str], start_image: str | None = None) -> dict:
    fs = [Image.open(p).convert("RGB") for p in paths]
    if not fs:
        return {"frames": 0}
    step = [_mad(fs[i - 1], fs[i]) for i in range(1, len(fs))] or [0.0]
    drift = [_mad(fs[0], f) for f in fs]
    luma = [ImageStat.Stat(f.convert("L")).mean[0] for f in fs]
    hi = sorted(set(list(range(0, len(fs), HIST_EVERY)) + [len(fs) - 1]))
    h0 = _hist(fs[0])
    cdrift = [_hdist(h0, _hist(fs[i])) for i in hi]

    srt = sorted(step)
    med = srt[len(srt) // 2]
    jump_i = max(range(len(step)), key=step.__getitem__)
    run = best = 0
    for s in step:
        run = run + 1 if s < STILL else 0
        best = max(best, run)
    lstep = [abs(luma[i] - luma[i - 1]) for i in range(1, len(luma))] or [0.0]

    m = {
        "frames": len(fs),
        "motion_median": round(med, 2),
        "motion_p90": round(srt[int(0.9 * (len(srt) - 1))], 2),
        "jump_ratio": round(step[jump_i] / max(med, 0.5), 2),
        "jump_frame": jump_i + 2,
        "longest_still_run": best,
        "drift_pixels_end": round(drift[-1], 2),
        "drift_pixels_max": round(max(drift), 2),
        "drift_colour_end": round(cdrift[-1], 2),
        "drift_colour_max": round(max(cdrift), 2),
        "luma_min": round(min(luma), 1),
        "luma_max": round(max(luma), 1),
        "luma_jump_max": round(max(lstep), 2),
    }
    if start_image:
        try:
            ref = Image.open(start_image).convert("RGB").resize(fs[0].size, Image.LANCZOS)
            m["start_mismatch_pixels"] = round(_mad(ref, fs[0]), 2)
            m["start_mismatch_colour"] = round(_hdist(_hist(ref), h0), 2)
        except OSError:
            m["start_image_unreadable"] = True
    return m
