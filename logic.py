"""
Gesture logic: turns raw per-frame hand readings into clean, deliberate events.

This file has NO dependency on the camera or MediaPipe, so it can be unit-tested
on its own (see tests/test_logic.py). This is where most of the "HCI design"
lives: how long a pose must be held, how still the hand must be, how fast a
swipe must be, and how we avoid accidental triggers.
"""

from collections import deque
from dataclasses import dataclass
import math


@dataclass
class HandReading:
    """One frame's worth of information about the detected hand."""
    name: str          # MediaPipe gesture label, e.g. "Thumb_Up", "Open_Palm", "None"
    score: float       # confidence of that label (0..1)
    x: float           # palm centre, normalised 0..1 (0 = left edge of mirrored image)
    y: float           # palm centre, normalised 0..1 (0 = top)
    landmarks: list = None  # 21 (x, y) points, only used for drawing


class SwipeDetector:
    """Detects a fast horizontal hand movement.

    We keep the palm position for the last `window_seconds`. If the hand moved
    at least `min_distance` (fraction of the frame width) sideways in that time,
    while not moving too much vertically, it counts as a swipe.
    """

    def __init__(self, window_seconds=0.4, min_distance=0.25, max_vertical=0.15):
        self.window = window_seconds
        self.min_distance = min_distance
        self.max_vertical = max_vertical
        self.history = deque()  # items: (t, x, y)

    def reset(self):
        self.history.clear()

    def update(self, t, x, y):
        self.history.append((t, x, y))
        while self.history and t - self.history[0][0] > self.window:
            self.history.popleft()
        if len(self.history) < 3:
            return None

        _, x0, y0 = self.history[0]
        dx, dy = x - x0, y - y0
        if abs(dx) >= self.min_distance and abs(dy) <= self.max_vertical:
            self.history.clear()  # don't detect the same swipe twice
            return "swipe_right" if dx > 0 else "swipe_left"
        return None


class StaticGestureStabilizer:
    """Decides when a hand *pose* (thumbs up, fist...) is deliberate.

    Rules (each one exists to stop accidental triggers):
      1. Confidence must be at least `min_score`.
      2. The pose must be held for `hold_frames` frames in a row.
      3. The hand must stay roughly still while holding (moving = probably a swipe
         or just talking with your hands).
      4. Short flickers (the detector misreading 1-2 frames) are ignored thanks to
         `grace_frames`, so one long hold doesn't fire twice.

    update() returns None, "first" (fire now) or "repeat" (fire again because the
    pose is still being held, used for things like volume). The caller must call
    confirm() if it actually acted on the result.
    """

    def __init__(self, hold_frames=8, min_score=0.6, still_threshold=0.06,
                 repeat_interval=0.4, grace_frames=3):
        self.hold_frames = hold_frames
        self.min_score = min_score
        self.still = still_threshold
        self.repeat_interval = repeat_interval
        self.grace_frames = grace_frames
        self.reset()

    def reset(self):
        self.current = None
        self.count = 0
        self.anchor = (0.0, 0.0)
        self.fired = False
        self.last_fire = 0.0
        self.mismatch = 0

    def progress(self):
        """0..1, how close the current pose is to firing (for the on-screen bar)."""
        if self.current is None or self.fired:
            return 0.0
        return min(1.0, self.count / self.hold_frames)

    def consume(self):
        """Mark the current pose as already used (e.g. it was part of a swipe)."""
        self.fired = True

    def confirm(self, t):
        self.fired = True
        self.last_fire = t

    def update(self, t, name, score, x, y):
        if name in (None, "None") or score < self.min_score:
            name = None

        if name != self.current:
            self.mismatch += 1
            if self.current is not None and self.mismatch < self.grace_frames:
                return None  # probably a flicker, keep the current pose
            self.current = name
            self.count = 1 if name else 0
            self.anchor = (x, y)
            self.fired = False
            self.mismatch = 0
            return None

        self.mismatch = 0
        if name is None:
            return None

        if abs(x - self.anchor[0]) > self.still or abs(y - self.anchor[1]) > self.still:
            self.count = 1           # hand moved: restart the hold timer
            self.anchor = (x, y)
            return None

        self.count += 1
        if self.count < self.hold_frames:
            return None
        if not self.fired:
            return "first"
        if t - self.last_fire >= self.repeat_interval:
            return "repeat"
        return None


