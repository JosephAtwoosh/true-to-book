"""Turn clips into small PNG frames (f_0001.png, ...) with ffmpeg or Blender.

Frames are cached: a clip whose folder has a done.json matching the clip's size and
modification time is not extracted again.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Bump when extraction output changes, so cached frames are made again.
# 2: Blender renders the whole picture scaled down (1 rendered a centre crop).
EXTRACT_VERSION = 2


def find_ffmpeg() -> str | None:
    p = os.environ.get("TTB_FFMPEG") or shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg  # optional: pip install imageio-ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def find_blender() -> str | None:
    p = os.environ.get("TTB_BLENDER") or shutil.which("blender")
    if p:
        return p
    if sys.platform == "win32":
        la = os.environ.get("LOCALAPPDATA", "")
        # Microsoft Store build: only this alias can be started from outside.
        alias = os.path.join(la, "Microsoft", "WindowsApps", "blender-launcher.exe")
        if os.path.exists(alias):
            return alias
        hits = sorted(glob.glob(r"C:\Program Files\Blender Foundation\*\blender.exe"))
        if hits:
            return hits[-1]
    elif sys.platform == "darwin":
        p = "/Applications/Blender.app/Contents/MacOS/Blender"
        if os.path.exists(p):
            return p
    return None


def _cached(clip: str, out: str, width: int) -> bool:
    try:
        with open(os.path.join(out, "done.json"), encoding="utf-8") as f:
            d = json.load(f)
        st = os.stat(clip)
        return (d.get("v") == EXTRACT_VERSION and d.get("width") == width
                and d.get("clip_bytes") == st.st_size
                and abs(d.get("clip_mtime", 0) - st.st_mtime) < 1)
    except (OSError, ValueError):
        return False


def _reset(out: str):
    os.makedirs(out, exist_ok=True)
    for p in glob.glob(os.path.join(out, "f_*.png")) + glob.glob(os.path.join(out, "*.json")):
        os.remove(p)


def _ffmpeg(ffmpeg: str, clip: str, out: str, width: int):
    _reset(out)
    r = subprocess.run([ffmpeg, "-v", "error", "-i", clip, "-vf", f"scale={width}:-2",
                        "-start_number", "1", os.path.join(out, "f_%04d.png")],
                       capture_output=True, text=True)
    if r.returncode:
        with open(os.path.join(out, "error.json"), "w", encoding="utf-8") as f:
            json.dump({"error": r.stderr[-2000:]}, f)
        return
    st = os.stat(clip)
    n = len(glob.glob(os.path.join(out, "f_*.png")))
    with open(os.path.join(out, "done.json"), "w", encoding="utf-8") as f:
        json.dump({"v": EXTRACT_VERSION, "frames": n, "width": width, "clip_bytes": st.st_size,
                   "clip_mtime": st.st_mtime}, f)


def _blender(blender: str, jobs: list[tuple[str, str]], width: int, log=print):
    for _, out in jobs:
        _reset(out)
    fd, jobs_path = tempfile.mkstemp(suffix=".json", prefix="ttb-jobs-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"v": EXTRACT_VERSION, "width": width, "jobs": [{"clip": c, "out": o} for c, o in jobs]}, f)
    try:
        # The Store launcher prints nothing; results come back through done.json files.
        subprocess.run([blender, "-b", "--factory-startup", "--python",
                        os.path.join(HERE, "blender_extract.py"), "--", jobs_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.remove(jobs_path)


def extract(jobs: list[tuple[str, str]], width: int = 224, backend: str = "auto",
            batch: int = 40, log=print) -> dict[str, str]:
    """jobs: [(clip, out_dir)]. Returns {out_dir: 'ok' | 'cached' | error text}."""
    todo = [(c, o) for c, o in jobs if not _cached(c, o, width)]
    status = {o: "cached" for c, o in jobs if (c, o) not in todo}
    if todo:
        ffmpeg = find_ffmpeg() if backend in ("auto", "ffmpeg") else None
        blender = find_blender() if backend in ("auto", "blender") and not ffmpeg else None
        if ffmpeg:
            log(f"extracting {len(todo)} clips with ffmpeg ({ffmpeg})")
            for c, o in todo:
                _ffmpeg(ffmpeg, c, o, width)
        elif blender:
            log(f"extracting {len(todo)} clips with Blender ({blender})")
            for i in range(0, len(todo), batch):
                _blender(blender, todo[i:i + batch], width)
                log(f"  {min(i + batch, len(todo))}/{len(todo)}")
        else:
            raise RuntimeError("neither ffmpeg nor Blender found; set TTB_FFMPEG or TTB_BLENDER")
    for c, o in todo:
        if os.path.exists(os.path.join(o, "done.json")):
            status[o] = "ok"
        else:
            try:
                with open(os.path.join(o, "error.json"), encoding="utf-8") as f:
                    status[o] = json.load(f)["error"].strip().splitlines()[-1]
            except (OSError, ValueError, KeyError, IndexError):
                status[o] = "extraction failed (no result written)"
    return status


def frame_paths(out: str) -> list[str]:
    return sorted(glob.glob(os.path.join(out, "f_*.png")))
