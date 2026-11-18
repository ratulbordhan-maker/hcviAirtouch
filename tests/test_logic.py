"""Tests for the gesture logic (no camera needed). Run: python -m unittest discover tests"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from logic import GestureController, HandReading  # noqa: E402

FPS = 30
DT = 1 / FPS


def load_config(**overrides):
    path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.update(overrides)
    return cfg


def run(ctrl, frames, start=0.0):
    """frames: list of HandReading or None. Returns (events, end_time)."""
    events, t = [], start
    for hand in frames:
        e = ctrl.process(t, hand)
        if e:
            events.append(e)
        t += DT
    return events, t


def pose(name, n, x=0.5, y=0.5, score=0.9):
    return [HandReading(name, score, x, y) for _ in range(n)]


class TestPoses(unittest.TestCase):
    def test_short_pose_does_not_fire(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, pose("Thumb_Up", 5))
        self.assertEqual(events, [])

    def test_held_pose_fires_once(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, pose("Thumb_Up", 60))  # 2 seconds
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger"], "Thumb_Up")

    def test_flicker_does_not_double_fire(self):
        ctrl = GestureController(load_config())
        frames = pose("Thumb_Up", 15) + pose("None", 1, score=0.0) + pose("Thumb_Up", 30)
        events, _ = run(ctrl, frames)
        self.assertEqual(len(events), 1)

    def test_low_confidence_ignored(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, pose("Thumb_Up", 30, score=0.3))
        self.assertEqual(events, [])

    def test_moving_hand_does_not_fire_pose(self):
        ctrl = GestureController(load_config())
        # thumbs up while drifting up and down (like talking with your hands)
        frames = [HandReading("Thumb_Up", 0.9, 0.5, 0.3 + 0.2 * (i % 2)) for i in range(30)]
        events, _ = run(ctrl, frames)
        self.assertEqual(events, [])

    def test_repeat_gesture_keeps_firing(self):
        ctrl = GestureController(load_config(active_profile="media"))
        events, _ = run(ctrl, pose("Thumb_Up", 60))  # volume up held 2 s
        self.assertGreater(len(events), 2)


class TestSwipes(unittest.TestCase):
    def swipe_frames(self, x_from, x_to, n=8):
        step = (x_to - x_from) / (n - 1)
        return [HandReading("Open_Palm", 0.9, x_from + i * step, 0.5) for i in range(n)]

    def test_swipe_left_is_next_slide(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, self.swipe_frames(0.8, 0.3))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger"], "swipe_left")
        self.assertEqual(events[0]["action"]["key"], "right")

    def test_slow_movement_is_not_swipe(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, self.swipe_frames(0.8, 0.3, n=60))  # 2 seconds
        self.assertEqual([e for e in events if e["trigger"].startswith("swipe")], [])

    def test_pose_after_swipe_does_not_fire(self):
        ctrl = GestureController(load_config(active_profile="media"))
        frames = self.swipe_frames(0.8, 0.3) + pose("Open_Palm", 40, x=0.3)
        events, _ = run(ctrl, frames)
        self.assertEqual([e["trigger"] for e in events], ["swipe_left"])


class TestModes(unittest.TestCase):
    def test_pause_blocks_actions(self):
        ctrl = GestureController(load_config())
        frames = pose("ILoveYou", 20) + pose("None", 5, score=0) + pose("Thumb_Up", 30)
        events, _ = run(ctrl, frames)
        self.assertEqual(events[0], {"type": "toggle", "enabled": False})
        self.assertEqual(len(events), 1)

    def test_profile_cycle(self):
        ctrl = GestureController(load_config())
        events, _ = run(ctrl, pose("Victory", 20))
        self.assertEqual(events[0], {"type": "profile", "profile": "media"})


if __name__ == "__main__":
    unittest.main()
