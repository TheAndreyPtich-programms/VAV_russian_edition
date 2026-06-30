import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import cv2
from pathlib import Path
from vision.hand_tracker import HandTracker
from vision.gesture_matcher import normalize_landmarks


class GestureWindow:
    def __init__(self, parent, config_file, tracker):
        self.parent = parent
        self.config_file = Path(config_file)
        self.tracker = tracker
        self.config = self._load_config()

        self.window = tk.Toplevel(parent)
        self.window.title("Настройка жестов")
        self.window.geometry("900x600")
        self.window.transient(parent)
        self.window.grab_set()

        self._create_ui()
        self._update_video_feed()

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_config(self):
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"gestures": {}}

    def _create_ui(self):
        # Левая панель
        left = ttk.Frame(self.window, width=250)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        ttk.Label(left, text="Сохранённые жесты:").pack(anchor=tk.W)

        self.listbox = tk.Listbox(left, height=15)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self._refresh_list()
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Правая панель
        right = ttk.Frame(self.window)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Label(right, bg="black", width=640, height=480)
        self.canvas.pack(pady=5)

        ctrl_frame = ttk.Frame(right)
        ctrl_frame.pack(fill=tk.X, pady=5)

        ttk.Label(ctrl_frame, text="Действие:").pack(side=tk.LEFT, padx=5)
        self.action_var = tk.StringVar(value="left_click")
        actions = ["left_click", "hold_left", "hold_right", "release", "scroll_up", "scroll_down"]
        ttk.Combobox(ctrl_frame, textvariable=self.action_var, values=actions, state="readonly", width=15).pack(
            side=tk.LEFT, padx=5)

        self.name_var = tk.StringVar()
        ttk.Entry(ctrl_frame, textvariable=self.name_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Button(ctrl_frame, text="Записать текущий жест", command=self._record_gesture).pack(side=tk.LEFT, padx=10)
        ttk.Button(ctrl_frame, text="Удалить", command=self._delete_gesture).pack(side=tk.RIGHT, padx=5)
        ttk.Button(ctrl_frame, text="Сохранить всё", command=self._save_config).pack(side=tk.RIGHT)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for name in sorted(self.config.get("gestures", {}).keys()):
            self.listbox.insert(tk.END, name)

    def _update_video_feed(self):
        frame = self.tracker.get_frame()
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from PIL import Image, ImageTk
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.canvas.imgtk = imgtk
            self.canvas.configure(image=imgtk)
        self.window.after(30, self._update_video_feed)

    def _record_gesture(self):
        landmarks = self.tracker.get_landmarks()
        frame = self.tracker.get_frame()

        if not landmarks or frame is None:
            messagebox.showwarning("Внимание", "Рука не найдена в кадре!")
            return

        norm = normalize_landmarks(landmarks)
        if norm is None:
            messagebox.showwarning("Внимание", "Покажите руку полностью.")
            return

        name = self.name_var.get().strip()
        action = self.action_var.get()
        if not name:
            messagebox.showerror("Ошибка", "Введите название жеста")
            return

        # Сохраняем фото жеста
        preview_dir = Path(__file__).parent.parent / "gesture_previews"
        preview_dir.mkdir(exist_ok=True)
        preview_path = preview_dir / f"{name}.jpg"
        cv2.imwrite(str(preview_path), frame)

        self.config.setdefault("gestures", {})[name] = {
            "coords": norm,
            "action": action,
            "preview": str(preview_path)
        }
        self._save_config()
        self._refresh_list()
        messagebox.showinfo("Успех", f"Жест '{name}' сохранён!\nФото: {preview_path}")

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        name = self.listbox.get(sel[0])
        self.name_var.set(name)
        self.action_var.set(self.config["gestures"][name]["action"])

    def _on_close(self):
        # включаем управление мыши с камеры
        self.parent.gesture_window_open = False
        self.window.destroy()

    def _delete_gesture(self):
        sel = self.listbox.curselection()
        if not sel: return
        name = self.listbox.get(sel[0])
        if messagebox.askyesno("Подтверждение", f"Удалить жест '{name}'?"):
            del self.config["gestures"][name]
            self._save_config()
            self._refresh_list()
            self.name_var.set("")

    def _save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
        messagebox.showinfo("Сохранено", "Настройки жестов обновлены")