class GestureController:
    """Combines swipes + poses with the user's config and returns events.

    Events are dicts like:
      {"type": "action", "trigger": "Thumb_Up", "action": {...}}
      {"type": "toggle", "enabled": False}
      {"type": "profile", "profile": "media"}
    """

    def __init__(self, config):
        self.cfg = config
        self.profiles = list(config["profiles"].keys())
        self.profile = config.get("active_profile", self.profiles[0])
        if self.profile not in self.profiles:
            raise ValueError(f"Unknown profile '{self.profile}'. Options: {self.profiles}")
        self.enabled = True
        self.cooldown = config.get("cooldown_seconds", 0.7)
        self.toggle_gesture = config.get("toggle_gesture")
        self.profile_gesture = config.get("profile_gesture")
        self.last_action_time = -1e9
        self.missing = 0
        self.lost_hand_frames = config.get("lost_hand_frames", 5)

        self.swipe = SwipeDetector(**config.get("swipe", {}))
        s = config.get("static", {})
        self.static = StaticGestureStabilizer(
            hold_frames=s.get("hold_frames", 8),
            min_score=s.get("min_score", 0.6),
            still_threshold=s.get("still_threshold", 0.06),
            repeat_interval=s.get("repeat_interval", 0.4),
            grace_frames=s.get("grace_frames", 3),
        )

    def mapping(self):
        return self.cfg["profiles"][self.profile]

    def set_profile(self, name):
        if name in self.profiles:
            self.profile = name

    def process(self, t, hand):
        # --- no hand in view -------------------------------------------------
        if hand is None:
            self.missing += 1
            self.static.update(t, None, 0.0, 0.0, 0.0)
            if self.missing > self.lost_hand_frames:
                self.swipe.reset()
            return None
        self.missing = 0

        in_cooldown = (t - self.last_action_time) < self.cooldown

        # --- swipes (movement) -----------------------------------------------
        swipe = self.swipe.update(t, hand.x, hand.y)
        if swipe and self.enabled and not in_cooldown and swipe in self.mapping():
            self.static.consume()  # the pose used while swiping must not fire afterwards
            self.last_action_time = t
            return {"type": "action", "trigger": swipe, "action": self.mapping()[swipe]}

        # --- poses (static) --------------------------------------------------
        kind = self.static.update(t, hand.name, hand.score, hand.x, hand.y)
        if kind is None:
            return None
        name = self.static.current
        action = self.mapping().get(name)

        if action and action.get("type") == "control":
            control = action.get("action")
            if control == "disabled":
                self.static.confirm(t)
                return None
            if control == "toggle" or (control == "profile" and self.enabled):
                if kind != "first" or in_cooldown:
                    return None
                self.static.confirm(t)
                self.last_action_time = t
                if control == "toggle":
                    self.enabled = not self.enabled
                    return {"type": "toggle", "enabled": self.enabled}
                i = self.profiles.index(self.profile)
                self.profile = self.profiles[(i + 1) % len(self.profiles)]
                return {"type": "profile", "profile": self.profile}
            if control != "profile":
                raise ValueError(f"Unknown control action: {control}")
            return None

        if name == self.toggle_gesture and action is None:
            if kind != "first" or in_cooldown:
                return None
            self.static.confirm(t)
            self.last_action_time = t
            self.enabled = not self.enabled
            return {"type": "toggle", "enabled": self.enabled}

        if not self.enabled:
            return None

        if name == self.profile_gesture and action is None:
            if kind != "first" or in_cooldown:
                return None
            self.static.confirm(t)
            self.last_action_time = t
            i = self.profiles.index(self.profile)
            self.profile = self.profiles[(i + 1) % len(self.profiles)]
            return {"type": "profile", "profile": self.profile}

        if action is None:
            return None
        if kind == "repeat" and not action.get("repeat", False):
            return None
        if kind == "first" and in_cooldown:
            return None  # wait; we'll get "first" again next frame

        self.static.confirm(t)
        if kind == "first":
            self.last_action_time = t
        return {"type": "action", "trigger": name, "action": action}


