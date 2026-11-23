"""Pass 1: does the file exist and match what the plan asked for? Hard failures only."""
from __future__ import annotations

import os

from .mp4info import probe
from .spec import Shot


def check_file(shot: Shot) -> dict:
    """Return {'probe': {...} | None, 'failures': [str, ...]}."""
    if not os.path.isfile(shot.clip):
        return {"probe": None, "failures": ["clip missing"]}
    try:
        p = probe(shot.clip)
    except Exception as e:  # noqa: BLE001 - ValueError, OSError, struct.error on broken files
        return {"probe": None, "failures": [f"unreadable clip: {e}"]}
    fails = []
    if not p["frames"]:
        fails.append("no frames")
    elif shot.frames and abs(p["frames"] - shot.frames) > 1:
        fails.append(f"{p['frames']} frames, plan asks for {shot.frames}")
    if shot.width and shot.height and (p["width"], p["height"]) != (shot.width, shot.height):
        fails.append(f"size {p['width']}x{p['height']}, plan asks for {shot.width}x{shot.height}")
    if shot.fps and p["fps"] and abs(p["fps"] - shot.fps) > 0.01:
        fails.append(f"{p['fps']} fps, plan asks for {shot.fps}")
    return {"probe": p, "failures": fails}
