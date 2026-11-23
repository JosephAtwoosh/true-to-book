"""Runs INSIDE Blender (headless). Renders every frame of each clip as a small PNG.

    blender -b --factory-startup --python blender_extract.py -- jobs.json

jobs.json: {"width": 224, "jobs": [{"clip": "...mp4", "out": "dir"}, ...]}
Each finished job writes <out>/done.json; a failed one writes <out>/error.json.
One Blender process handles all clips, so its start-up cost is paid once.
"""
import json
import os
import sys
import traceback

import bpy

jobs_path = sys.argv[sys.argv.index("--") + 1]
with open(jobs_path, encoding="utf-8") as f:
    cfg = json.load(f)
width = int(cfg.get("width", 224))

sc = bpy.context.scene
# Keep pixel values as decoded: no filmic/AgX look applied to the video.
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.view_settings.exposure = 0
sc.view_settings.gamma = 1
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.render.resolution_percentage = 100
ed = sc.sequence_editor_create()
strips = ed.strips if hasattr(ed, "strips") else ed.sequences

for job in cfg["jobs"]:
    out = job["out"]
    os.makedirs(out, exist_ok=True)
    for name in ("done.json", "error.json"):
        p = os.path.join(out, name)
        if os.path.exists(p):
            os.remove(p)
    try:
        for s in list(strips):
            strips.remove(s)
        s = strips.new_movie("clip", job["clip"], 1, 1)
        n = s.frame_final_duration
        ew, eh = s.elements[0].orig_width, s.elements[0].orig_height
        sc.frame_start, sc.frame_end = 1, n
        # Render the canvas at the clip's own size, scaled down by percentage. A small
        # canvas would show a 1:1 centre crop of the strip instead of the whole picture.
        sc.render.resolution_x, sc.render.resolution_y = ew, eh
        sc.render.resolution_percentage = max(1, min(100, round(100 * width / ew)))
        sc.render.filepath = os.path.join(out, "f_")
        bpy.ops.render.render(animation=True)
        st = os.stat(job["clip"])
        with open(os.path.join(out, "done.json"), "w", encoding="utf-8") as f:
            json.dump({"v": cfg.get("v"), "frames": n, "src": [ew, eh], "width": width,
                       "clip_bytes": st.st_size, "clip_mtime": st.st_mtime}, f)
    except Exception:  # noqa: BLE001 - record and carry on with the next clip
        with open(os.path.join(out, "error.json"), "w", encoding="utf-8") as f:
            json.dump({"error": traceback.format_exc()}, f)
