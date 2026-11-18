"""Tests for mouse control and evaluation mode (no camera needed)."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from evaluation import EvaluationSession  # noqa: E402
from logic import HandReading, MouseGestureController  # noqa: E402

DT = 1 / 30
SCREEN = (1920, 1080)
FRAME = (640, 480)


def make_hand(x, y, index_out=True, pinch=False, right_pinch=False):
    """A simple fake hand. (x, y) is the index knuckle = the pointer."""
    lm = [(x, y + 0.2)] * 21
    lm[0] = (x, y + 0.25)    # wrist
    lm[9] = (x, y + 0.13)    # middle knuckle  -> hand size 0.12
    lm[5] = (x, y)           # index knuckle (pointer)
    lm[6] = (x, y - 0.02)    # index middle joint
    lm[8] = (x, y - 0.10) if index_out else (x, y + 0.05)  # index tip
    lm[12] = (x + 0.05, y - 0.08)                          # middle tip
    if pinch:
        lm[4] = (x + 0.005, y - 0.10)    # thumb touches index tip
    elif right_pinch:
        lm[4] = (x + 0.055, y - 0.08)    # thumb touches middle tip
    else:
        lm[4] = (x + 0.12, y + 0.05)
    return HandReading("Pointing_Up" if index_out else "Closed_Fist", 0.9, x, y, lm)


def instant(**kw):
    return MouseGestureController(smoothing_min=1.0, smoothing_max=1.0, deadzone=0, **kw)


def px(x, margin=0.2):
    return round((x - margin) / (1 - 2 * margin) * (SCREEN[0] - 1))


class TestMouse(unittest.TestCase):
    def test_corner_never_reaches_failsafe(self):
        m = instant()
        for x, y in [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)]:
            pos = m.update(0, make_hand(x, y), FRAME, SCREEN)["position"]
            self.assertTrue(1 <= pos[0] <= SCREEN[0] - 2)
            self.assertTrue(1 <= pos[1] <= SCREEN[1] - 2)

    def test_edges_reachable_inside_margin(self):
        m = instant()
        right = m.update(0, make_hand(0.8, 0.5), FRAME, SCREEN)["position"]
        self.assertEqual(right[0], SCREEN[0] - 2)
        centre = m.update(0, make_hand(0.5, 0.5), FRAME, SCREEN)["position"]
        self.assertAlmostEqual(centre[0], SCREEN[0] / 2, delta=2)

    def test_tiny_tremor_ignored(self):
        m = MouseGestureController()
        first = m.update(0, make_hand(0.5, 0.5), FRAME, SCREEN)["position"]
        later = m.update(DT, make_hand(0.5005, 0.5), FRAME, SCREEN)["position"]
        self.assertEqual(first, later)

    def test_fast_move_less_lag_than_slow(self):
        slow, fast = MouseGestureController(), MouseGestureController()
        for m in (slow, fast):
            m.update(0, make_hand(0.5, 0.5), FRAME, SCREEN)
        s = slow.update(DT, make_hand(0.51, 0.5), FRAME, SCREEN)["position"][0]
        f = fast.update(DT, make_hand(0.7, 0.5), FRAME, SCREEN)["position"][0]
        start = SCREEN[0] / 2
        self.assertGreater((f - start) / (px(0.7) - start), (s - start) / (px(0.51) - start))

    def aim_then(self, m, final_hand, drift_x=0.6):
        """Hold still at 0.5 for 0.5 s, drift to drift_x over 0.1 s, then final_hand."""
        t = 0.0
        for _ in range(15):
            m.update(t, make_hand(0.5, 0.5), FRAME, SCREEN)
            t += DT
        for i in range(3):
            m.update(t, make_hand(0.5 + (drift_x - 0.5) * (i + 1) / 3, 0.5), FRAME, SCREEN)
            t += DT
        return m.update(t, final_hand, FRAME, SCREEN)

    def test_fist_rewinds_to_aimed_point(self):
        r = self.aim_then(instant(), make_hand(0.6, 0.5, index_out=False))
        self.assertAlmostEqual(r["position"][0], px(0.5), delta=2)

    def test_left_click_lands_on_aimed_point(self):
        r = self.aim_then(instant(), make_hand(0.6, 0.5, pinch=True))
        self.assertTrue(r["clicked"])
        self.assertFalse(r["right_clicked"])
        self.assertAlmostEqual(r["position"][0], px(0.5), delta=2)

    def test_right_click(self):
        r = self.aim_then(instant(), make_hand(0.6, 0.5, right_pinch=True))
        self.assertTrue(r["right_clicked"])
        self.assertFalse(r["clicked"])

    def test_cursor_stays_frozen_while_pinching(self):
        m = instant()
        self.aim_then(m, make_hand(0.6, 0.5, pinch=True))
        r = m.update(1.0, make_hand(0.7, 0.5, pinch=True), FRAME, SCREEN)
        self.assertIsNone(r["position"])

    def test_one_pinch_one_click(self):
        m = instant()
        frames = ([make_hand(0.5, 0.5)] * 3 + [make_hand(0.5, 0.5, pinch=True)] * 15
                  + [make_hand(0.5, 0.5)] * 3)
        clicks = sum(bool(m.update(i * DT, h, FRAME, SCREEN)["clicked"])
                     for i, h in enumerate(frames))
        self.assertEqual(clicks, 1)

    def test_brief_hand_loss_keeps_cursor(self):
        m = MouseGestureController()
        m.update(0, make_hand(0.5, 0.5), FRAME, SCREEN)
        for i in range(3):
            m.update((i + 1) * DT, None, FRAME, SCREEN)
        self.assertIsNotNone(m.cursor)


class TestEvaluation(unittest.TestCase):
    def make(self, gestures):
        return EvaluationSession(repetitions=1, gestures=gestures, hold_frames=5,
                                 start_delay_seconds=1.0, rng=random.Random(0))

    def run_frames(self, ev, hands, t=0.0):
        results = []
        for h in hands:
            r = ev.update(t, h)
            if r:
                results.append(r)
            t += DT
        return results, t

    def test_countdown_then_correct_pose(self):
        ev = self.make(("Thumb_Up",))
        _, t = self.run_frames(ev, [None] * 40)  # countdown
        results, _ = self.run_frames(ev, [HandReading("Thumb_Up", 0.9, .5, .5)] * 10, t)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["correct"])

    def test_transition_shape_not_counted(self):
        ev = self.make(("Thumb_Up",))
        _, t = self.run_frames(ev, [None] * 40)
        frames = ([HandReading("Closed_Fist", 0.9, .5, .5)] * 2
                  + [HandReading("Thumb_Up", 0.9, .5, .5)] * 10)
        results, _ = self.run_frames(ev, frames, t)
        self.assertEqual(results[0]["detected"], "Thumb_Up")


if __name__ == "__main__":
    unittest.main()
