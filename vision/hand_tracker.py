import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import queue
import os
import urllib.request

#установка нужной мне модели если еще не установлена
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")

# корды точек руки
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  #большой палец
    (0, 5), (5, 6), (6, 7), (7, 8),  #указательный
    (0, 9), (9, 10), (10, 11), (11, 12),  #средний
    (0, 13), (13, 14), (14, 15), (15, 16),  #безымянный
    (0, 17), (17, 18), (18, 19), (19, 20),  #мизинец
    (5, 9), (9, 13), (13, 17)  #центральная часть
]

#рисовалка точек и линий для наглядности
def _draw_hand_manually(frame, landmarks):
    h, w, _ = frame.shape
    # линии
    for i, j in HAND_CONNECTIONS:
        p1, p2 = landmarks[i], landmarks[j]
        cv2.line(frame,
                 (int(p1[0] * w), int(p1[1] * h)),
                 (int(p2[0] * w), int(p2[1] * h)),
                 (0, 255, 0), 2)
    # рисование точек
    for (x, y, _) in landmarks:
        cv2.circle(frame, (int(x * w), int(y * h)), 4, (255, 0, 0), -1)


def _download_model():
    if not os.path.exists(MODEL_PATH):
        print("Загрузка модели hand_landmarker.task...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Модель загружена.")


class HandTracker:
    def __init__(self):
        _download_model()

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError("Камера не найдена или занята другим приложением.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self.frame_queue = queue.Queue(maxsize=1)
        self.landmarks_queue = queue.Queue(maxsize=1)
        self.running = False
        self.thread = None

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