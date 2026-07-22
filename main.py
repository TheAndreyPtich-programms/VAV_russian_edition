import sys
import subprocess
import importlib.util


def bootstrap_dependencies():
    print("проверка нужных библиотек...")

    deps = {
        "cv2": "opencv-python",
        "mediapipe": "mediapipe",
        "vosk": "vosk",
        "pyautogui": "pyautogui",
        "keyboard": "keyboard",
        "numpy": "numpy",
        "PIL": "Pillow",
        "screeninfo": "screeninfo",
        "pyaudio": "PyAudio"
    }

    missing = []
    for mod, pkg in deps.items():
        if importlib.util.find_spec(mod) is None:
            missing.append(pkg)

    if not missing:
        print("все библиотеки установлены")
        return

    print(f"установка библиотек: {', '.join(missing)}")

    # Разделяем PyAudio и остальные, так как PyAudio на Windows часто требует pipwin
    standard_pkgs = [p for p in missing if p != "PyAudio"]
    need_pyaudio = "PyAudio" in missing

    if standard_pkgs:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *standard_pkgs])
        except:
            print("Ошибка установки основных библиотек.")

    if need_pyaudio:
        print("Попытка установки PyAudio...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "PyAudio"])
        except:
            print("Стандартная установка PyAudio не удалась. Пробуем через pipwin...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pipwin"])
                subprocess.check_call([sys.executable, "-m", "pipwin", "install", "pyaudio"])
            except:
                print("ВНИМАНИЕ: Не удалось установить PyAudio. Микрофон может не работать.")

    print("все библиотеки установлены")


bootstrap_dependencies()

import pyautogui
import tkinter as tk
from tkinter import scrolledtext, messagebox
import json
import keyboard
import threading
import queue
import time
import os
import cv2
import ctypes
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent))
from audio.recognizer import VoskRecognizer
from vision.hand_tracker import HandTracker
from vision.gesture_matcher import match_gesture
from vision.mouse_controller import MouseController
from commands.matcher import match_command
from audio.microphone import get_microphone_stream

LOG_FILE = Path(__file__).parent / "assistant.log"


def write_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

import subprocess
import os

def open_app_or_file(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen([path], shell=True)
        write_log(f"Запущено: {path}")
        return True
    except:
        error_msg = f"Ошибка запуска {path}"
        write_log(error_msg)
        return False


class CameraPreviewWindow:
    def __init__(self, parent, tracker):
        self.parent = parent
        self.tracker = tracker
        self.window = tk.Toplevel(parent)
        self.window.title("Просмотр камеры")
        self.window.geometry("660x530")
        self.window.transient(parent)

        # Холст для отображения видео
        self.canvas = tk.Label(self.window, bg="black", width=640, height=480)
        self.canvas.pack(pady=10, padx=10)

        self._update_video_feed()

    def _update_video_feed(self):
        if not self.window.winfo_exists():
            return

        frame = self.tracker.get_frame()
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from PIL import Image, ImageTk

            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)


            self.canvas.imgtk = imgtk
            self.canvas.configure(image=imgtk)

        self.window.after(30, self._update_video_feed)


class VoiceAssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Голосовой помощник")
        self.root.geometry("750x550")

        self.config_file = Path(__file__).parent / "config.json"
        self.config = self._load_config()
        self.model_paths = self.config.get("model_paths", {})

        self.language_label = None
        self.current_language = "ru"

        self.gesture_window_open = False
        self.vision_enabled = False
        self.hand_tracker = None
        self.mouse_ctrl = None
        self.vision_thread = None
        self.gesture_templates = {}
        self.hand_state = "lost"

        self.stored_text = ""
        self.remembering_mode = False
        self.remember_timeout = None

        self.ru_recognizer = VoskRecognizer(self.model_paths.get("ru"))
        self.en_recognizer = VoskRecognizer(self.model_paths.get("en"))
        self.active_recognizer = self.ru_recognizer
        self.original_recognizer = None

        self.command_queue = queue.Queue()
        self.microphone_enabled = False
        self.microphone_thread = None
        self.audio_stream = None
        self.pyaudio_obj = None
        self.recognizer = None

        self.pressed_keys = set()

        self.toast_window = None
        self.toast_timer = None

        self._create_widgets()
        #self._update_language_display()

        self._process_commands()

        write_log("Программа запущена")
        self.add_log("Все библиотеки установлены и проверены")

        self.root.after(1500, self._auto_start_services)

    def _reset_remember_timer(self):
        if hasattr(self, 'remember_timeout') and self.remember_timeout:
            self.root.after_cancel(self.remember_timeout)
        self.remember_timeout = self.root.after(10000, self._exit_remember_mode)

    def toggle_vision(self):
        if getattr(self, 'vision_enabled', False):
            self._stop_vision()
        else:
            self._start_vision()

    def _start_vision(self):
        import screeninfo
        try:
            monitors = screeninfo.get_monitors()
            w, h = monitors[0].width, monitors[0].height
        except Exception:
            w, h = 1920, 1080

        self.config.setdefault("gestures", {})

        from vision.hand_tracker import HandTracker
        from vision.mouse_controller import MouseController

        self.hand_tracker = HandTracker()
        self.hand_tracker.start()

        # Проверка доступа к камере
        if not self.hand_tracker.cap.isOpened():
            self.add_log("ОШИБКА: Не удалось получить доступ к камере!")
            self.hand_tracker.stop()
            return

        self.add_log("Камера успешно инициализирована и готова к работе.")
        self.show_toast("Камера и жесты включены")

        # Настройки мыши (game_mode=True для Minecraft, False для рабочего стола)
        self.mouse_ctrl = MouseController(
            w, h, smoothing=0.78, invert_x=False, invert_y=False,
            active_zone=(0.12, 0.88, 0.08, 0.92),
            game_mode=False, sensitivity=2000
        )
        self.gesture_templates = self.config["gestures"]

        self.vision_enabled = True
        self.vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
        self.vision_thread.start()

        if hasattr(self, 'mic_button'):
            self.mic_button.config(text="Выкл. камеру", bg="lightcoral")

    def _stop_vision(self):
        self.vision_enabled = False


        if hasattr(self, 'mouse_ctrl') and self.mouse_ctrl:
            self.mouse_ctrl.release_all()

        if hasattr(self, 'hand_tracker') and self.hand_tracker:
            self.hand_tracker.stop()
            self.hand_tracker = None

        self.mouse_ctrl = None
        self.add_log("Камера и управление жестами выключены")
        self.show_toast("Камера и жесты выключены")

        if hasattr(self, 'mic_button'):
            self.mic_button.config(text="Вкл. камеру", bg="lightgray")

    def _vision_loop(self):
        import time

        hand_lost_frames = 0
        LOST_THRESHOLD = 25

        last_scroll_time = 0
        scroll_cooldown = 0.12
        hold_state = None

        while self.vision_enabled:


            if getattr(self, 'gesture_window_open', False):
                time.sleep(0.1)
                continue

            landmarks = self.hand_tracker.get_landmarks()
            now = time.time()

            if landmarks:

                if hand_lost_frames >= LOST_THRESHOLD:
                    self.hand_state = "found"
                    self.add_log("Рука распознана")
                    self.show_toast("Рука распознана")
                hand_lost_frames = 0


                # Движение курсора
                hx, hy = landmarks[9][0], landmarks[9][1]
                self.mouse_ctrl.move_cursor(hx, hy, is_dragging=(hold_state is not None))

                # распознавание жеста
                templates = self.config.get("gestures", {})
                matched, conf = (None, 0.0)
                if templates:
                    matched, conf = match_gesture(landmarks, templates, distance_threshold=0.25)

                action = templates.get(matched, {}).get("action", "") if matched else ""

                # действия
                if matched and action in ["hold_left", "hold_right"]:
                    btn = 'left' if action == "hold_left" else 'right'
                    hold_state = btn
                    self.mouse_ctrl.update_hold(btn, True)
                elif hold_state:

                    if conf < 0.35:
                        self.mouse_ctrl.release_all()
                        hold_state = None
                    else:
                        self.mouse_ctrl.update_hold(hold_state, True)
                elif matched and action == "release":
                    self.mouse_ctrl.release_all()
                    hold_state = None
                elif matched and action.startswith("scroll_"):
                    if now - last_scroll_time > scroll_cooldown:
                        direction = 1 if action == "scroll_up" else -1
                        pyautogui.scroll(direction * 3)
                        last_scroll_time = now
                elif matched and action == "left_click":
                    pyautogui.click()
                    time.sleep(0.1)
                else:

                    if hold_state:
                        self.mouse_ctrl.release_all()
                        hold_state = None
            else:
                hand_lost_frames += 1

                if hand_lost_frames == LOST_THRESHOLD:
                    self.hand_state = "lost"
                    self.add_log("Рука потеряна")
                    self.show_toast("Рука потеряна")
                    self.mouse_ctrl.release_all()
                    hold_state = None
                elif hand_lost_frames > LOST_THRESHOLD:
                    self.mouse_ctrl.release_all()
                    hold_state = None

            time.sleep(0.01)

    def _load_config(self):
        default_config = {
            "wake_word": "компьютер",
            "commands": {
                "open_apps": {
                    "Блокнот": {"phrases": ["блокнот", "notepad", "заметки"], "path": "notepad.exe"},
                    "Калькулятор": {"phrases": ["калькулятор", "calc", "посчитать"], "path": "calc.exe"}
                }
            }
        }
        if not self.config_file.exists():
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            return default_config
        else:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)

    def open_settings(self):
        from gui.settings_window import SettingsWindow
        def on_saved():
            self.config = self._load_config()
            self.add_log("Настройки обновлены")

        SettingsWindow(self.root, self.config_file, on_saved)

    def _create_widgets(self):
        # Верхняя строка с кнопками
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        # 👇 НОВАЯ КНОПКА
        tk.Button(top_frame, text="Просмотр камеры", command=self.open_camera_preview).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Управление жестами", command=self.toggle_vision).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Настройка жестов", command=self.open_gesture_window).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Настройки", command=self.open_settings).pack(side=tk.LEFT, padx=5)

        self.mic_button = tk.Button(top_frame, text="Вкл. микрофон", command=self.toggle_microphone, bg="lightgray")
        self.mic_button.pack(side=tk.LEFT, padx=5)

        tk.Button(top_frame, text="Очистить лог", command=self.clear_log_display).pack(side=tk.RIGHT, padx=5)

        # Индикатор языка
        #self.language_label = tk.Label(top_frame, text="🇷🇺 РУС", font=("Arial", 10, "bold"), bg="lightgreen", padx=5, pady=2, relief=tk.RIDGE)
        #self.language_label.pack(side=tk.RIGHT, padx=10)

        # Ручной ввод команды
        manual_frame = tk.Frame(self.root)
        manual_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(manual_frame, text="Ручной ввод команды:").pack(anchor=tk.W)
        entry_frame = tk.Frame(manual_frame)
        entry_frame.pack(fill=tk.X)
        self.command_entry = tk.Entry(entry_frame, width=80)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(entry_frame, text="Выполнить", command=self.submit_manual_command).pack(side=tk.RIGHT)

        # Область лога
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tk.Label(log_frame, text="Лог работы:").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

    def _auto_start_services(self):
        #запуск камеры и микро
        self.add_log("Автоматический запуск сервисов...")
        self._start_microphone()
        # время на загрузку ресов
        time.sleep(10)
        self._start_vision()
    def open_camera_preview(self):
        if not getattr(self, 'hand_tracker', None):
            self.add_log("Сначала включите камеру кнопкой 'Управление жестами'!")
            self.show_toast("Камера выключена")
            return

        # окно с камеры
        CameraPreviewWindow(self.root, self.hand_tracker)


    def show_toast(self, event_message):
        if self.toast_timer:
            self.root.after_cancel(self.toast_timer)

        # окно уведомлений
        if self.toast_window is None or not self.toast_window.winfo_exists():
            self.toast_window = tk.Toplevel(self.root)
            self.toast_window.overrideredirect(True)  #zagolovok
            self.toast_window.attributes('-topmost', True)  #poverh okon
            self.toast_window.attributes('-alpha', 0.70)  #можно настроить прозначность
            self.toast_window.configure(bg='#2d2d2d')

            self.toast_label = tk.Label(
                self.toast_window, text="", fg='#ffffff', bg='#2d2d2d',
                font=('Segoe UI', 10, 'bold'), padx=15, pady=10, justify='left'
            )
            self.toast_label.pack()

        # Формируем текст статуса
        cam_status = "камера: ВКЛ" if getattr(self, 'vision_enabled', False) else "камера: ВЫКЛ"
        mic_status = "микро: ВКЛ" if getattr(self, 'microphone_enabled', False) else "микро: ВЫКЛ"
        hand_status = "Рука: Найдена" if getattr(self, 'hand_state', 'lost') == 'found' else "Рука: Потеряна"

        full_text = f"{event_message}\n\n{cam_status}  |  {mic_status}  |  {hand_status}"
        self.toast_label.config(text=full_text)


        self.toast_window.update_idletasks()
        width = self.toast_window.winfo_width()
        height = self.toast_window.winfo_height()
        x = self.root.winfo_screenwidth() - width - 30
        y = self.root.winfo_screenheight() - height - 30
        self.toast_window.geometry(f"+{x}+{y}")


        self.toast_window.deiconify()

        # скрывается через 3.5 сек
        self.toast_timer = self.root.after(3500, self._hide_toast)

    def _hide_toast(self):

        if self.toast_window and self.toast_window.winfo_exists():
            self.toast_window.withdraw()
        self.toast_timer = None

    def open_gesture_window(self):
        self.gesture_window_open = True  # Блокируем управление мышью
        if not self.hand_tracker:
            self._start_vision()
            self.root.after(500, self._create_gesture_ui)
        else:
            self._create_gesture_ui()

    def _create_gesture_ui(self):
        from gui.gesture_window import GestureWindow
        GestureWindow(self.root, self.config_file, self.hand_tracker)

    def add_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        write_log(message)

    '''   работа с языком пока проблемна код закоменчен. возможно вернусь позже
    def _update_language_display(self):
        
        if not self.language_label:
            return
        if self.current_language == "ru":
            self.language_label.config(text="🇷🇺 РУС", bg="lightgreen")
        elif self.current_language == "en":
            self.language_label.config(text="🇬🇧 ENG", bg="lightcoral")
        else:
            self.language_label.config(text="???", bg="lightgray")
    '''
    def clear_log_display(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)


    def submit_manual_command(self):
        command = self.command_entry.get().strip()
        if command:
            self.command_entry.delete(0, tk.END)
            self.command_queue.put(command)
            self.add_log(f"[Ручной ввод] {command}")
        else:
            messagebox.showinfo("Внимание", "Введите команду")

    #Микрофон
    def toggle_microphone(self):
        if self.microphone_enabled:
            self._stop_microphone()
        else:
            self._start_microphone()

    def _start_microphone(self):
        try:
            from audio.microphone import get_microphone_stream

            self.audio_stream, self.pyaudio_obj = get_microphone_stream()
            if self.audio_stream is None:
                self.add_log("Не удалось получить доступ к микрофону")
                return

            model_path = self.model_paths.get(self.current_language)
            if not model_path or not Path(model_path).exists():
                self.add_log(f"Модель для языка {self.current_language} не найдена: {model_path}")
                return
            self.active_recognizer = VoskRecognizer()
            self.active_recognizer.load_model(model_path)  # загружаем модель в память
            self.microphone_enabled = True
            self.mic_button.config(text="Выключить микрофон", bg="lightgreen")
            self.add_log(f"Микрофон включён. Язык: {self.current_language}")
            self.show_toast("Микрофон включён")
            self.microphone_thread = threading.Thread(target=self._listen_microphone, daemon=True)
            self.microphone_thread.start()
        except:
            self.add_log(f"Ошибка включения микрофона: ")

    def _stop_microphone(self):
        self.microphone_enabled = False
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None
        if self.pyaudio_obj:
            self.pyaudio_obj.terminate()
            self.pyaudio_obj = None

        if self.active_recognizer:
            self.active_recognizer = None
        self.mic_button.config(text="Включить микрофон", bg="lightgray")
        self.add_log("Микрофон выключен, модель выгружена.")
        self.show_toast("Микрофон выключен")

    def _listen_microphone(self):
        wake_word = self.config.get("wake_word", "компьютер").lower() #ожидание нужного слова б
        try:
            while self.microphone_enabled and self.audio_stream and self.active_recognizer:
                data = self.audio_stream.read(4000, exception_on_overflow=False) #4000байт инфы с микрофона
                if self.active_recognizer.accept_waveform(data):
                    result = self.active_recognizer.result()
                    text = result.get("text", "").strip().lower() #уборка мусора из текст
                    if text:
                        self.add_log(f"[Микрофон] Распознано: {text}")
                        if self.remembering_mode:
                            self.command_queue.put(text)
                            continue
                        if wake_word in text:
                            command_part = text.split(wake_word, 1)[-1].strip()
                            if command_part:
                                self.add_log(f"[Микрофон] Команда: {command_part}")
                                self.command_queue.put(command_part)
                            else:
                                self.add_log("[Микрофон] Только ключевое слово")
                    time.sleep(0.01)
        except:
            if self.microphone_enabled:
                self.add_log(f"Ошибка в потоке микрофона")

    # работа команд
    def _process_commands(self):
        try:
            while True:
                command = self.command_queue.get_nowait()
                self._execute_command(command)
        except:
            pass
        finally:
            self.root.after(100, self._process_commands)

    def _execute_command(self, command_text):
        import pyautogui
        self.add_log(f"Обработка: '{command_text}'")
        apps = self.config.get("commands", {}).get("open_apps", {})
        text_cmds = self.config.get("text_commands", {})

        #переключение языка (не работает возможно потом сделаю)
        '''if command_text in ["переключи язык", "английский", "русский", "сменить язык"]:
            new_lang = None
            if "английский" in command_text or "сменить" in command_text:
                new_lang = "en"
            elif "russian" in command_text:
                new_lang = "ru"
            if new_lang and new_lang != self.current_language:
                if not self.microphone_enabled:
                    self.current_language = new_lang
                    self._update_language_display()  # <-- ДОБАВИТЬ
                    self.add_log(f"Язык (для следующего включения) переключён на {new_lang}.")
                    return
                # Если микрофон активен
                self.add_log(f"Переключаю язык на {new_lang}...")
                new_model_path = self.model_paths.get(new_lang)
                if not new_model_path or not Path(new_model_path).exists():
                    self.add_log(f"Модель для {new_lang} не найдена")
                    return
                self.active_recognizer = None
                self.active_recognizer = VoskRecognizer()
                self.active_recognizer.load_model(new_model_path)
                self.current_language = new_lang
                self._update_language_display()  # <-- ДОБАВИТЬ
                self.add_log(f"Язык переключён на {self.current_language}")
            else:
                self.add_log(f"ℹЯзык уже {self.current_language}.")
            return'''

        # открытие приложений
        if command_text.startswith("приложение ") or command_text.startswith("открой "):
            clean_command = command_text.split(" ", 1)[1].strip()
            self.add_log(f"Поиск приложения по запросу: '{clean_command}'")

            apps = self.config.get("commands", {}).get("open_apps", {})
            match = match_command(clean_command, apps)

            if match:
                app_name, app_path, score = match
                self.add_log(f"Совпадение: '{app_name}' (уверенность {score:.1f}%)")
                if open_app_or_file(app_path):
                    self.add_log(f"Запущено: {app_name}")
                else:
                    self.add_log(f"Не удалось запустить {app_name}")
            else:
                self.add_log(f"риложение '{clean_command}' не найдено в настройках.")
            return

        # открытие приложений по конфигу если ранее ничего не нашлось
        apps = self.config.get("commands", {}).get("open_apps", {})
        if apps:
            match = match_command(command_text, apps)
            if match:
                app_name, app_path, score = match
                self.add_log(f"Совпадение: '{app_name}' (уверенность {score:.1f}%)")
                if open_app_or_file(app_path):
                    self.add_log(f"Запущено: {app_name}")
                else:
                    self.add_log(f"Не удалось запустить {app_name}")
                return

        #  запомнить текмт
        remember_triggers = text_cmds.get("remember_text", ["запомни"])
        if any(command_text.startswith(tr) for tr in remember_triggers):
            switch_to_en = "английский" in command_text
            if switch_to_en:
                # Сохраняем текущую модель, чтобы потом вернуть
                self.original_recognizer = self.active_recognizer
                # Переключаем на английскую
                if hasattr(self, 'en_recognizer') and self.en_recognizer:
                    self.active_recognizer = self.en_recognizer
                    self.add_log("Переключено на АНГЛИЙСКУЮ модель для запоминания")
                else:
                    self.add_log("Английская модель не загружена, запоминаю на текущем языке")
            else:
                self.original_recognizer = None

            self.remembering_mode = True
            self.stored_text = ""
            self._reset_remember_timer()
            self.add_log(
                "Режим запоминания текста включён. Говорите фразы. Скажите 'хватит' или ждите 10 секунд молчания.")
            return

        if self.remembering_mode:
            if command_text in ["хватит", "стоп", "отмена"]:
                self._exit_remember_mode()
                self.add_log(
                    f"Запомнен текст: {self.stored_text[:100]}{'...' if len(self.stored_text) > 100 else ''}")
            else:
                if self.stored_text:
                    self.stored_text += " " + command_text
                else:
                    self.stored_text = command_text
                self.add_log(f"Запомнено: {command_text}")
                # Сбрасываем таймер
                self._reset_remember_timer()
            return

        # вставить запомненное
        insert_triggers = text_cmds.get("insert_remembered", ["вставь запомненное", "скажи"])
        if any(command_text.startswith(tr) for tr in insert_triggers):
            if self.stored_text:
                try:
                    import pyautogui
                    import keyboard
                    import time
                    self.root.clipboard_clear()
                    self.root.clipboard_append(self.stored_text)
                    self.root.update()
                    time.sleep(0.1)
                    keyboard.send('ctrl+v')
                    self.add_log(f"Вставлен запомненный текст через Ctrl+V: {self.stored_text[:100]}")

                except:
                    self.add_log(f'Ошибка вставки')
            else:
                self.add_log("Нет запомненного текста")
            return

        #копирование с помощью буфера
        copy_paste_triggers = text_cmds.get("copy_paste", ["скопируй", "копировать", "скопируй и вставь"])
        self.add_log(f"Проверка копирования: команда '{command_text}' триггеры {copy_paste_triggers}")
        if any(command_text.startswith(tr) for tr in copy_paste_triggers):
            self.add_log("✅ Сработал триггер копирования")
            try:
                import pyautogui
                import time
                import keyboard
                self.add_log("▶️ Выполняю Ctrl+C...")
                keyboard.send('ctrl+c')
                time.sleep(0.2)
                self.add_log("✅ Команда копирования выполнена")
            except:
                self.add_log(f"Ошибка копирования")
            return

        #вставка  с помощью буфера
        paste_triggers = text_cmds.get("paste", ["вставь", "вставить"])
        if any(command_text.startswith(tr) for tr in paste_triggers):
            try:
                import pyautogui
                pyautogui.hotkey('ctrl', 'v')
                self.add_log("Выполнена вставка (Ctrl+V)")
            except:
                self.add_log(f"Ошибка вставки")
            return

        #вырезать
        cut_paste_triggers = text_cmds.get("cut_paste", ["вырежи", "вырезать"])
        if any(command_text.startswith(tr) for tr in cut_paste_triggers):
            try:
                import pyautogui
                import time
                pyautogui.hotkey('ctrl', 'x')
                time.sleep(0.1)
                self.add_log("Вырезано")
            except:
                self.add_log(f"Ошибка вырезания/вставки")
            return

        # Печать текста
        if command_text.startswith("текст"):
            text_to_type = command_text[5:].strip()
            if text_to_type:
                try:
                    import pyautogui
                    pyautogui.write(text_to_type)
                    self.add_log(f"Напечатан текст: {text_to_type}")
                except:
                    self.add_log(f"Ошибка печати")
            else:
                self.add_log("Не указан текст")
            return

        #  решение примеров
        if command_text.startswith("реши"):
            expr = command_text[4:].strip()
            if not expr:
                self.add_log("Не указано выражение после 'реши'. Пример: реши 2+2 или реши пять плюс три")
                return


            operator_map = {
                "плюс": "+", "прибавить": "+", "сложить": "+",
                "минус": "-", "вычесть": "-", "отнять": "-",
                "умножить": "*", "умножить на": "*", "помножить": "*",
                "делить": "/", "разделить": "/", "поделить": "/"
            }
            for word, sym in operator_map.items():
                expr = expr.replace(word, sym)


            number_map = {
                "ноль": "0", "один": "1", "два": "2", "три": "3", "четыре": "4",
                "пять": "5", "шесть": "6", "семь": "7", "восемь": "8", "девять": "9",
                "десять": "10", "одиннадцать": "11", "двенадцать": "12", "тринадцать": "13",
                "четырнадцать": "14", "пятнадцать": "15", "шестнадцать": "16", "семнадцать": "17",
                "восемнадцать": "18", "девятнадцать": "19", "двадцать": "20",
                "тридцать": "30", "сорок": "40", "пятьдесят": "50",
                "шестьдесят": "60", "семьдесят": "70", "восемьдесят": "80", "девяносто": "90"
            }

            for word, digit in number_map.items():
                expr = expr.replace(word, digit)


            expr = expr.strip()


            import re
            expr_clean = re.sub(r'[^0-9+\-*/.\s()]', '', expr)
            if not expr_clean:
                self.add_log("Пустое выражение после фильтрации")
                return

            try:
                result = eval(expr_clean)
                rounded = round(result, 5)
                result_str = str(int(rounded)) if rounded.is_integer() else str(rounded)
                self.add_log(f"🧮 {expr_clean} = {result_str}")


                self.root.clipboard_clear()
                self.root.clipboard_append(result_str)
                self.root.update()
                #используется и кейбоард и пайаутогуи т.к. иногда эта фигня не работает
                try:
                    import keyboard
                    keyboard.send('ctrl+v')
                    self.add_log(f"✅ Результат '{result_str}' вставлен")
                except ImportError:
                    import pyautogui
                    pyautogui.hotkey('ctrl', 'v')
                    self.add_log(f"✅ Результат '{result_str}' вставлеH")
                except:
                    self.add_log(f"Не удалось вставить, но результат в буфере обмена")

            except ZeroDivisionError:
                self.add_log("Ошибка: деление на ноль")
            except:
                self.add_log(f"Ошибка вычисления")
            return

             #нажате клавишь

        SPECIAL_KEYS_MAP = {
            "пробел": "space", "space": "space",
            "энтер": "enter", "enter": "enter", "ввод": "enter",
            "таб": "tab", "tab": "tab",
            "эскейп": "esc", "esc": "esc",
            "шифт": "shift", "shift": "shift",
            "контроль": "ctrl", "ctrl": "ctrl", "control": "ctrl",
            "альт": "alt", "alt": "alt", "алта":"alt",
            "делит": "delete", "delete": "delete", "удалить": "delete",
            "бэкспейс": "backspace", "backspace": "backspace", "стереть": "backspace",
            "левая кнопка мыши": "__mouse_left__", "лкм": "__mouse_left__", "мышь левая": "__mouse_left__",
            "правая кнопка мыши": "__mouse_right__", "пкм": "__mouse_right__", "мышь правая": "__mouse_right__",
            "твёрдый знак": "]", "твердый знак": "]", "твёрдый": "]",
            "мягкий знак": "m", "мягкий": "m",
            "твёрдый и": "s", "твердый и": "s",
        }

        def normalize_key_name_smart(raw_key):
            raw = raw_key.lower().strip()
            if not raw:
                return None

            if raw in SPECIAL_KEYS_MAP:
                return SPECIAL_KEYS_MAP[raw]

            #костыль для распознования букв через первую букву слова
            first_letter = raw[0]

            #Словарь перевода
            ru_to_en_qwerty = {
                'й': 'q', 'ц': 'w', 'у': 'e', 'к': 'r', 'е': 't', 'н': 'y', 'г': 'u', 'ш': 'i', 'щ': 'o', 'з': 'p',
                'х': '[', 'ъ': ']',
                'ф': 'a', 'ы': 's', 'в': 'd', 'а': 'f', 'п': 'g', 'р': 'h', 'о': 'j', 'л': 'k', 'д': 'l', 'ж': ';',
                'э': "'",
                'я': 'z', 'ч': 'x', 'с': 'c', 'м': 'v', 'и': 'b', 'т': 'n', 'ь': 'm', 'б': ',', 'ю': '.',
                "твёрдый знак": "]", "твердый знак": "]", "твёрдый": "]",
                "мягкий знак": "m", "мягкий": "m",
                "твёрдый и": "s", "твердый и": "s",
            }

            #смена языка
            if first_letter in ru_to_en_qwerty:
                first_letter = ru_to_en_qwerty[first_letter]

            #возвращаем символ если есть
            if first_letter.isalnum() or first_letter in "[],.;'":
                return first_letter

            return raw

        def extract_key_name(text):
            parts = text.split()
            return " ".join(parts[1:]) if len(parts) > 1 else ""

        # нажатие кнопки
        if command_text.startswith("нажмите "):
            key_name = extract_key_name(command_text).strip()
            if not key_name:
                self.add_log("Не указана клавиша. Пример: нажмите арбуз")
                return

            mapped = normalize_key_name_smart(key_name)
            self.add_log(f"Распознано '{key_name}' -> символ/клавиша: '{mapped}'")

            # нажатие кнопок мыши
            if mapped == "__mouse_left__":
                pyautogui.click(button='left')
                self.add_log("🖱 Нажата левая кнопка мыши")
                return
            if mapped == "__mouse_right__":
                pyautogui.click(button='right')
                self.add_log("🖱 Нажата правая кнопка мыши")
                return

            # нажатие клавиш
            if mapped:
                try:
                    import keyboard
                    keyboard.press(mapped)
                    keyboard.release(mapped)
                    self.add_log(f"⌨Нажата клавиша: {mapped}")
                except:
                    self.add_log(f"Ошибка нажатия клавиши '{mapped}'")
            return

        # зажатие клавиш
        if command_text.startswith("держи "):
            key_name = extract_key_name(command_text).strip()
            if not key_name:
                self.add_log( "Не указана клавиша. Пример: держи шифт")
                return
            mapped = normalize_key_name_smart(key_name)

            # Зажатие кнопки мыши
            if mapped == "__mouse_left__":
                pyautogui.mouseDown(button='left')
                self.pressed_keys.add("__mouse_left__")
                self.add_log("Левая кнопка мыши зажата")
                return
            if mapped == "__mouse_right__":
                pyautogui.mouseDown(button='right')
                self.pressed_keys.add("__mouse_right__")
                self.add_log("Правая кнопка мыши зажата")
                return

            # Зажатие клавиши
            if mapped:
                if mapped in self.pressed_keys:
                    self.add_log(f"Клавиша {mapped} уже зажата")
                    return
                try:
                    import keyboard
                    keyboard.press(mapped)
                    self.pressed_keys.add(mapped)
                    self.add_log(f"Клавиша '{mapped}' успешно зажата")
                except:
                    self.add_log(f"Ошибка зажатия клавиши '{mapped}'")
            return

        # отжатие клавиш
        if command_text.startswith("отпусти "):
            key_name = extract_key_name(command_text).strip()
            import keyboard

            if not key_name:
                #отпустить все
                for k in list(self.pressed_keys):
                    if k.startswith("__mouse"):
                        btn = 'left' if 'left' in k else 'right'
                        pyautogui.mouseUp(button=btn)
                    else:
                        keyboard.release(k)
                self.pressed_keys.clear()
                self.add_log("Отпущены все клавиши и кнопки мыши")
                return

            mapped = normalize_key_name_smart(key_name)

            # Отжатие кнопки мыши
            if mapped == "__mouse_left__":
                if "__mouse_left__" in self.pressed_keys:
                    pyautogui.mouseUp(button='left')
                    self.pressed_keys.discard("__mouse_left__")
                    self.add_log("Левая кнопка мыши отпущена")
                return
            if mapped == "__mouse_right__":
                if "__mouse_right__" in self.pressed_keys:
                    pyautogui.mouseUp(button='right')
                    self.pressed_keys.discard("__mouse_right__")
                    self.add_log("Правая кнопка мыши отпущена")
                return

            # Отжатие клавиш
            if mapped in self.pressed_keys:
                keyboard.release(mapped)
                self.pressed_keys.discard(mapped)
                self.add_log(f"Клавиша {mapped} отпущена")
            else:
                # на случай если флаги не сработают
                try:
                    keyboard.release(mapped)
                    self.add_log(f"Отправлен принудительный сигнал отжатия для: {mapped}")
                except:
                    self.add_log(f"Клавиша {mapped} не была зажата")
            return

         # колесико мышы

        if command_text in ["вверх", "прокрути вверх", "скролл вверх", "колесо вверх"]:
            try:

                pyautogui.scroll(300)
                self.add_log("Прокрутка колесика вверх")
            except:
                self.add_log(f"Ошибка прокрутки")
            return

        if command_text in ["вниз", "прокрути вниз", "скролл вниз", "колесо вниз"]:
            try:

                pyautogui.scroll(-300)
                self.add_log(" Прокрутка колесика вниз")
            except:
                self.add_log(f"Ошибка прокрутки")
            return

       #перемещаем курсор
        if command_text.startswith("курсор "):
            parts = command_text.split()
            if len(parts) >= 3:
                direction = parts[1]
                dist_str = parts[2]


                word_to_num = {
                    "десять": 10, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
                    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500,
                    "тысяча": 1000, "сотня":100
                }

                dist_str_lower = dist_str.lower()
                distance = word_to_num.get(dist_str_lower)

                # на случай если в словаре нет числа
                if distance is None:
                    try:
                        distance = int(dist_str)
                    except:
                        self.add_log(
                            f"Не удалось распознать число: '{dist_str}'. Скажите цифру (например, 'курсор вправо 100').")
                        return

                dx, dy = 0, 0
                if direction in ["влево", "налево", "лево"]:
                    dx = -distance
                elif direction in ["вправо", "направо", "право"]:
                    dx = distance
                elif direction in ["вверх", "наверх"]:
                    dy = -distance
                elif direction in ["вниз", "наниз"]:
                    dy = distance
                else:
                    self.add_log(f"Неизвестное направление: '{direction}'. Используйте: влево, вправо, вверх, вниз.")
                    return

                try:

                    pyautogui.move(dx, dy, duration=0.2)# duration отвечает за плавность камеры. чем выше тем плавнее
                    self.add_log(f"Курсор сдвинут: {direction} на {distance} пикселей")
                except Exception as e:
                    self.add_log(f"Ошибка перемещения курсора: {e}")
                return
            else:
                self.add_log("Неверный формат команды. Пример: 'курсор вправо 100' или 'курсор вверх 50'")
                return

        if command_text.startswith("камера "):
            parts = command_text.split()
            if len(parts) >= 3:
                direction = parts[1]
                dist_str = parts[2]

                # Словарь чисел прописью (можно расширить)
                word_to_num = { "десять": 10, "двадцать": 20, "пятьдесят": 50, "сто": 100, "двести": 200}
                distance = word_to_num.get(dist_str.lower())

                if distance is None:
                    try:
                        distance = int(dist_str)
                    except ValueError:
                        self.add_log(f" Не удалось распознать число: '{dist_str}'.")
                        return

                dx, dy = 0, 0
                if direction in ["влево", "налево"]:
                    dx = -distance
                elif direction in ["вправо", "направо"]:
                    dx = distance
                elif direction in ["вверх", "наверх"]:
                    dy = -distance  # В сырых данных мыши отрицательный Y = вверх
                elif direction in ["вниз", "наниз"]:
                    dy = distance  # Положительный Y = вниз
                else:
                    self.add_log(f"Неизвестное направление: '{direction}'.")
                    return

            else:
                self.add_log("Неверный формат. Пример: 'камера вправо 100' или 'камера вверх 50'")
                return

        # если команда не найдена
        self.add_log(f"Неизвестная команда: '{command_text}'")

    def _exit_remember_mode(self):
        self.remembering_mode = False
        if self.remember_timeout:
            self.root.after_cancel(self.remember_timeout)
            self.remember_timeout = None

        # переключения назад на русский
        if self.original_recognizer is not None:
            self.active_recognizer = self.original_recognizer
            self.original_recognizer = None
            self.add_log("Модель переключена обратно на русский язык")

        # НОВЫЙ ФУНКЦИОНАЛ: Сохранение в файл
        if self.stored_text.strip():
            try:
                save_path = Path(__file__).parent / "remembered_texts.txt"
                with open(save_path, "a", encoding="utf-8") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"\n--- [{timestamp}] ---\n")
                    f.write(self.stored_text + "\n")
                self.add_log(f"Текст также сохранён в файл: {save_path}")
            except Exception as e:
                self.add_log(f"Ошибка сохранения текста в файл: {e}")

        self.add_log("Режим запоминания текста выключен.")

def main():
    root = tk.Tk()
    app = VoiceAssistantApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()


