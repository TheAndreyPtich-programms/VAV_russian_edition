import pyautogui

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0


class MouseController:
    def __init__(self, screen_w, screen_h, smoothing=0.85, invert_x=True, invert_y=False,
                 active_zone=(0.12, 0.88, 0.08, 0.92), game_mode=False, sensitivity=200):
        #sensitivity отвечает за плавность камеры вероятно не будет использоваться возникают проблемы на тестах
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.smoothing = smoothing
        self.drag_smoothing = 0.92
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.active_zone = active_zone
        self.prev_x, self.prev_y = None, None
        self.held_button = None

        # Настройки для игр
        self.game_mode = game_mode
        self.sensitivity = sensitivity

        # Новые переменные для гибридного режима
        self.prev_abs_x = None
        self.prev_abs_y = None

    def move_cursor(self, hx, hy, is_dragging=False):
        if self.game_mode:
            pass #функция не может использоваться ввиду отмены решения ее делать на данный момент. взять на рассмотрение в будущем может что смогу. на данный момент не работает
            '''            if self.prev_x is None:
                self.prev_x, self.prev_y = hx, hy
                return

            dx = hx - 0.5
            dy = hy - 0.5

            if self.invert_x: dx = -dx
            if self.invert_y: dy = -dy

            DEADZONE = 0.15  

            #обычная мышь в центре
            if abs(dx) <= DEADZONE and abs(dy) <= DEADZONE:
                self.prev_rel_x = None
                self.prev_rel_y = None

                norm_x = (dx + DEADZONE) / (2 * DEADZONE)
                norm_y = (dy + DEADZONE) / (2 * DEADZONE)

                precision_zone_w = self.screen_w * 0.35
                precision_zone_h = self.screen_h * 0.35

                screen_center_x = self.screen_w / 2
                screen_center_y = self.screen_h / 2

                target_x = screen_center_x - (precision_zone_w / 2) + (norm_x * precision_zone_w)
                target_y = screen_center_y - (precision_zone_h / 2) + (norm_y * precision_zone_h)

                s = self.drag_smoothing if is_dragging else 0.88

                if self.prev_abs_x is None:
                    self.prev_abs_x, self.prev_abs_y = target_x, target_y
                else:
                    self.prev_abs_x = self.prev_abs_x * s + target_x * (1 - s)
                    self.prev_abs_y = self.prev_abs_y * s + target_y * (1 - s)

                pyautogui.moveTo(int(self.prev_abs_x), int(self.prev_abs_y))

            #ускорение курсора как на геймпадах для более быстрого поворота
            else:
                self.prev_abs_x = None
                self.prev_abs_y = None

                power = 2.0  
                final_dx = 0
                final_dy = 0

                if abs(dx) > DEADZONE:
                    accel_x = (abs(dx) - DEADZONE) / (0.5 - DEADZONE)
                    speed_x = (accel_x ** power) * self.sensitivity
                    final_dx = int(speed_x * (1 if dx > 0 else -1))

                if abs(dy) > DEADZONE:
                    accel_y = (abs(dy) - DEADZONE) / (0.5 - DEADZONE)
                    speed_y = (accel_y ** power) * self.sensitivity
                    final_dy = int(speed_y * (1 if dy > 0 else -1))

                if final_dx != 0 or final_dy != 0:
                    pyautogui.moveRel(final_dx, final_dy)

            self.prev_x, self.prev_y = hx, hy'''

        else:

            x_min, x_max, y_min, y_max = self.active_zone
            hx = max(x_min, min(hx, x_max))
            hy = max(y_min, min(hy, y_max))

            width = x_max - x_min
            height = y_max - y_min
            hx_norm = (hx - x_min) / width if width > 0 else 0.5
            hy_norm = (hy - y_min) / height if height > 0 else 0.5

            target_x = (1.0 - hx_norm) * self.screen_w if self.invert_x else hx_norm * self.screen_w
            target_y = hy_norm * self.screen_h

            s = self.drag_smoothing if is_dragging else self.smoothing

            if self.prev_x is None:
                self.prev_x, self.prev_y = target_x, target_y
            else:
                self.prev_x = self.prev_x * s + target_x * (1 - s)
                self.prev_y = self.prev_y * s + target_y * (1 - s)

            pyautogui.moveTo(int(self.prev_x), int(self.prev_y))

    def update_hold(self, button, is_holding):
        if is_holding:
            if self.held_button != button:
                pyautogui.mouseDown(button=button)
                self.held_button = button
        else:
            if self.held_button == button:
                pyautogui.mouseUp(button=button)
                self.held_button = None

    def release_all(self):
        if self.held_button:
            pyautogui.mouseUp(button=self.held_button)
            self.held_button = None