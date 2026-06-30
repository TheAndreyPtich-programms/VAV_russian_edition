
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from pathlib import Path

class SettingsWindow:
    def __init__(self, parent, config_file, on_save_callback):
        self.parent = parent
        self.config_file = Path(config_file)
        self.on_save = on_save_callback
        self.full_config = self._load_full_config()

        self.window = tk.Toplevel(parent)
        self.window.title("Настройки помощника")
        self.window.geometry("800x600")
        self.window.transient(parent)
        self.window.grab_set()

        # Создаём вкладки
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Вкладка "Приложения"
        self.apps_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.apps_frame, text="Приложения")
        self._create_apps_tab()

        # Вкладка "Текстовые команды"
        self.text_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.text_frame, text="Текстовые команды")
        self._create_text_commands_tab()

        # Кнопка "Сохранить всё и закрыть"
        bottom_frame = ttk.Frame(self.window)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        ttk.Button(bottom_frame, text="Сохранить всё и закрыть", command=self._close_and_save).pack(side=tk.RIGHT)

    def _load_full_config(self):
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # конфиг база
            default = {
                "wake_word": "компьютер",
                "commands": {
                    "open_apps": {
                        "Блокнот": {"phrases": ["блокнот", "notepad"], "path": "notepad.exe"},
                        "Калькулятор": {"phrases": ["калькулятор", "calc"], "path": "calc.exe"}
                    }
                },
                "text_commands": {
                    "copy_paste": ["скопируй", "копировать", "скопировать", "скопируй и вставь"],
                    "paste": ["вставь", "вставить", "вклей"],
                    "cut_paste": ["вырежи", "вырезать"],
                    "remember_text": ["запомни", "запомнить текст", "запомни это"],
                    "insert_remembered": ["вставь запомненное", "вставь сохранённое", "скажи запомненное"]
                }
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4, ensure_ascii=False)
            return default

    def _save_full_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.full_config, f, indent=4, ensure_ascii=False)
        if self.on_save:
            self.on_save()

    def _create_apps_tab(self):
        # Левая часть: список приложений
        left_frame = ttk.Frame(self.apps_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(left_frame, text="Приложения:").pack(anchor=tk.W)
        self.app_listbox = tk.Listbox(left_frame, height=15)
        self.app_listbox.pack(fill=tk.BOTH, expand=True)
        self.app_listbox.bind('<<ListboxSelect>>', self._on_select_app)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Добавить приложение", command=self._add_app).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить приложение", command=self._delete_app).pack(side=tk.LEFT, padx=2)

        #правая часть для редактирование
        right_frame = ttk.Frame(self.apps_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(right_frame, text="Путь к программе или файлу:").pack(anchor=tk.W)
        path_frame = ttk.Frame(right_frame)
        path_frame.pack(fill=tk.X, pady=2)
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=50)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Обзор...", command=self._browse_and_set).pack(side=tk.LEFT, padx=(5,0))

        ttk.Label(right_frame, text="Фразы (по одной на строку):").pack(anchor=tk.W, pady=(10,0))
        self.phrases_text = tk.Text(right_frame, height=10, width=50)
        self.phrases_text.pack(fill=tk.BOTH, expand=True, pady=2)

        ttk.Button(right_frame, text="Сохранить изменения для приложения", command=self._save_current_app).pack(pady=5)

        #загружаем данные приложений
        self.apps_data = self.full_config.get("commands", {}).get("open_apps", {})
        self._refresh_app_list()
        self.current_app = None

    def _refresh_app_list(self):
        self.app_listbox.delete(0, tk.END)
        for app_name in sorted(self.apps_data.keys()):
            self.app_listbox.insert(tk.END, app_name)

    def _on_select_app(self, event):
        selection = self.app_listbox.curselection()
        if not selection:
            return
        app_name = self.app_listbox.get(selection[0])
        app_info = self.apps_data.get(app_name, {})
        self.path_var.set(app_info.get("path", ""))
        self.phrases_text.delete(1.0, tk.END)
        phrases = app_info.get("phrases", [])
        self.phrases_text.insert(tk.END, "\n".join(phrases))
        self.current_app = app_name

    def _save_current_app(self):
        if not self.current_app:
            messagebox.showwarning("Предупреждение", "Сначала выберите приложение")
            return
        new_path = self.path_var.get().strip()
        phrases_raw = self.phrases_text.get(1.0, tk.END).strip()
        phrases_list = [p.strip() for p in phrases_raw.splitlines() if p.strip()]
        if not new_path or not phrases_list:
            messagebox.showerror("Ошибка", "Путь и фразы не могут быть пустыми")
            return
        self.apps_data[self.current_app]["path"] = new_path
        self.apps_data[self.current_app]["phrases"] = phrases_list
        self.full_config.setdefault("commands", {}).setdefault("open_apps", {})
        self.full_config["commands"]["open_apps"] = self.apps_data
        self._save_full_config()
        messagebox.showinfo("Успех", f"Приложение '{self.current_app}' обновлено")

    def _add_app(self):
        dialog = tk.Toplevel(self.window)
        dialog.title("Новое приложение")
        dialog.geometry("450x300")
        dialog.transient(self.window)
        dialog.grab_set()

        ttk.Label(dialog, text="Название приложения:").pack(pady=5)
        name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=name_var, width=40).pack(pady=5)

        ttk.Label(dialog, text="Путь к файлу:").pack(pady=5)
        path_frame = ttk.Frame(dialog)
        path_frame.pack(pady=5, fill=tk.X, padx=20)
        path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=path_var, width=35)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Обзор...", command=lambda: self._browse_and_set_dialog(path_var)).pack(side=tk.LEFT, padx=5)

        ttk.Label(dialog, text="Фразы (через запятую):").pack(pady=5)
        phrases_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=phrases_var, width=40).pack(pady=5)

        def do_add():
            name = name_var.get().strip()
            path = path_var.get().strip()
            phrases_str = phrases_var.get().strip()
            if not name or not path or not phrases_str:
                messagebox.showerror("Ошибка", "Заполните все поля")
                return
            phrases = [p.strip() for p in phrases_str.split(",") if p.strip()]
            if name in self.apps_data:
                messagebox.showerror("Ошибка", "Такое приложение уже есть")
                return
            self.apps_data[name] = {"phrases": phrases, "path": path}
            self.full_config["commands"]["open_apps"] = self.apps_data
            self._save_full_config()
            self._refresh_app_list()
            dialog.destroy()
            messagebox.showinfo("Успех", f"Приложение '{name}' добавлено")

        ttk.Button(dialog, text="Добавить", command=do_add).pack(pady=20)

    def _delete_app(self):
        selection = self.app_listbox.curselection()
        if not selection:
            return
        app_name = self.app_listbox.get(selection[0])
        if messagebox.askyesno("Подтверждение", f"Удалить '{app_name}'?"):
            del self.apps_data[app_name]
            self.full_config["commands"]["open_apps"] = self.apps_data
            self._save_full_config()
            self._refresh_app_list()
            self.path_var.set("")
            self.phrases_text.delete(1.0, tk.END)
            self.current_app = None

    def _browse_and_set(self):
        path = filedialog.askopenfilename(title="Выберите программу или файл")
        if path:
            self.path_var.set(path)

    def _browse_and_set_dialog(self, string_var):
        path = filedialog.askopenfilename(title="Выберите программу или файл")
        if path:
            string_var.set(path)

    def _create_text_commands_tab(self):
        frame = self.text_frame
        text_cmds = self.full_config.get("text_commands", {})
        self.text_vars = {}

        row = 0
        for key in ["copy_paste", "paste", "cut_paste", "remember_text", "insert_remembered"]:
            ttk.Label(frame, text=f"{key} (фразы через запятую):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
            current = ", ".join(text_cmds.get(key, []))
            var = tk.StringVar(value=current)
            entry = ttk.Entry(frame, textvariable=var, width=60)
            entry.grid(row=row, column=1, padx=5, pady=5, sticky=tk.W)
            self.text_vars[key] = var
            row += 1

        ttk.Button(frame, text="Сохранить текстовые команды", command=self._save_text_commands).grid(row=row, column=0, columnspan=2, pady=15)

    def _save_text_commands(self):
        new_cmds = {}
        for key, var in self.text_vars.items():
            raw = var.get().strip()
            if raw:
                phrases = [p.strip() for p in raw.split(",") if p.strip()]
                new_cmds[key] = phrases
            else:
                new_cmds[key] = []
        self.full_config["text_commands"] = new_cmds
        self._save_full_config()
        messagebox.showinfo("Успех", "Текстовые команды сохранены")


    def _close_and_save(self):
        self._save_full_config()
        self.window.destroy()


