"""
Turns an action from config.json into a real key press / scroll.

Action formats:
  {"type": "key",    "key": "right"}            -> press one key
  {"type": "hotkey", "keys": ["alt", "left"]}   -> key combination
  {"type": "scroll", "amount": -300}            -> scroll (negative = down)
Optional fields: "label" (shown on screen), "repeat" (keep firing while held)
"""

import sys
import threading
import time

import pyautogui

pyautogui.PAUSE = 0  # no built-in delay after each action


def focus_window(title_part):
    """Bring the first window whose title contains `title_part` to the front,
    so key presses go there instead of the camera preview.
    Works on Windows. On macOS/Linux it silently does nothing; click the app yourself.
    """
    if not title_part:
        return
    title_part = title_part.lower()
    try:
        active = pyautogui.getActiveWindow()
        if active and title_part in active.title.lower():
            return  # already focused
        for w in pyautogui.getAllWindows():
            if title_part in w.title.lower() and "gesture control" not in w.title.lower():
                if w.isMinimized:
                    w.restore()
                try:
                    w.activate()
                except Exception:
                    pass  # Windows sometimes reports an error even when it worked
                time.sleep(0.05)
                return
    except Exception:
        pass


def perform(action):
    kind = action["type"]
    if kind == "key":
        pyautogui.press(action["key"])
    elif kind == "hotkey":
        pyautogui.hotkey(*action["keys"])
    elif kind == "scroll":
        pyautogui.scroll(int(action["amount"]))
    elif kind == "mouse_click":
        pyautogui.click(button=action.get("button", "left"))
    else:
        raise ValueError(f"Unknown action type: {kind}")


def move_mouse(x, y):
    pyautogui.moveTo(x, y)


def screen_size():
    return tuple(pyautogui.size())


def describe(action):
    if "label" in action:
        return action["label"]
    kind = action["type"]
    if kind == "key":
        return f"press {action['key']}"
    if kind == "hotkey":
        return "+".join(action["keys"])
    if kind == "scroll":
        return f"scroll {action['amount']}"
    if kind == "mouse_click":
        return f"{action.get('button', 'left').capitalize()} click"
    return kind


def play_feedback(event, enabled=True):
    if not enabled:
        return

    if event["type"] == "action":
        frequency, duration = 880, 100
    elif event["type"] == "toggle":
        frequency, duration = (1100, 100) if event["enabled"] else (520, 160)
    else:
        return

    if sys.platform == "win32":
        import winsound
        # Beep() blocks until the sound ends; run it in the background so the
        # camera loop doesn't freeze for 100-160 ms on every action.
        threading.Thread(target=winsound.Beep, args=(frequency, duration),
                         daemon=True).start()
    else:
        print("\a", end="", flush=True)
