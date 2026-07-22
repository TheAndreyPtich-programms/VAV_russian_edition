import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import queue
import os
from pathlib import Path
import urllib.request
import sys

# --- НОВЫЙ БЛОК ОПРЕДЕЛЕНИЯ ПУТИ (как в main.py) ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(os.path.dirname(sys.executable))
else:
    # Поднимаемся на уровень выше, так как hand_tracker.py лежит в подпапке (например, vision/)
    BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
# Теперь модель будет качаться в корень папки проекта/директории exe
MODEL_PATH = str(BASE_DIR / "hand_landmarker.task")
# ------------------------------------------------

# корды точек руки
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # большой палец
    (0, 5), (5, 6), (6, 7), (7, 8),  # указательный
    (0, 9), (9, 10), (10, 11), (11, 12),  # средний
    (0, 13), (13, 14), (14, 15), (15, 16),  # безымянный
    (0, 17), (17, 18), (18, 19), (19, 20),  # мизинец
    (5, 9), (9, 13), (13, 17)  # центральная часть
]


def _draw_hand_manually(frame, landmarks):
    h, w, _ = frame.shape
    for lm in landmarks:
        cx, cy = int(lm[0] * w), int(lm[1] * h)
        cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
    for connection in HAND_CONNECTIONS:
        start_idx, end_idx = connection
        lm_start = landmarks[start_idx]
        lm_end = landmarks[end_idx]
        x1, y1 = int(lm_start[0] * w), int(lm_start[1] * h)
        x2, y2 = int(lm_end[0] * w), int(lm_end[1] * h)
        cv2.line(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)


class HandTracker:
    def __init__(self):
        # Скачивание модели, если её нет
        if not os.path.exists(MODEL_PATH):
            print(f"[ЗАГРУЗКА] Загрузка модели MediaPipe: {MODEL_URL}")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            print("[УСПЕХ] Модель успешно загружена!")

        print("[ИНФО] Инициализация MediaPipe Detector...")
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        print("[УСПЕХ] MediaPipe Detector инициализирован!")

        print("[ИНФО] Подключение к камере...")
        # Добавили cv2.CAP_DSHOW для стабильности под Windows в exe
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        self.running = False
        self.thread = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.landmarks_queue = queue.Queue(maxsize=2)
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread: self.thread.join()
        self.cap.release()
        self.detector.close()

    def _capture_loop(self):
        timestamp_ms = 0
        while self.running:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                continue

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            detection_result = self.detector.detect_for_video(mp_image, timestamp_ms=timestamp_ms)
            timestamp_ms += 33

            landmarks = None
            if detection_result.hand_landmarks:
                hand_landmarks = detection_result.hand_landmarks[0]
                landmarks = [(lm.x, lm.y, lm.z) for lm in hand_landmarks]
                _draw_hand_manually(frame, landmarks)

            for q, data in [(self.frame_queue, frame), (self.landmarks_queue, landmarks)]:
                if q.full(): q.get()
                q.put(data)

    def get_frame(self):
        try:
            return self.frame_queue.get_nowait()
        except:
            return None

    def get_landmarks(self):
        try:
            return self.landmarks_queue.get_nowait()
        except:
            return None