class MouseGestureController:
    """Moves the cursor with the index finger; pinch thumb + index = left click,
    pinch thumb + middle = right click; fold the index finger (fist) = stop.

    Design choices, each fixing a common problem with webcam mice:
      * Pointer = index knuckle (default) instead of fingertip: the knuckle barely
        moves when you fold a finger or pinch, so the cursor doesn't drift.
      * Rewind: when a click or stop starts, the cursor jumps back to where it was
        `rewind_seconds` ago, i.e. before your fingers started moving.
      * Adaptive smoothing: small moves smoothed a lot (steady), fast moves
        only a little (no lag). A dead zone ignores tiny tremors.
      * Finger geometry instead of the "Pointing_Up" label, so the cursor doesn't
        stop when the classifier flickers.
      * Pinch measured relative to hand size (works near and far) with two
        thresholds (hysteresis) so one pinch = one click.
      * The cursor stays frozen while pinching or stopped.
      * A few frames without a hand don't reset anything (no cursor jumps).
    """

    POINTER_LANDMARK = {"knuckle": 5, "fingertip": 8}

    def __init__(self, smoothing_min=0.15, smoothing_max=0.7, speed_for_max=0.03,
                 deadzone=0.002, pinch_on=0.35, pinch_off=0.5,
                 click_cooldown_seconds=0.4, edge_margin=0.2, lost_hand_frames=5,
                 pointer="knuckle", rewind_seconds=0.2, **_ignored):
        if not 0 < smoothing_min <= smoothing_max <= 1:
            raise ValueError("need 0 < smoothing_min <= smoothing_max <= 1")
        if not 0 <= edge_margin < 0.5:
            raise ValueError("edge_margin must be between 0 and 0.5")
        if pinch_off < pinch_on:
            raise ValueError("pinch_off must be >= pinch_on")
        if pointer not in self.POINTER_LANDMARK:
            raise ValueError(f"pointer must be one of {list(self.POINTER_LANDMARK)}")
        self.smoothing_min = smoothing_min
        self.smoothing_max = smoothing_max
        self.speed_for_max = speed_for_max
        self.deadzone = deadzone
        self.pinch_on = pinch_on
        self.pinch_off = pinch_off
        self.click_cooldown = click_cooldown_seconds
        # Only the middle of the camera image is mapped to the whole screen,
        # because MediaPipe loses the hand near the image edges.
        self.edge_margin = edge_margin
        self.lost_hand_frames = lost_hand_frames
        self.pointer_id = self.POINTER_LANDMARK[pointer]
        self.rewind = rewind_seconds
        self.reset()

    def reset(self):
        self.cursor = None
        self.pinching = False        # thumb + index
        self.right_pinching = False  # thumb + middle
        self.moving = False
        self.history = deque()       # (t, cursor) for the last ~second
        self.last_click = -math.inf
        self.missing = 0

    @staticmethod
    def _dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _pinch(self, ratio, was_pinching):
        return ratio < (self.pinch_off if was_pinching else self.pinch_on)

    def _rewound_cursor(self, t):
        """Cursor position from `rewind` seconds ago (before the fingers moved)."""
        target = t - self.rewind
        best = None
        for when, pos in self.history:
            if when <= target:
                best = pos
            else:
                break
        if best is None and self.history:
            best = self.history[0][1]
        return best or self.cursor

    def _to_pixels(self, cursor, screen_size):
        w, h = screen_size
        # Stay 1 px away from the edges: PyAutoGUI's fail-safe stops the app
        # when the cursor reaches a screen corner.
        x = min(w - 2, max(1, round(cursor[0] * (w - 1))))
        y = min(h - 2, max(1, round(cursor[1] * (h - 1))))
        return x, y

    def update(self, t, hand, frame_size, screen_size, enabled=True):
        """Returns None or {"position": (x, y) | None, "clicked": bool,
        "right_clicked": bool}."""
        if hand is None or not hand.landmarks or len(hand.landmarks) < 21:
            self.missing += 1
            if self.missing > self.lost_hand_frames:
                self.cursor = None
                self.pinching = self.right_pinching = self.moving = False
                self.history.clear()
            return None
        self.missing = 0
        if min(screen_size) <= 0:
            raise ValueError("screen dimensions must be positive")
        lm = hand.landmarks

        # --- pinches ----------------------------------------------------------
        hand_size = self._dist(lm[0], lm[9]) or 1e-6   # wrist -> middle knuckle
        left_ratio = self._dist(lm[4], lm[8]) / hand_size
        right_ratio = self._dist(lm[4], lm[12]) / hand_size
        left = self._pinch(left_ratio, self.pinching)
        right = self._pinch(right_ratio, self.right_pinching)
        if left and right:  # thumb near both fingers: keep only the closer one
            left, right = left_ratio <= right_ratio, right_ratio < left_ratio

        can_click = enabled and t - self.last_click >= self.click_cooldown
        clicked = can_click and left and not self.pinching and not self.right_pinching
        right_clicked = (can_click and right and not self.right_pinching
                         and not self.pinching and not clicked)
        self.pinching, self.right_pinching = left, right
        if clicked or right_clicked:
            self.last_click = t

        # --- should the cursor move? -----------------------------------------
        index_out = self._dist(lm[0], lm[8]) > self._dist(lm[0], lm[6]) * 1.15
        should_move = index_out and not left and not right

        if not should_move:
            position = None
            if self.moving and self.cursor is not None:
                # just stopped or started a click: go back to where we aimed
                self.cursor = self._rewound_cursor(t)
                if enabled:
                    position = self._to_pixels(self.cursor, screen_size)
            self.moving = False
            return {"position": position, "clicked": clicked,
                    "right_clicked": right_clicked}

        # --- map pointer to screen with adaptive smoothing --------------------
        px, py = lm[self.pointer_id]
        span = 1.0 - 2 * self.edge_margin
        tx = min(1.0, max(0.0, (px - self.edge_margin) / span))
        ty = min(1.0, max(0.0, (py - self.edge_margin) / span))
        if self.cursor is None:
            self.cursor = (tx, ty)
        else:
            cx, cy = self.cursor
            dx, dy = tx - cx, ty - cy
            distance = math.hypot(dx, dy)
            if distance > self.deadzone:
                speed = min(1.0, distance / self.speed_for_max)
                a = self.smoothing_min + (self.smoothing_max - self.smoothing_min) * speed
                self.cursor = (cx + a * dx, cy + a * dy)
        self.moving = True
        self.history.append((t, self.cursor))
        while self.history and t - self.history[0][0] > 1.0:
            self.history.popleft()

        if not enabled:
            return {"position": None, "clicked": False, "right_clicked": False}
        return {"position": self._to_pixels(self.cursor, screen_size),
                "clicked": clicked, "right_clicked": right_clicked}
