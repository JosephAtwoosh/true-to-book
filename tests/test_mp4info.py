"""MP4 header reading, on a synthetic file (box headers only, no real video)."""
import os
import struct
import tempfile
import unittest

from true_to_book.mp4info import probe


def box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), typ) + payload


def track(handler: bytes, frames: int, timescale: int, delta: int, w=0, h=0, codec=b"avc1"):
    tkhd = b"\0" * 4 + b"\0" * 20 + b"\0" * 16 + b"\0" * 36 + struct.pack(">II", w << 16, h << 16)
    mdhd = b"\0" * 4 + struct.pack(">IIII", 0, 0, timescale, frames * delta) + b"\0" * 4
    hdlr = b"\0" * 8 + handler + b"\0" * 12 + b"x\0"
    stsd = b"\0" * 4 + struct.pack(">I", 1) + box(codec, b"\0" * 8)
    stts = b"\0" * 4 + struct.pack(">III", 1, frames, delta)
    stsz = b"\0" * 4 + struct.pack(">II", 0, frames)
    stbl = box(b"stbl", box(b"stsd", stsd) + box(b"stts", stts) + box(b"stsz", stsz))
    mdia = box(b"mdia", box(b"mdhd", mdhd) + box(b"hdlr", hdlr) + box(b"minf", stbl))
    return box(b"trak", box(b"tkhd", tkhd) + mdia)


def mp4(moov_last=False) -> bytes:
    ftyp = box(b"ftyp", b"isom" + b"\0" * 4)
    moov = box(b"moov", box(b"mvhd", b"\0" * 100)
               + track(b"vide", 73, 12288, 1024, 896, 512)
               + track(b"soun", 100, 48000, 1024, codec=b"mp4a"))
    mdat = box(b"mdat", b"\0" * 1000)
    return ftyp + (mdat + moov if moov_last else moov + mdat)


class ProbeTest(unittest.TestCase):
    def _probe(self, data):
        fd, p = tempfile.mkstemp(suffix=".mp4")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            return probe(p)
        finally:
            os.remove(p)

    def test_reads_video_track(self):
        for last in (False, True):
            p = self._probe(mp4(moov_last=last))
            self.assertEqual(p["frames"], 73)
            self.assertEqual(p["fps"], 12.0)
            self.assertEqual((p["width"], p["height"]), (896, 512))
            self.assertAlmostEqual(p["duration_s"], 73 / 12, places=2)
            self.assertEqual(p["codec"], "avc1")
            self.assertEqual(p["audio_tracks"], 1)

    def test_rejects_non_mp4(self):
        with self.assertRaises(ValueError):
            self._probe(b"not a video at all")


if __name__ == "__main__":
    unittest.main()
