"""The input contract: one JSON file describing the shots to check.

{
  "version": 1,
  "shots": [
    {
      "id": "s01-01",
      "clip": "renders/s01-01/out/s01-01.mp4",     # required; relative to this file
      "frames": 73, "fps": 12, "width": 896, "height": 512,   # what the plan asked for
      "start_image": "renders/s01-01/inputs/start.png",       # the source picture, if any
      "kind": "dialogue",              # free text; "dialogue" expects visible acting
      "audio_drives_motion": true,
      "camera": "locked",              # "locked" | "moving" | null (unknown)
      "cast": ["hero"], "action": "...", "framing": "..."
    }
  ]
}

Everything except "id" and "clip" is optional; a check that needs a missing field is skipped.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields


@dataclass
class Shot:
    id: str
    clip: str
    frames: int | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    start_image: str | None = None
    kind: str | None = None
    audio_drives_motion: bool = False
    camera: str | None = None
    cast: list = field(default_factory=list)
    action: str = ""
    framing: str = ""


_PATH_FIELDS = ("clip", "start_image")


def load_spec(path: str) -> list[Shot]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("version", 1) != 1:
        raise ValueError(f"{path}: unsupported spec version {data.get('version')}")
    base = os.path.dirname(os.path.abspath(path))
    names = {f.name for f in fields(Shot)}
    shots = []
    for i, raw in enumerate(data.get("shots", [])):
        if "id" not in raw or "clip" not in raw:
            raise ValueError(f"{path}: shot #{i} needs 'id' and 'clip'")
        kw = {k: v for k, v in raw.items() if k in names}
        for k in _PATH_FIELDS:
            if kw.get(k):
                kw[k] = os.path.normpath(os.path.join(base, kw[k]))
        shots.append(Shot(**kw))
    ids = [s.id for s in shots]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate shot ids")
    return shots
