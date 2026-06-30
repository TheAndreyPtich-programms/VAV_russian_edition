import numpy as np
import math


def normalize_landmarks(landmarks):
    if not landmarks or len(landmarks) < 21:
         return None
    pts = np.array(landmarks)
    wrist = pts[0]
    palm_size = math.dist(wrist, pts[9])
    if palm_size < 0.01:
         return None


    norm = (pts - wrist) / palm_size
    norm[:, 2] = 0.0
    return norm.tolist()


def match_gesture(current_landmarks, templates, distance_threshold=0.15):  #
    if not templates:
        return None, 0.0

    current_norm = normalize_landmarks(current_landmarks)
    if current_norm is None:
        return None, 0.0

    current_arr = np.array(current_norm)
    best_name, min_dist = None, float('inf')


    OLD_KEY_INDICES = [0, 4, 8, 12, 16, 20, 9]

    for name, tmpl_data in templates.items():
        tmpl_coords = tmpl_data.get("coords") if isinstance(tmpl_data, dict) else tmpl_data
        if not tmpl_coords:
            continue

        tmpl_arr = np.array(tmpl_coords)

        #пока не переделал шаблон с 7 на 21 точку будет так. потом убрать
        if tmpl_arr.shape[0] == 7:
            eval_current = current_arr[OLD_KEY_INDICES]
        else:

            eval_current = current_arr

        dist = np.mean(np.linalg.norm(eval_current - tmpl_arr, axis=1))

        if dist < min_dist:
             min_dist = dist
             best_name = name

    confidence = max(0.0, 1.0 - (min_dist / distance_threshold))
    return (best_name, confidence) if confidence >= 0.45 else (None, 0.0)