"""Randomized gesture-recognition trials and CSV summaries."""

import csv
import math
import os
import random
from collections import Counter
from datetime import datetime

from logic import SwipeDetector

POSE_GESTURES = (
    "Closed_Fist",
    "Open_Palm",
    "Pointing_Up",
    "Thumb_Down",
    "Thumb_Up",
    "Victory",
    "ILoveYou",
)
SWIPE_GESTURES = ("swipe_left", "swipe_right")
EVALUATION_GESTURES = POSE_GESTURES + SWIPE_GESTURES


class EvaluationSession:
    def __init__(self, repetitions=20, timeout_seconds=10.0, minimum_score=0.6,
                 gestures=EVALUATION_GESTURES, rng=None, hold_frames=8,
                 swipe_settings=None, start_delay_seconds=3.0):
        if repetitions < 1:
            raise ValueError("repetitions must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.gestures = tuple(gestures)
        self.repetitions = repetitions
        self.timeout_seconds = timeout_seconds
        self.minimum_score = minimum_score
        self.targets = [gesture for gesture in self.gestures for _ in range(repetitions)]
        (rng or random).shuffle(self.targets)
        self.results = []
        self.index = 0
        self.started_at = None
        self.feedback_until = None
        self.last_message = ""
        self.waiting_for_release = False
        self.release_name = None
        self.release_frames = 0
        self.swipe = SwipeDetector(**(swipe_settings or {}))
        # A pose only counts once it has been seen for `hold_frames` frames in a
        # row (same rule as normal use). Otherwise the in-between shapes your
        # hand makes while forming a gesture get recorded as wrong answers.
        self.hold_frames = max(1, hold_frames)
        self.pose_name = None
        self.pose_count = 0
        self.start_delay = start_delay_seconds
        self.ready_at = None
        self.countdown_text = None

    @property
    def finished(self):
        return self.index >= len(self.targets)

    @property
    def current_target(self):
        return None if self.finished else self.targets[self.index]

    @property
    def prompt(self):
        if self.finished:
            return "Evaluation complete"
        if self.countdown_text:
            return self.countdown_text
        if self.feedback_until is not None:
            return self.last_message
        if self.waiting_for_release:
            return "Release your hand"
        return f"Do: {self.current_target}"

    def update(self, t, hand):
        if self.finished:
            return None

        # short "get ready" countdown before the first trial
        if self.ready_at is None:
            self.ready_at = t + self.start_delay
        if t < self.ready_at:
            self.countdown_text = f"Get ready... {math.ceil(self.ready_at - t)}"
            return None
        self.countdown_text = None

        if self.feedback_until is not None:
            if t < self.feedback_until:
                return None
            self.feedback_until = None

        if self.waiting_for_release:
            still_holding = (
                hand is not None
                and hand.name == self.release_name
                and hand.score >= self.minimum_score
            )
            self.release_frames = 0 if still_holding else self.release_frames + 1
            if self.release_frames < 3:
                return None
            self.waiting_for_release = False
            self.release_name = None
            self.release_frames = 0
            self.started_at = t
            self.swipe.reset()
            self._reset_pose()
            return None

        if self.started_at is None:
            self.started_at = t

        target = self.current_target
        detected = None
        if target in SWIPE_GESTURES:
            if hand is not None:
                detected = self.swipe.update(t, hand.x, hand.y)
        elif (hand is not None and hand.name in POSE_GESTURES
              and hand.score >= self.minimum_score):
            if hand.name == self.pose_name:
                self.pose_count += 1
            else:
                self.pose_name, self.pose_count = hand.name, 1
            if self.pose_count >= self.hold_frames:
                detected = hand.name
        else:
            self._reset_pose()

        if detected is not None:
            return self._finish(t, detected)
        if t - self.started_at >= self.timeout_seconds:
            return self._finish(t, None)
        return None

    def _finish(self, t, detected):
        target = self.current_target
        reaction = t - self.started_at
        result = {
            "trial": self.index + 1,
            "gesture": target,
            "detected": detected or "",
            "correct": detected == target,
            "reaction_seconds": reaction,
        }
        self.results.append(result)
        self.index += 1
        self.started_at = None
        self.swipe.reset()
        self._reset_pose()
        self.last_message = (
            f"Detected: {detected} ({reaction:.2f}s)"
            if detected is not None else "No detection (timed out)"
        )
        self.feedback_until = t + 0.65
        self.waiting_for_release = detected in POSE_GESTURES
        self.release_name = detected if self.waiting_for_release else None
        self.release_frames = 0
        return result

    def _reset_pose(self):
        self.pose_name = None
        self.pose_count = 0

    def summary(self):
        counts = Counter(row["gesture"] for row in self.results)
        summaries = []
        for gesture in self.gestures:
            rows = [row for row in self.results if row["gesture"] == gesture]
            correct_rows = [
                row for row in rows
                if row["correct"] and row["reaction_seconds"] is not None
            ]
            correct_count = sum(row["correct"] for row in rows)
            summaries.append({
                "gesture": gesture,
                "trials": counts[gesture],
                "correct_trials": correct_count,
                "accuracy_percent": (
                    100.0 * correct_count / len(rows) if rows else ""
                ),
                "average_reaction_seconds": (
                    sum(row["reaction_seconds"] for row in correct_rows)
                    / len(correct_rows)
                    if correct_rows else ""
                ),
            })
        return summaries

    def save(self, folder="logs"):
        os.makedirs(folder, exist_ok=True)
        filename = datetime.now().strftime("evaluation_%Y%m%d_%H%M%S.csv")
        path = os.path.join(folder, filename)
        fields = (
            "row_type",
            "trial",
            "gesture",
            "detected",
            "correct",
            "reaction_seconds",
            "trials",
            "correct_trials",
            "accuracy_percent",
            "average_reaction_seconds",
        )
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for result in self.results:
                writer.writerow({
                    "row_type": "trial",
                    "trial": result["trial"],
                    "gesture": result["gesture"],
                    "detected": result["detected"],
                    "correct": int(result["correct"]),
                    "reaction_seconds": f"{result['reaction_seconds']:.3f}",
                })
            for summary in self.summary():
                writer.writerow({"row_type": "summary", **summary})
        return path
