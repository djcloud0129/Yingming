from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from dataclasses import replace
from math import ceil
from pathlib import Path
from typing import Any

from yingming_core.service import YingmingService
from yingming_core.settings import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL


FULL_WINDOW_GEOMETRY = "340x600+920+160"
FULL_WINDOW_SIZE = "340x600"
FULL_WINDOW_MIN_SIZE = (340, 600)
COLLAPSED_WINDOW_GEOMETRY = "220x340"
COLLAPSED_WINDOW_MIN_SIZE = (220, 340)
PORTRAIT_MAX_SIZE = 180


class YingmingPetApp:
    def __init__(self, project_root: Path, topmost: bool = True):
        self.project_root = project_root
        self.service = YingmingService(project_root)
        self.topmost = topmost
        self.response_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.is_waiting = False
        self.is_collapsed = False
        self.drag_start_x = 0
        self.drag_start_y = 0

        self.root = tk.Tk()
        self.root.title("樱茗")
        self.root.geometry(FULL_WINDOW_GEOMETRY)
        self.root.minsize(*FULL_WINDOW_MIN_SIZE)
        self.root.configure(bg="#f7f1e8")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", self.topmost)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="展开聊天", command=self.restore_full_window)
        self.menu.add_command(label="打开记忆体", command=self.ask_memory)
        self.menu.add_command(label="连接 DeepSeek", command=self.open_connection_settings)
        self.menu.add_command(label="编辑用户画像", command=self.open_profile_editor)
        self.menu.add_command(label="切换置顶", command=self.toggle_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="退出樱茗", command=self.quit)

        self.build_ui()
        self.root.bind("<Escape>", lambda _event: self.quit())
        self.root.bind("<Button-3>", self.show_menu)
        self.root.after(120, self.poll_response_queue)

    def build_ui(self) -> None:
        shell = tk.Frame(self.root, bg="#f7f1e8", padx=12, pady=12)
        shell.pack(fill="both", expand=True)
        shell.bind("<ButtonPress-1>", self.start_drag)
        shell.bind("<B1-Motion>", self.drag)

        header = tk.Frame(shell, bg="#f7f1e8")
        header.pack(fill="x")
        header.bind("<ButtonPress-1>", self.start_drag)
        header.bind("<B1-Motion>", self.drag)

        title = tk.Label(
            header,
            text="樱茗",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 20, "bold"),
        )
        title.pack(side="left")

        self.mode_label = tk.Label(
            header,
            text=self.model_label_text(),
            bg="#f7f1e8",
            fg="#6f7f56",
            font=("Microsoft YaHei UI", 9),
        )
        self.mode_label.pack(side="right", pady=(8, 0))

        self.image_label = tk.Label(shell, bg="#f7f1e8", bd=0)
        self.image_label.pack(pady=(8, 8))
        self.image_label.bind("<ButtonPress-1>", self.start_drag)
        self.image_label.bind("<B1-Motion>", self.drag)
        self.image_label.bind("<Double-Button-1>", lambda _event: self.restore_full_window())
        self.load_portrait()

        self.compact_actions = tk.Frame(shell, bg="#f7f1e8")
        tk.Button(
            self.compact_actions,
            text="展开",
            command=self.restore_full_window,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            self.compact_actions,
            text="退出",
            command=self.quit,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="right", fill="x", expand=True, padx=(8, 0))

        self.bubble_frame = tk.Frame(shell, bg="#f7f1e8")
        self.bubble_frame.pack(fill="x", pady=(2, 10))

        self.bubble_scrollbar = tk.Scrollbar(self.bubble_frame, orient="vertical")
        self.bubble = tk.Text(
            self.bubble_frame,
            height=7,
            width=1,
            wrap="word",
            bg="#fff8f6",
            fg="#2d3230",
            insertbackground="#2d3230",
            relief="solid",
            bd=1,
            padx=12,
            pady=10,
            font=("Microsoft YaHei UI", 10),
            yscrollcommand=self.bubble_scrollbar.set,
        )
        self.bubble_scrollbar.configure(command=self.bubble.yview)
        self.bubble_scrollbar.pack(side="right", fill="y")
        self.bubble.pack(side="left", fill="both", expand=True)
        self.set_bubble("晚上好。我在这里。你可以慢慢说。")

        self.input_frame = tk.Frame(shell, bg="#f7f1e8")
        self.input_frame.pack(fill="x")

        self.input_var = tk.StringVar()
        self.input_box = tk.Entry(
            self.input_frame,
            textvariable=self.input_var,
            bg="#fffaf2",
            fg="#2d3230",
            insertbackground="#2d3230",
            relief="solid",
            bd=1,
            font=("Microsoft YaHei UI", 10),
        )
        self.input_box.pack(side="left", fill="x", expand=True, ipady=8)
        self.input_box.bind("<Return>", lambda _event: self.send_message())

        self.send_button = tk.Button(
            self.input_frame,
            text="发送",
            command=self.send_message,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.send_button.pack(side="right", padx=(8, 0))

        self.actions = tk.Frame(shell, bg="#f7f1e8")
        self.actions.pack(fill="x", pady=(10, 0))

        tk.Button(
            self.actions,
            text="记忆体",
            command=self.ask_memory,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=10,
            pady=5,
        ).pack(side="left")

        tk.Button(
            self.actions,
            text="画像",
            command=self.open_profile_editor,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=10,
            pady=5,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            self.actions,
            text="连接",
            command=self.open_connection_settings,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=10,
            pady=5,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            self.actions,
            text="收起",
            command=self.minimize_to_small_pet,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=10,
            pady=5,
        ).pack(side="right")

    def load_portrait(self) -> None:
        image_path = self.project_root / "web" / "assets" / "yingming-portrait.png"
        try:
            raw = tk.PhotoImage(file=str(image_path))
            largest_side = max(raw.width(), raw.height())
            factor = max(1, ceil(largest_side / PORTRAIT_MAX_SIZE))
            self.portrait = raw.subsample(factor, factor)
            self.image_label.configure(image=self.portrait)
            try:
                self.root.iconphoto(True, self.portrait)
            except tk.TclError:
                pass
        except tk.TclError:
            self.image_label.configure(
                text="樱茗",
                fg="#cf8792",
                font=("Microsoft YaHei UI", 32, "bold"),
                width=9,
                height=5,
            )

    def model_label_text(self) -> str:
        state = self.service.state()
        model = state.get("model", {})
        return str(model.get("name") or "离线模式")

    def refresh_mode_label(self) -> None:
        self.mode_label.configure(text=self.model_label_text())

    def send_message(self) -> None:
        text = self.input_var.get().strip()
        if not text or self.is_waiting:
            return

        self.is_waiting = True
        self.input_var.set("")
        self.set_busy(True)
        self.set_bubble("我在想。")

        worker = threading.Thread(target=self.reply_worker, args=(text,), daemon=True)
        worker.start()

    def reply_worker(self, text: str) -> None:
        try:
            result = self.service.reply(text)
            self.response_queue.put(
                {
                    "ok": True,
                    "reply": result["reply"],
                    "memories_added": result.get("memories_added", []),
                }
            )
        except Exception as exc:  # noqa: BLE001 - show local prototype errors in UI.
            self.response_queue.put({"ok": False, "reply": str(exc)})

    def poll_response_queue(self) -> None:
        try:
            result = self.response_queue.get_nowait()
        except queue.Empty:
            self.root.after(120, self.poll_response_queue)
            return

        self.is_waiting = False
        self.set_busy(False)
        if result["ok"]:
            reply = result["reply"]
            memories_added = result.get("memories_added", [])
            if memories_added:
                reply = f"{reply}\n\n（我整理了 {len(memories_added)} 条新的长期记忆。）"
            self.set_bubble(reply)
        else:
            self.set_bubble(f"这里暂时没有接好：{result['reply']}")
        self.refresh_mode_label()

        self.root.after(120, self.poll_response_queue)

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.input_box.configure(state=state)
        if not busy:
            self.input_box.focus_set()

    def ask_memory(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("记忆体")
        window.geometry("520x520+760+180")
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        tk.Label(
            window,
            text="记忆体",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        memory_frame = tk.Frame(window, bg="#f7f1e8")
        memory_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        memory_scrollbar = tk.Scrollbar(memory_frame, orient="vertical")
        memory_view = tk.Text(
            memory_frame,
            height=12,
            wrap="word",
            bg="#fff8f6",
            fg="#2d3230",
            relief="solid",
            bd=1,
            padx=10,
            pady=10,
            font=("Microsoft YaHei UI", 10),
            yscrollcommand=memory_scrollbar.set,
        )
        memory_scrollbar.configure(command=memory_view.yview)
        memory_scrollbar.pack(side="right", fill="y")
        memory_view.pack(side="left", fill="both", expand=True)

        tk.Label(
            window,
            text="写入新记忆",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(0, 6))

        editor = tk.Text(
            window,
            height=5,
            wrap="word",
            bg="#fffaf2",
            fg="#2d3230",
            insertbackground="#2d3230",
            relief="solid",
            bd=1,
            padx=10,
            pady=10,
            font=("Microsoft YaHei UI", 10),
        )
        editor.pack(fill="x", padx=12, pady=(0, 10))

        buttons = tk.Frame(window, bg="#f7f1e8")
        buttons.pack(fill="x", padx=12, pady=(0, 12))

        def render() -> None:
            memory_view.configure(state="normal")
            memory_view.delete("1.0", "end")
            memory_view.insert("1.0", self.service.memory.as_readable_text())
            memory_view.configure(state="disabled")
            memory_view.yview_moveto(0.0)

        def save() -> None:
            text = editor.get("1.0", "end-1c").strip()
            if not text:
                messagebox.showwarning("樱茗", "记忆内容不能为空。", parent=window)
                return
            try:
                self.service.remember(text, category="manual")
            except ValueError as exc:
                messagebox.showwarning("樱茗", str(exc), parent=window)
                return
            self.set_bubble("好，我记住了。")
            editor.delete("1.0", "end")
            render()

        tk.Button(
            buttons,
            text="关闭",
            command=window.destroy,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="right")
        tk.Button(
            buttons,
            text="刷新",
            command=render,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons,
            text="保存记忆",
            command=save,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="right", padx=(0, 8))

        render()
        editor.focus_set()

    def open_connection_settings(self) -> None:
        settings = self.service.client.settings
        if not settings.is_deepseek:
            settings = self.service.deepseek_defaults(api_key=settings.api_key)

        window = tk.Toplevel(self.root)
        window.title("连接 DeepSeek")
        window.geometry("500x410+780+200")
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        form = tk.Frame(window, bg="#f7f1e8", padx=12, pady=12)
        form.pack(fill="both", expand=True)

        tk.Label(
            form,
            text="连接 DeepSeek",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        def add_entry(label: str, value: str, show: str | None = None) -> tk.Entry:
            tk.Label(
                form,
                text=label,
                bg="#f7f1e8",
                fg="#2d3230",
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(anchor="w", pady=(8, 4))
            entry = tk.Entry(
                form,
                bg="#fffaf2",
                fg="#2d3230",
                insertbackground="#2d3230",
                relief="solid",
                bd=1,
                font=("Microsoft YaHei UI", 10),
                show=show,
            )
            entry.insert(0, value)
            entry.pack(fill="x", ipady=7)
            return entry

        api_key_entry = add_entry("API Key", settings.api_key, show="*")
        base_url_entry = add_entry("Base URL", settings.base_url or DEFAULT_DEEPSEEK_BASE_URL)
        model_entry = add_entry("模型", settings.model or DEFAULT_DEEPSEEK_MODEL)
        temperature_entry = add_entry("温度", str(settings.temperature))

        auto_memory_var = tk.BooleanVar(value=settings.auto_memory)
        tk.Checkbutton(
            form,
            text="自动整理长期记忆",
            variable=auto_memory_var,
            bg="#f7f1e8",
            fg="#2d3230",
            activebackground="#f7f1e8",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(10, 0))

        thinking_var = tk.BooleanVar(value=settings.deepseek_thinking == "enabled")
        tk.Checkbutton(
            form,
            text="启用 DeepSeek 思考模式",
            variable=thinking_var,
            bg="#f7f1e8",
            fg="#2d3230",
            activebackground="#f7f1e8",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        buttons = tk.Frame(form, bg="#f7f1e8")
        buttons.pack(fill="x", pady=(16, 0))

        def fill_deepseek_defaults() -> None:
            base_url_entry.delete(0, "end")
            base_url_entry.insert(0, DEFAULT_DEEPSEEK_BASE_URL)
            model_entry.delete(0, "end")
            model_entry.insert(0, DEFAULT_DEEPSEEK_MODEL)

        def save() -> None:
            try:
                temperature = float(temperature_entry.get().strip() or "0.8")
            except ValueError:
                messagebox.showwarning("樱茗", "温度需要是数字，例如 0.8。", parent=window)
                return

            new_settings = replace(
                settings,
                provider="deepseek",
                api_key=api_key_entry.get().strip(),
                base_url=base_url_entry.get().strip().rstrip("/") or DEFAULT_DEEPSEEK_BASE_URL,
                model=model_entry.get().strip() or DEFAULT_DEEPSEEK_MODEL,
                temperature=temperature,
                auto_memory=auto_memory_var.get(),
                deepseek_thinking="enabled" if thinking_var.get() else "disabled",
            )
            self.service.save_model_settings(new_settings)
            self.refresh_mode_label()
            self.set_bubble("DeepSeek 已保存。你可以直接和我说话，我会带着记忆体一起回应。")
            window.destroy()

        tk.Button(
            buttons,
            text="DeepSeek 默认",
            command=fill_deepseek_defaults,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left")
        tk.Button(
            buttons,
            text="关闭",
            command=window.destroy,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="right")
        tk.Button(
            buttons,
            text="保存连接",
            command=save,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="right", padx=(0, 8))

        api_key_entry.focus_set()

    def open_profile_editor(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("用户画像")
        window.geometry("560x500+760+180")
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        editor = tk.Text(
            window,
            wrap="word",
            bg="#fffaf2",
            fg="#2d3230",
            insertbackground="#2d3230",
            relief="solid",
            bd=1,
            padx=10,
            pady=10,
            font=("Microsoft YaHei UI", 10),
        )
        editor.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        editor.insert("1.0", self.service.read_profile())

        def save() -> None:
            self.service.save_profile(editor.get("1.0", "end-1c"))
            self.set_bubble("画像已经保存。这样我会更稳地记住你确认过的部分。")
            window.destroy()

        tk.Button(
            window,
            text="保存画像",
            command=save,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="e", padx=12, pady=(0, 12))

    def minimize_to_small_pet(self) -> None:
        self.is_collapsed = True
        self.input_frame.pack_forget()
        self.actions.pack_forget()
        self.bubble_frame.pack_forget()
        if not self.compact_actions.winfo_ismapped():
            self.compact_actions.pack(fill="x", pady=(6, 0))
        self.root.minsize(*COLLAPSED_WINDOW_MIN_SIZE)
        self.root.geometry(COLLAPSED_WINDOW_GEOMETRY)

    def restore_full_window(self) -> None:
        if not self.is_collapsed and self.input_frame.winfo_ismapped():
            return
        self.is_collapsed = False
        self.compact_actions.pack_forget()
        self.root.minsize(*FULL_WINDOW_MIN_SIZE)
        self.root.geometry(FULL_WINDOW_SIZE)
        if not self.bubble_frame.winfo_ismapped():
            self.bubble_frame.pack(fill="x", pady=(2, 10))
        if not self.input_frame.winfo_ismapped():
            self.input_frame.pack(fill="x")
        if not self.actions.winfo_ismapped():
            self.actions.pack(fill="x", pady=(10, 0))
        self.bubble.configure(height=7)
        self.set_bubble("我回来啦。")
        self.input_box.focus_set()

    def toggle_topmost(self) -> None:
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        self.set_bubble("我会继续待在最前面。" if self.topmost else "好，我先不挡着你。")

    def set_bubble(self, text: str) -> None:
        self.bubble.configure(state="normal")
        self.bubble.delete("1.0", "end")
        self.bubble.insert("1.0", text.strip())
        self.bubble.configure(state="disabled")
        self.bubble.yview_moveto(0.0)

    def show_menu(self, event: tk.Event[Any]) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def start_drag(self, event: tk.Event[Any]) -> None:
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def drag(self, event: tk.Event[Any]) -> None:
        x = self.root.winfo_x() + event.x - self.drag_start_x
        y = self.root.winfo_y() + event.y - self.drag_start_y
        self.root.geometry(f"+{x}+{y}")

    def quit(self) -> None:
        self.root.destroy()

    def run(self) -> None:
        self.input_box.focus_set()
        self.root.mainloop()


def run_pet(project_root: Path, topmost: bool = True) -> None:
    YingmingPetApp(project_root, topmost=topmost).run()
