"""Read frame count, size, fps and codec from an MP4/MOV file in pure Python.

No ffmpeg needed, so the file checks also run on a render box straight after rendering.
Only the 'moov' box is read; the media data is skipped.
"""
from __future__ import annotations

import os
import struct
from collections import Counter

_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf"}


def _iter_boxes(buf: bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        size, typ = struct.unpack_from(">I4s", buf, i)
        hdr = 8
        if size == 1:
            if i + 16 > end:
                return
            size = struct.unpack_from(">Q", buf, i + 8)[0]
            hdr = 16
        elif size == 0:
            size = end - i
        if size < hdr:
            return
        yield typ, i + hdr, min(i + size, end)
        i += size


def _read_moov(path: str) -> bytes:
    with open(path, "rb") as f:
        total = os.fstat(f.fileno()).st_size
        pos = 0
        while pos + 8 <= total:
            f.seek(pos)
            head = f.read(16)
            size, typ = struct.unpack_from(">I4s", head, 0)
            hdr = 8
            if size == 1:
                size = struct.unpack_from(">Q", head, 8)[0]
                hdr = 16
            elif size == 0:
                size = total - pos
            if size < hdr:
                break
            if typ == b"moov":
                f.seek(pos)
                return f.read(size)
            pos += size
    raise ValueError("no 'moov' box (not an MP4/MOV file, or truncated)")


def _find(buf, start, end, typ):
    for t, s, e in _iter_boxes(buf, start, end):
        if t == typ:
            return s, e
    return None


def _track(buf, s, e) -> dict:
    info: dict = {}
    for typ, ps, pe in _iter_boxes(buf, s, e):
        if typ == b"tkhd":
            ver = buf[ps]
            off = ps + (88 if ver == 1 else 76)
            if off + 8 <= pe:
                w, h = struct.unpack_from(">II", buf, off)
                info["width"], info["height"] = round(w / 65536), round(h / 65536)
        elif typ == b"mdia":
            _mdia(buf, ps, pe, info)
    return info


def _mdia(buf, s, e, info):
    for typ, ps, pe in _iter_boxes(buf, s, e):
        if typ == b"mdhd":
            ver = buf[ps]
            if ver == 1:
                ts, dur = struct.unpack_from(">IQ", buf, ps + 20)
            else:
                ts, dur = struct.unpack_from(">II", buf, ps + 12)
            info["timescale"], info["duration_units"] = ts, dur
        elif typ == b"hdlr":
            info["handler"] = buf[ps + 8:ps + 12].decode("latin-1")
        elif typ == b"minf":
            stbl = _find(buf, ps, pe, b"stbl")
            if stbl:
                _stbl(buf, *stbl, info)


def _stbl(buf, s, e, info):
    for typ, ps, pe in _iter_boxes(buf, s, e):
        if typ == b"stsz":
            info["samples"] = struct.unpack_from(">I", buf, ps + 8)[0]
        elif typ == b"stts":
            n = struct.unpack_from(">I", buf, ps + 4)[0]
            deltas = Counter()
            for k in range(n):
                cnt, delta = struct.unpack_from(">II", buf, ps + 8 + 8 * k)
                deltas[delta] += cnt
            if deltas:
                info["sample_delta"] = deltas.most_common(1)[0][0]
        elif typ == b"stsd":
            if ps + 16 <= pe:
                info["codec"] = buf[ps + 12:ps + 16].decode("latin-1")


def probe(path: str) -> dict:
    """Return {'frames','fps','width','height','duration_s','codec','audio_tracks','bytes'}."""
    moov = _read_moov(path)
    tracks = []
    for typ, s, e in _iter_boxes(moov, 8, len(moov)):
        if typ == b"trak":
            tracks.append(_track(moov, s, e))
    video = [t for t in tracks if t.get("handler") == "vide"]
    if not video:
        raise ValueError("no video track")
    v = video[0]
    ts = v.get("timescale") or 0
    fps = ts / v["sample_delta"] if ts and v.get("sample_delta") else None
    return {
        "frames": v.get("samples"),
        "fps": round(fps, 3) if fps else None,
        "width": v.get("width"),
        "height": v.get("height"),
        "duration_s": round(v["duration_units"] / ts, 3) if ts else None,
        "codec": v.get("codec"),
        "audio_tracks": sum(t.get("handler") == "soun" for t in tracks),
        "bytes": os.path.getsize(path),
    }
