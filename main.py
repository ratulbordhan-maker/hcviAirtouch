"""
Gesture Control Toolkit - control slides, media and browsing with hand gestures.

Run:
    python main.py                    # uses config.json, starts in "slides" profile
    python main.py --profile media    # start in another profile
    python main.py --dry-run          # detect + log, but don't press any keys
    python main.py --small            # use a 320x240 preview window
    python main.py --eval             # run randomized recognition trials
    python main.py --settings         # edit config.json in a Tkinter window

Press q or Esc in the preview window to quit.
"""

import argparse
import csv
import json
import os
import time
from datetime import datetime

import cv2

import actions
from detector import GestureDetector
from evaluation import EvaluationSession
from logic import GestureController, MouseGestureController

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),
]
WINDOW = "Gesture Control"


class EventLogger:
    """Writes every fired event to logs/session_<time>.csv for later evaluation."""

    def __init__(self, folder="logs"):
        os.makedirs(folder, exist_ok=True)
        name = datetime.now().strftime("session_%Y%m%d_%H%M%S.csv")
        self.path = os.path.join(folder, name)
        self.file = open(self.path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(["time", "profile", "event_type", "trigger", "result", "score"])

    def log(self, profile, event, score):
        if event["type"] == "action":
            row = ["action", event["trigger"], actions.describe(event["action"])]
        elif event["type"] == "toggle":
            row = ["toggle", "", "enabled" if event["enabled"] else "paused"]
        else:
            row = ["profile", "", event["profile"]]
        self.writer.writerow([datetime.now().isoformat(timespec="milliseconds"),
                              profile, *row, f"{score:.2f}"])
        self.file.flush()

    def close(self):
        self.file.close()


def draw_overlay(frame, hand, controller, fps, detect_ms, banner,
                 target_window, evaluation_text=None):
    h, w = frame.shape[:2]

    if hand and hand.landmarks:
        pts = [(int(x * w), int(y * h)) for x, y in hand.landmarks]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (200, 200, 200), 2)
        for p in pts:
            cv2.circle(frame, p, 4, (0, 180, 255), -1)
        cv2.circle(frame, (int(hand.x * w), int(hand.y * h)), 8, (255, 0, 255), 2)

    # top bar
    cv2.rectangle(frame, (0, 0), (w, 60), (30, 30, 30), -1)
    status = "ON" if controller.enabled else "PAUSED"
    color = (80, 220, 80) if controller.enabled else (60, 60, 230)
    cv2.putText(frame, f"[{status}]", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(frame, f"Profile: {controller.profile}", (120, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"{fps:4.1f} fps | detect {detect_ms:4.1f} ms", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

    target_text = f"Target: {target_window}"
    target_width = max(1, w - 20)
    while (target_text and
           cv2.getTextSize(target_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
           > target_width):
        target_text = target_text[:-4] + "..." if len(target_text) > 4 else target_text[:-1]
    target_size = cv2.getTextSize(target_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
    cv2.rectangle(frame, (8, 65), (min(w - 8, target_size[0] + 18), 89),
                  (30, 30, 30), -1)
    cv2.putText(frame, target_text, (14, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (220, 220, 220), 1)

    gesture = f"{hand.name} ({hand.score:.2f})" if hand else "no hand"
    cv2.putText(frame, gesture, (w - 230, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1)

    # hold progress bar: shows the user how long to keep holding a pose
    progress = controller.static.progress()
    if progress > 0:
        cv2.rectangle(frame, (10, h - 25), (10 + int((w - 20) * progress), h - 10),
                      (0, 200, 255), -1)
        cv2.rectangle(frame, (10, h - 25), (w - 10, h - 10), (255, 255, 255), 1)

    # banner for the last event (feedback that something happened)
    if banner:
        text, until = banner
        if time.monotonic() < until:
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
            x = (w - tw) // 2
            cv2.rectangle(frame, (x - 15, h // 2 - th - 15), (x + tw + 15, h // 2 + 15),
                          (0, 0, 0), -1)
            cv2.putText(frame, text, (x, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (0, 255, 255), 2)

    if evaluation_text:
        (tw, th), _ = cv2.getTextSize(
            evaluation_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2
        )
        x = max(10, (w - tw) // 2)
        y = max(120, h // 2 + 60)
        cv2.rectangle(frame, (x - 12, y - th - 12), (min(w - 5, x + tw + 12), y + 12),
                      (30, 30, 30), -1)
        cv2.putText(frame, evaluation_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (0, 255, 255), 2)


def event_text(event):
    if event["type"] == "action":
        return actions.describe(event["action"])
    if event["type"] == "toggle":
        return "Gestures ON" if event["enabled"] else "Gestures PAUSED"
    return f"Profile: {event['profile']}"


def profile_target_window(config, profile):
    target = config["profiles"][profile].get("target_window", "")
    return str(target).strip() or "active window"


def profile_focus_title(config, profile):
    return str(config["profiles"][profile].get("target_window", "")).strip()


def handle_event(event, profile, score, logger, dry_run, sounds_enabled, target=""):
    if event["type"] == "action" and not dry_run:
        actions.focus_window(target)
        actions.perform(event["action"])
    actions.play_feedback(event, sounds_enabled)
    if logger is not None:
        logger.log(profile, event, score)
    text = event_text(event)
    print(f"{datetime.now():%H:%M:%S}  {text}")
    return text, time.monotonic() + 1.0


def main():
    parser = argparse.ArgumentParser(description="Hand-gesture control toolkit")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--profile", help="profile to start in (overrides config)")
    parser.add_argument("--dry-run", action="store_true",
                        help="detect and log gestures but do not press any keys")
    parser.add_argument("--small", action="store_true",
                        help="show the camera preview in a 320x240 window")
    parser.add_argument("--eval", action="store_true",
                        help="run 20 randomized recognition trials per gesture")
    parser.add_argument("--settings", action="store_true",
                        help="open the settings window and save changes to config.json")
    args = parser.parse_args()

    if args.settings:
        import settings
        settings.open_settings(args.config)
        return

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    if args.profile:
        config["active_profile"] = args.profile

    controller = GestureController(config)
    mouse_config = config.get("mouse", {})
    mouse_controller = MouseGestureController(**mouse_config)
    evaluation = EvaluationSession(
        hold_frames=config.get("static", {}).get("hold_frames", 8),
        minimum_score=config.get("static", {}).get("min_score", 0.6),
        swipe_settings=config.get("swipe"),
    ) if args.eval else None
    evaluation_saved = False
    detector = GestureDetector()
    logger = None if args.eval else EventLogger()

    cap = cv2.VideoCapture(config.get("camera_index", 0))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.get("frame_width", 640))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.get("frame_height", 480))
    if not cap.isOpened():
        detector.close()
        if logger is not None:
            logger.close()
        raise SystemExit("Could not open the webcam. Try another camera_index in config.json.")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    if args.small:
        cv2.resizeWindow(WINDOW, 320, 240)
    try:
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)  # keep preview on top
    except Exception:
        pass

    if logger is not None:
        print(f"Logging to {logger.path}")
    if evaluation is not None:
        print("Evaluation mode: perform the gesture shown in the camera window.")
    else:
        print("Hold 'ILoveYou' (thumb + index + pinky up) to pause/resume, "
              "'Victory' to switch profile. Press q in the window to quit.")

    banner = None
    fps, last_frame = 0.0, time.monotonic()
    screen_size = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame not received, stopping.")
                break
            frame = cv2.flip(frame, 1)  # mirror, so moving right looks like right
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            now = time.monotonic()
            t0 = time.perf_counter()
            hand = detector.detect(rgb, now * 1000)
            detect_ms = (time.perf_counter() - t0) * 1000

            evaluation_text = None
            if evaluation is not None:
                result = evaluation.update(now, hand)
                evaluation_text = evaluation.prompt
                if result:
                    detected = result["detected"] or "nothing"
                    print(
                        f"Trial {result['trial']}: {result['gesture']} -> "
                        f"{detected} ({result['reaction_seconds']:.2f}s)"
                    )
                if evaluation.finished and not evaluation_saved:
                    path = evaluation.save()
                    evaluation_saved = True
                    print(f"Evaluation results saved to {path}")
            else:
                event = controller.process(now, hand)
                if event:
                    banner = handle_event(
                        event,
                        controller.profile,
                        hand.score if hand else 0.0,
                        logger,
                        args.dry_run,
                        config.get("sounds_enabled", True),
                        profile_focus_title(config, controller.profile),
                    )

                if config["profiles"][controller.profile].get("mode") == "mouse":
                    if screen_size is None:
                        screen_size = actions.screen_size()
                    mouse_result = mouse_controller.update(
                        now,
                        hand,
                        (frame.shape[1], frame.shape[0]),
                        screen_size,
                        enabled=controller.enabled,
                    )
                    if mouse_result:
                        position = mouse_result["position"]
                        if position is not None and not args.dry_run:
                            actions.move_mouse(*position)
                        profile_cfg = config["profiles"][controller.profile]
                        for flag, key, trigger in (
                            ("clicked", "pinch_action", "Pinch"),
                            ("right_clicked", "right_pinch_action", "Right_Pinch"),
                        ):
                            click_action = profile_cfg.get(key)
                            if mouse_result.get(flag) and click_action:
                                banner = handle_event(
                                    {"type": "action", "trigger": trigger,
                                     "action": click_action},
                                    controller.profile,
                                    hand.score if hand else 0.0,
                                    logger,
                                    args.dry_run,
                                    config.get("sounds_enabled", True),
                                    profile_focus_title(config, controller.profile),
                                )
                else:
                    mouse_controller.reset()

            dt = now - last_frame
            last_frame = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)  # smoothed

            draw_overlay(
                frame,
                hand,
                controller,
                fps,
                detect_ms,
                banner,
                profile_target_window(config, controller.profile),
                evaluation_text,
            )
            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        if evaluation is not None and not evaluation_saved:
            path = evaluation.save()
            print(f"Partial evaluation results saved to {path}")
        cap.release()
        cv2.destroyAllWindows()
        detector.close()
        if logger is not None:
            logger.close()


if __name__ == "__main__":
    main()
