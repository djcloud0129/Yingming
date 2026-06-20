from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from dataclasses import replace
from math import ceil
from pathlib import Path
from typing import Any

from yingming_core.memory import MEMORY_CATEGORIES
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
        self.is_profile_refreshing = False
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
                    "memory_suggestions": result.get("memory_suggestions", []),
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

        if result.get("type") == "profile_refresh":
            self.is_profile_refreshing = False
            if result.get("ok") and result.get("updated"):
                self.set_bubble("画像已经自动更新。这样我会更稳地理解你。")
            elif not result.get("ok"):
                self.set_bubble(f"画像自动更新暂时失败：{result.get('error', '')}")
            self.root.after(120, self.poll_response_queue)
            return

        self.is_waiting = False
        self.set_busy(False)
        if result["ok"]:
            reply = result["reply"]
            memories_added = result.get("memories_added", [])
            memory_suggestions = result.get("memory_suggestions", [])
            if memories_added:
                reply = f"{reply}\n\n（我整理了 {len(memories_added)} 条新的长期记忆。）"
            if memory_suggestions:
                reply = f"{reply}\n\n（我整理了 {len(memory_suggestions)} 条待确认记忆，点“记忆体”确认。）"
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

    def start_profile_refresh(self, reason: str) -> None:
        if not self.service.client.settings.auto_profile or self.is_profile_refreshing:
            return
        self.is_profile_refreshing = True
        threading.Thread(target=self.profile_refresh_worker, args=(reason,), daemon=True).start()

    def profile_refresh_worker(self, reason: str) -> None:
        try:
            result = self.service.auto_refresh_profile(reason)
            self.response_queue.put(
                {
                    "type": "profile_refresh",
                    "ok": True,
                    "updated": result.get("updated", False),
                }
            )
        except Exception as exc:  # noqa: BLE001 - show prototype errors.
            self.response_queue.put({"type": "profile_refresh", "ok": False, "error": str(exc)})

    def ask_memory(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("记忆体管理器")
        window.geometry("760x620+620+80")
        window.minsize(720, 560)
        window.resizable(True, True)
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        state: dict[str, Any] = {
            "kind": "",
            "id": "",
            "pending": [],
            "memories": [],
        }

        shell = tk.Frame(window, bg="#f7f1e8", padx=12, pady=12)
        shell.pack(fill="both", expand=True)
        shell.rowconfigure(1, weight=1)
        shell.columnconfigure(0, weight=1)

        header = tk.Frame(shell, bg="#f7f1e8")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text="记忆体",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        count_label = tk.Label(
            header,
            text="",
            bg="#f7f1e8",
            fg="#6f7f56",
            font=("Microsoft YaHei UI", 10),
        )
        count_label.grid(row=0, column=1, sticky="e")

        body = tk.Frame(shell, bg="#f7f1e8")
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)

        lists = tk.Frame(body, bg="#f7f1e8")
        lists.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        lists.rowconfigure(1, weight=1)
        lists.rowconfigure(3, weight=2)
        lists.columnconfigure(0, weight=1)

        tk.Label(
            lists,
            text="待确认",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        pending_frame = tk.Frame(lists, bg="#f7f1e8")
        pending_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        pending_frame.rowconfigure(0, weight=1)
        pending_frame.columnconfigure(0, weight=1)

        pending_scrollbar = tk.Scrollbar(pending_frame, orient="vertical")
        pending_list = tk.Listbox(
            pending_frame,
            height=7,
            bg="#fff8f6",
            fg="#2d3230",
            relief="solid",
            bd=1,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            yscrollcommand=pending_scrollbar.set,
        )
        pending_scrollbar.configure(command=pending_list.yview)
        pending_list.grid(row=0, column=0, sticky="nsew")
        pending_scrollbar.grid(row=0, column=1, sticky="ns")

        tk.Label(
            lists,
            text="长期记忆",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))

        memory_frame = tk.Frame(lists, bg="#f7f1e8")
        memory_frame.grid(row=3, column=0, sticky="nsew")
        memory_frame.rowconfigure(0, weight=1)
        memory_frame.columnconfigure(0, weight=1)

        memory_scrollbar = tk.Scrollbar(memory_frame, orient="vertical")
        memory_list = tk.Listbox(
            memory_frame,
            height=13,
            bg="#fff8f6",
            fg="#2d3230",
            relief="solid",
            bd=1,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            yscrollcommand=memory_scrollbar.set,
        )
        memory_scrollbar.configure(command=memory_list.yview)
        memory_list.grid(row=0, column=0, sticky="nsew")
        memory_scrollbar.grid(row=0, column=1, sticky="ns")

        editor_panel = tk.Frame(body, bg="#f7f1e8")
        editor_panel.grid(row=0, column=1, sticky="nsew")
        editor_panel.rowconfigure(3, weight=1)
        editor_panel.columnconfigure(0, weight=1)

        selection_label = tk.Label(
            editor_panel,
            text="新记忆",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        selection_label.grid(row=0, column=0, sticky="w", pady=(0, 6))

        category_var = tk.StringVar(value="manual")
        category_menu = tk.OptionMenu(editor_panel, category_var, *MEMORY_CATEGORIES)
        category_menu.configure(
            bg="#fffaf2",
            fg="#2d3230",
            activebackground="#f2e8dc",
            relief="solid",
            bd=1,
            font=("Microsoft YaHei UI", 10),
        )
        category_menu.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        editor = tk.Text(
            editor_panel,
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
        editor.grid(row=3, column=0, sticky="nsew")

        editor_scrollbar = tk.Scrollbar(editor_panel, orient="vertical", command=editor.yview)
        editor.configure(yscrollcommand=editor_scrollbar.set)
        editor_scrollbar.grid(row=3, column=1, sticky="ns")

        buttons = tk.Frame(shell, bg="#f7f1e8")
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        primary_buttons = tk.Frame(buttons, bg="#f7f1e8")
        primary_buttons.grid(row=0, column=0, columnspan=2, sticky="w")

        secondary_buttons = tk.Frame(buttons, bg="#f7f1e8")
        secondary_buttons.grid(row=1, column=0, sticky="w", pady=(8, 0))

        window_buttons = tk.Frame(buttons, bg="#f7f1e8")
        window_buttons.grid(row=1, column=1, sticky="e", pady=(8, 0))

        def item_title(item: dict[str, Any], index: int) -> str:
            text = str(item.get("text", "")).replace("\n", " ").strip()
            if len(text) > 36:
                text = text[:36] + "..."
            return f"{index}. [{item.get('category', 'manual')}] {text}"

        def set_editor(text: str, category: str) -> None:
            category_var.set(category if category in MEMORY_CATEGORIES else "manual")
            editor.delete("1.0", "end")
            editor.insert("1.0", text)

        def clear_selection() -> None:
            state["kind"] = ""
            state["id"] = ""
            pending_list.selection_clear(0, "end")
            memory_list.selection_clear(0, "end")
            selection_label.configure(text="新记忆")
            set_editor("", "manual")

        def render(keep_selection: bool = False) -> None:
            old_kind = state["kind"] if keep_selection else ""
            old_id = state["id"] if keep_selection else ""
            data = self.service.memory.load()
            state["pending"] = data.get("pending", [])
            state["memories"] = data.get("long_term", [])
            count_label.configure(text=f"待确认 {len(state['pending'])} 条 · 长期 {len(state['memories'])} 条")

            pending_list.delete(0, "end")
            for index, item in enumerate(state["pending"], start=1):
                pending_list.insert("end", item_title(item, index))

            memory_list.delete(0, "end")
            for index, item in enumerate(state["memories"], start=1):
                memory_list.insert("end", item_title(item, index))

            state["kind"] = ""
            state["id"] = ""
            selection_label.configure(text="新记忆")
            if old_kind == "pending":
                for index, item in enumerate(state["pending"]):
                    if item.get("id") == old_id:
                        pending_list.selection_set(index)
                        load_pending(index)
                        return
            if old_kind == "memory":
                for index, item in enumerate(state["memories"]):
                    if item.get("id") == old_id:
                        memory_list.selection_set(index)
                        load_memory(index)
                        return
            if not keep_selection:
                clear_selection()

        def load_pending(index: int) -> None:
            if index < 0 or index >= len(state["pending"]):
                return
            item = state["pending"][index]
            state["kind"] = "pending"
            state["id"] = str(item.get("id", ""))
            memory_list.selection_clear(0, "end")
            selection_label.configure(text="待确认记忆")
            set_editor(str(item.get("text", "")), str(item.get("category", "manual")))

        def load_memory(index: int) -> None:
            if index < 0 or index >= len(state["memories"]):
                return
            item = state["memories"][index]
            state["kind"] = "memory"
            state["id"] = str(item.get("id", ""))
            pending_list.selection_clear(0, "end")
            selection_label.configure(text="长期记忆")
            set_editor(str(item.get("text", "")), str(item.get("category", "manual")))

        def on_pending_select(_event: tk.Event[Any]) -> None:
            selection = pending_list.curselection()
            if selection:
                load_pending(selection[0])

        def on_memory_select(_event: tk.Event[Any]) -> None:
            selection = memory_list.curselection()
            if selection:
                load_memory(selection[0])

        def editor_text() -> str:
            return editor.get("1.0", "end-1c").strip()

        def add_pending() -> None:
            text = editor_text()
            if not text:
                messagebox.showwarning("樱茗", "记忆内容不能为空。", parent=window)
                return
            try:
                self.service.suggest_memory(text, category=category_var.get())
            except ValueError as exc:
                messagebox.showwarning("樱茗", str(exc), parent=window)
                return
            self.set_bubble("好，我先放进待确认。确认之后再进入长期记忆。")
            clear_selection()
            render()

        def save_direct() -> None:
            text = editor_text()
            if not text:
                messagebox.showwarning("樱茗", "记忆内容不能为空。", parent=window)
                return
            try:
                self.service.remember(text, category=category_var.get(), refresh_profile=False)
            except ValueError as exc:
                messagebox.showwarning("樱茗", str(exc), parent=window)
                return
            self.set_bubble("好，这条已经直接写入长期记忆。")
            self.start_profile_refresh("直接写入长期记忆")
            clear_selection()
            render()

        def save_edit() -> None:
            if not state["kind"] or not state["id"]:
                messagebox.showwarning("樱茗", "请先选择一条记忆。", parent=window)
                return
            text = editor_text()
            try:
                if state["kind"] == "pending":
                    self.service.update_pending_memory(state["id"], text, category_var.get())
                else:
                    self.service.update_memory(state["id"], text, category_var.get(), refresh_profile=False)
                    self.start_profile_refresh("修改长期记忆")
            except ValueError as exc:
                messagebox.showwarning("樱茗", str(exc), parent=window)
                return
            self.set_bubble("记忆已经改好了。")
            render(keep_selection=True)

        def confirm_pending() -> None:
            if state["kind"] != "pending" or not state["id"]:
                messagebox.showwarning("樱茗", "请先选择一条待确认记忆。", parent=window)
                return
            try:
                self.service.confirm_pending_memory(
                    state["id"],
                    text=editor_text(),
                    category=category_var.get(),
                    refresh_profile=False,
                )
            except ValueError as exc:
                messagebox.showwarning("樱茗", str(exc), parent=window)
                return
            self.set_bubble("好，这条已经进入长期记忆。")
            self.start_profile_refresh("确认待确认记忆")
            clear_selection()
            render()

        def discard_pending() -> None:
            if state["kind"] != "pending" or not state["id"]:
                messagebox.showwarning("樱茗", "请先选择一条待确认记忆。", parent=window)
                return
            self.service.discard_pending_memory(state["id"])
            self.set_bubble("这条建议已经忽略。")
            clear_selection()
            render()

        def delete_memory() -> None:
            if state["kind"] != "memory" or not state["id"]:
                messagebox.showwarning("樱茗", "请先选择一条长期记忆。", parent=window)
                return
            if not messagebox.askyesno("樱茗", "要删除这条长期记忆吗？", parent=window):
                return
            self.service.delete_memory(state["id"], refresh_profile=False)
            self.set_bubble("这条长期记忆已经删除。")
            self.start_profile_refresh("删除长期记忆")
            clear_selection()
            render()

        pending_list.bind("<<ListboxSelect>>", on_pending_select)
        memory_list.bind("<<ListboxSelect>>", on_memory_select)

        tk.Button(
            window_buttons,
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
            window_buttons,
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
            secondary_buttons,
            text="删除长期",
            command=delete_memory,
            bg="#ffffff",
            fg="#8a3b3b",
            relief="solid",
            bd=1,
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            secondary_buttons,
            text="忽略待确认",
            command=discard_pending,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            primary_buttons,
            text="加入待确认",
            command=add_pending,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            primary_buttons,
            text="确认到长期",
            command=confirm_pending,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            primary_buttons,
            text="保存修改",
            command=save_edit,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            primary_buttons,
            text="直接长期",
            command=save_direct,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left")

        render()
        editor.focus_set()

    def open_connection_settings(self) -> None:
        settings = self.service.client.settings
        if not settings.is_deepseek:
            settings = self.service.deepseek_defaults(api_key=settings.api_key)

        window = tk.Toplevel(self.root)
        window.title("连接 DeepSeek")
        window.geometry("520x560+760+100")
        window.minsize(520, 560)
        window.resizable(True, False)
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        form = tk.Frame(window, bg="#f7f1e8", padx=12, pady=12)
        form.pack(side="top", fill="both", expand=True)
        form.columnconfigure(0, weight=1)

        tk.Label(
            form,
            text="连接 DeepSeek",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        def add_entry(row: int, label: str, value: str, show: str | None = None) -> tk.Entry:
            tk.Label(
                form,
                text=label,
                bg="#f7f1e8",
                fg="#2d3230",
                font=("Microsoft YaHei UI", 10, "bold"),
            ).grid(row=row, column=0, sticky="w", pady=(6, 3))
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
            entry.grid(row=row + 1, column=0, sticky="ew", ipady=7)
            return entry

        api_key_entry = add_entry(1, "API Key", settings.api_key, show="*")
        base_url_entry = add_entry(3, "Base URL", settings.base_url or DEFAULT_DEEPSEEK_BASE_URL)
        model_entry = add_entry(5, "模型", settings.model or DEFAULT_DEEPSEEK_MODEL)
        temperature_entry = add_entry(7, "温度", str(settings.temperature))

        auto_memory_var = tk.BooleanVar(value=settings.auto_memory)
        tk.Checkbutton(
            form,
            text="自动整理长期记忆",
            variable=auto_memory_var,
            bg="#f7f1e8",
            fg="#2d3230",
            activebackground="#f7f1e8",
            font=("Microsoft YaHei UI", 10),
        ).grid(row=9, column=0, sticky="w", pady=(10, 0))

        auto_profile_var = tk.BooleanVar(value=settings.auto_profile)
        tk.Checkbutton(
            form,
            text="自动总结用户画像",
            variable=auto_profile_var,
            bg="#f7f1e8",
            fg="#2d3230",
            activebackground="#f7f1e8",
            font=("Microsoft YaHei UI", 10),
        ).grid(row=10, column=0, sticky="w", pady=(4, 0))

        thinking_var = tk.BooleanVar(value=settings.deepseek_thinking == "enabled")
        tk.Checkbutton(
            form,
            text="启用 DeepSeek 思考模式",
            variable=thinking_var,
            bg="#f7f1e8",
            fg="#2d3230",
            activebackground="#f7f1e8",
            font=("Microsoft YaHei UI", 10),
        ).grid(row=11, column=0, sticky="w", pady=(4, 0))

        buttons = tk.Frame(window, bg="#f7f1e8")
        buttons.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

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
                auto_profile=auto_profile_var.get(),
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
        window.geometry("660x620+700+120")
        window.minsize(620, 560)
        window.resizable(True, True)
        window.configure(bg="#f7f1e8")
        window.attributes("-topmost", self.topmost)

        result_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        shell = tk.Frame(window, bg="#f7f1e8", padx=12, pady=12)
        shell.pack(fill="both", expand=True)
        shell.rowconfigure(1, weight=1)
        shell.columnconfigure(0, weight=1)

        header = tk.Frame(shell, bg="#f7f1e8")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="用户画像",
            bg="#f7f1e8",
            fg="#2d3230",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        status_label = tk.Label(
            header,
            text="确认后保存，樱茗以后会按这份画像理解你。",
            bg="#f7f1e8",
            fg="#6f7f56",
            font=("Microsoft YaHei UI", 9),
        )
        status_label.grid(row=0, column=1, sticky="e")

        editor_frame = tk.Frame(shell, bg="#f7f1e8")
        editor_frame.grid(row=1, column=0, sticky="nsew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        editor = tk.Text(
            editor_frame,
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
        editor.grid(row=0, column=0, sticky="nsew")
        editor_scrollbar = tk.Scrollbar(editor_frame, orient="vertical", command=editor.yview)
        editor.configure(yscrollcommand=editor_scrollbar.set)
        editor_scrollbar.grid(row=0, column=1, sticky="ns")
        editor.insert("1.0", self.service.read_profile())

        buttons = tk.Frame(shell, bg="#f7f1e8")
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        def set_editor_text(text: str) -> None:
            editor.delete("1.0", "end")
            editor.insert("1.0", text)

        def load_current() -> None:
            set_editor_text(self.service.read_profile())
            status_label.configure(text="已载入当前画像。")

        def generate_worker() -> None:
            try:
                result = self.service.generate_profile_draft()
                result_queue.put({"ok": True, "draft": result["profile_draft"]})
            except Exception as exc:  # noqa: BLE001 - keep prototype errors visible.
                result_queue.put({"ok": False, "error": str(exc)})

        def poll_generate_result() -> None:
            try:
                result = result_queue.get_nowait()
            except queue.Empty:
                if window.winfo_exists():
                    window.after(120, poll_generate_result)
                return

            generate_button.configure(state="normal")
            if result.get("ok"):
                set_editor_text(str(result.get("draft", "")))
                status_label.configure(text="草稿已生成。请检查后再保存。")
                self.set_bubble("画像草稿已经整理好。你看一遍，确认后再保存。")
            else:
                status_label.configure(text="生成失败。")
                messagebox.showerror("樱茗", str(result.get("error", "生成画像草稿失败。")), parent=window)

        def generate() -> None:
            generate_button.configure(state="disabled")
            status_label.configure(text="正在根据长期记忆整理画像草稿。")
            threading.Thread(target=generate_worker, daemon=True).start()
            window.after(120, poll_generate_result)

        def save() -> None:
            self.service.save_profile(editor.get("1.0", "end-1c"))
            self.set_bubble("画像已经保存。这样我会更稳地记住你确认过的部分。")
            status_label.configure(text="画像已保存。")
            window.destroy()

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
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons,
            text="载入当前",
            command=load_current,
            bg="#ffffff",
            fg="#42523d",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 8))
        generate_button = tk.Button(
            buttons,
            text="生成画像草稿",
            command=generate,
            bg="#42523d",
            fg="#ffffff",
            activebackground="#526a7a",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        generate_button.pack(side="left")

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
