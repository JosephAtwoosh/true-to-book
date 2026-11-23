# true-to-book

Checks that AI-rendered video shots stay **true to their book source**, and ranks the shots
most likely to need a reshoot, so a person reviews a short list instead of every clip.

Built for turning illustrated books into films with image/audio-to-video models (LTX-2.5,
Wan 2.2, ...) and as little human intervention as possible. The renders are usually fine,
but some inevitably drift: a character melts into another, a dialogue shot barely moves, a
clip comes out one frame long. This tool finds those.

## How it works

You describe the shots in a small JSON file (the plan: expected frames, size, the source
picture, whether it's a dialogue shot, whether the camera is locked). The tool checks each
rendered clip against it, in passes from cheapest to most expensive:

| Pass | What it finds | Needs |
|---|---|---|
| **files** | missing or unreadable clip, wrong frame count, size or fps | Python only (pure-Python MP4 reader) |
| **pixels** | barely moving or frozen shots, glitch frames, flashes, colour drift (something vanished or changed look), picture wandering off although the camera is locked, first frame not matching the source picture | Pillow + ffmpeg **or** Blender to extract frames |
| lip-sync | mouth not following the voice in dialogue shots | *planned* |
| vision | a vision model checks cast, looks, anatomy, style and action against the plan | *planned* (paid API) |

Shots are scored against **the other shots of the same film** (robust z-scores), so
"unusual for this film" is what gets flagged, not a fixed number. Output: `report.json`
(everything, for a review UI) and `report.md` (the ranked suspect list).

## Install

```sh
pip install -e .                 # Pillow is the only dependency
pip install -e .[ffmpeg]         # optional: bundled ffmpeg for frame extraction
```

Frame extraction uses ffmpeg if found (`TTB_FFMPEG`, `PATH`, or `imageio-ffmpeg`), otherwise
Blender in background mode (`TTB_BLENDER`, `PATH`, the Microsoft Store alias
`blender-launcher.exe`, or `C:\Program Files\Blender Foundation\*`). One Blender process
handles a batch of clips; extracted frames are cached and reused while the clip is unchanged.

## Use

```sh
python -m true_to_book check shots.json --out qc/                # files + pixels
python -m true_to_book check shots.json --out qc/ --files-only   # seconds, no ffmpeg/Blender
python -m true_to_book probe clip.mp4
```

`--files-only` is meant to run on the render machine right after each clip is made, so a
broken render is redone before the rented GPU is released. The exit code is 1 when any
shot fails a file check.

## The spec file

```json
{
  "version": 1,
  "shots": [
    {
      "id": "s01-01",
      "clip": "renders/s01-01.mp4",
      "frames": 73, "fps": 12, "width": 896, "height": 512,
      "start_image": "pictures/s01-01-start.png",
      "kind": "dialogue",
      "audio_drives_motion": true,
      "camera": "locked",
      "cast": ["hero"], "action": "walks to the gate and waves", "framing": "medium-wide, locked camera"
    }
  ]
}
```

Only `id` and `clip` are required; paths are relative to the spec file. A check that needs
a missing field is skipped. `camera` is `"locked"`, `"moving"` or `null`.

## Tests

```sh
python -m unittest discover -s tests -t .
```

Tests use synthetic data only (generated frames and hand-built MP4 headers). No book
material, renders or voices belong in this repository.
