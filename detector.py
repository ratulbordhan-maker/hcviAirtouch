"""
Wraps MediaPipe's Gesture Recognizer (Tasks API).

It gives us, per frame: 21 hand landmarks + a gesture label from this list:
  None, Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou
"""

import os
import urllib.request

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from logic import HandReading

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
             "gesture_recognizer/float16/1/gesture_recognizer.task")
PALM_IDS = (0, 5, 9, 13, 17)  # wrist + base of each finger = stable palm centre


def ensure_model(path):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    print(f"Downloading gesture model to {path} (about 8 MB, one time only)...")
    urllib.request.urlretrieve(MODEL_URL, path)
    print("Done.")


class GestureDetector:
    def __init__(self, model_path="models/gesture_recognizer.task",
                 detection_conf=0.6, presence_conf=0.6, tracking_conf=0.5):
        ensure_model(model_path)
        options = vision.GestureRecognizerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=detection_conf,
            min_hand_presence_confidence=presence_conf,
            min_tracking_confidence=tracking_conf,
        )
        self.recognizer = vision.GestureRecognizer.create_from_options(options)
        self.last_ts = -1

    def detect(self, rgb_frame, timestamp_ms):
        """rgb_frame: HxWx3 uint8 RGB image. Returns HandReading or None."""
        ts = max(int(timestamp_ms), self.last_ts + 1)  # MediaPipe needs increasing timestamps
        self.last_ts = ts

        image = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=np.ascontiguousarray(rgb_frame))
        result = self.recognizer.recognize_for_video(image, ts)

        if not result.hand_landmarks:
            return None
        lms = result.hand_landmarks[0]

        name, score = "None", 0.0
        if result.gestures and result.gestures[0]:
            top = result.gestures[0][0]
            name, score = top.category_name, float(top.score)

        x = sum(lms[i].x for i in PALM_IDS) / len(PALM_IDS)
        y = sum(lms[i].y for i in PALM_IDS) / len(PALM_IDS)
        return HandReading(name=name, score=score, x=x, y=y,
                           landmarks=[(p.x, p.y) for p in lms])

    def close(self):
        self.recognizer.close()
