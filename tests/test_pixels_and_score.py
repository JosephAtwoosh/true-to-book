"""Pixel measurements and scoring on synthetic frames."""
import json
import os
import shutil
import tempfile
import unittest

from PIL import Image, ImageDraw

from true_to_book.pixels import measure
from true_to_book.score import score
from true_to_book.spec import Shot, load_spec

W, H = 224, 128


def _frame(x, objects=True, bright=0):
    im = Image.new("RGB", (W, H), (60 + bright, 90 + bright, 140 + bright))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 90, W, H], fill=(120 + bright, 90 + bright, 50 + bright))
    d.ellipse([x, 40, x + 40, 80], fill=(230, 120, 30))          # the "hero", moving
    if objects:
        d.ellipse([150, 50, 185, 85], fill=(200, 200, 210))      # a second character
    return im


def _write(folder, frames):
    os.makedirs(folder, exist_ok=True)
    paths = []
    for i, im in enumerate(frames):
        p = os.path.join(folder, f"f_{i + 1:04d}.png")
        im.save(p)
        paths.append(p)
    return paths


class PixelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def clip(self, name, frames):
        return measure(_write(os.path.join(self.tmp, name), frames))

    def test_normal_vs_frozen(self):
        normal = self.clip("normal", [_frame(10 + 3 * i) for i in range(30)])
        frozen = self.clip("frozen", [_frame(10) for _ in range(30)])
        self.assertGreater(normal["motion_median"], 0.5)   # above the "still" limit
        self.assertEqual(normal["longest_still_run"], 0)
        self.assertEqual(frozen["motion_median"], 0)
        self.assertEqual(frozen["longest_still_run"], 29)

    def test_vanishing_character_drifts_in_colour(self):
        stays = self.clip("stays", [_frame(10 + i) for i in range(30)])
        vanishes = self.clip("vanishes", [_frame(10 + i, objects=i < 15) for i in range(30)])
        self.assertGreater(vanishes["drift_colour_max"], stays["drift_colour_max"] + 1)

    def test_flash_is_a_jump(self):
        fr = [_frame(10 + i) for i in range(30)]
        fr[12] = _frame(22, bright=100)
        m = self.clip("flash", fr)
        self.assertGreater(m["luma_jump_max"], 40)
        self.assertIn(m["jump_frame"], (13, 14))

    def test_start_image_match(self):
        fr = [_frame(10 + i) for i in range(10)]
        good = os.path.join(self.tmp, "start_good.png")
        bad = os.path.join(self.tmp, "start_bad.png")
        fr[0].save(good)
        Image.new("RGB", (W, H), (255, 0, 255)).save(bad)
        paths = _write(os.path.join(self.tmp, "s"), fr)
        self.assertLess(measure(paths, good)["start_mismatch_pixels"], 1)
        self.assertGreater(measure(paths, bad)["start_mismatch_pixels"], 50)


def _px(motion=8.0, still=0, jump=1.5, luma=1.0, colour=5.0, drift=10.0, start=3.0):
    return {"motion_median": motion, "longest_still_run": still, "jump_ratio": jump,
            "luma_jump_max": luma, "drift_colour_max": colour, "drift_pixels_end": drift,
            "start_mismatch_pixels": start, "jump_frame": 5}


class ScoreTest(unittest.TestCase):
    def test_outliers_and_failures(self):
        shots = [Shot(id=f"s{i:02d}", clip="x.mp4", frames=49, camera="locked") for i in range(12)]
        ok_file = {"probe": {"frames": 49}, "failures": []}
        results = {s.id: {"file": ok_file, "pixels": _px(motion=8 + (i % 3) * 0.5,
                                                          colour=5 + (i % 4))}
                   for i, s in enumerate(shots)}
        results["s03"]["pixels"] = _px(motion=0.3, still=40)                    # frozen
        results["s07"]["pixels"] = _px(colour=40)                                # vanished
        results["s09"] = {"file": {"probe": {"frames": 1}, "failures": ["1 frames, plan asks for 49"]},
                          "pixels": None}
        rows = {r["id"]: r for r in score(shots, results)}
        self.assertEqual(rows["s09"]["verdict"], "fail")
        self.assertEqual(rows["s03"]["verdict"], "suspect")
        self.assertEqual(rows["s07"]["verdict"], "suspect")
        self.assertEqual(rows["s01"]["verdict"], "ok")
        ranked = [r["id"] for r in score(shots, results)]
        self.assertEqual(ranked[0], "s09")

    def test_locked_camera_rule_only_for_locked_shots(self):
        shots = [Shot(id=f"m{i}", clip="x.mp4", camera="moving") for i in range(8)]
        results = {s.id: {"file": {"probe": {}, "failures": []}, "pixels": _px()} for s in shots}
        results["m0"]["pixels"] = _px(drift=200)
        rows = {r["id"]: r for r in score(shots, results)}
        self.assertNotIn("drift_pixels_end", rows["m0"]["z"])


class SpecTest(unittest.TestCase):
    def test_relative_paths(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "shots.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "shots": [{"id": "a", "clip": "r/a.mp4",
                                                    "start_image": "r/a.png", "unknown": 1}]}, f)
            s = load_spec(p)[0]
            self.assertEqual(s.clip, os.path.normpath(os.path.join(d, "r/a.mp4")))
            self.assertTrue(s.start_image.endswith("a.png"))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
