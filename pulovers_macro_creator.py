#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 現代極簡扁平化 Python 巨集工作站 (CustomTkinter Edition)
=============================================================================
v4.0 全面重構：
1. 全面改用 CustomTkinter 現代極簡扁平化 UI，統一微圓角設計語言，徹底告別原生 tkinter 外觀。
2. 完整支援深色模式 / 淺色模式即時切換，並自動記憶使用者偏好主題。
3. 自動記憶上次開啟 / 儲存的專案檔：關閉軟體後，下次啟動將自動載入上次使用的存檔。
4. 純 CustomTkinter 巨集步驟清單、浮動下拉與右鍵選單、微圓角數值調整器與快捷鍵設定對話框。
5. 完整保留所有核心自動化功能：視窗控制、鍵鼠錄製、找圖/找色、流程控制、獨立 .py 匯出與全域防誤觸熱鍵。

環境需求：
    pip install customtkinter pyautogui pygetwindow pynput pillow opencv-python
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from tkinter import filedialog
from typing import Any, Callable, Dict, List, Optional, Set

# 確保本檔案所在目錄在模組搜尋路徑內
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    import customtkinter as ctk

    HAS_CTK = True
except Exception:
    ctk = None  # type: ignore
    HAS_CTK = False

from src.app_config import AppConfig
from src.macro_core import (
    ACTION_CATEGORIES,
    ACTION_DISPLAY_NAMES,
    CATEGORY_LABELS,
    DEFAULT_APP_HOTKEYS,
    HAS_PYAUTOGUI,
    HAS_PYGETWINDOW,
    HAS_PYNPUT,
    HOTKEY_ACTION_LABELS,
    HOTKEY_PRESETS,
    KEY_CATALOG,
    MODIFIER_KEYSYMS,
    MOUSE_BUTTON_OPTIONS,
    RESERVED_EDITOR_SHORTCUTS,
    TK_KEYSYM_MAP,
    MacroEngine,
    MacroStep,
    PythonScriptExporter,
    WindowManager,
    extract_clean_token,
    format_hotkey_display,
    get_default_sample_steps,
    get_key_dropdown_values,
    hotkey_to_pynput_sequence,
    is_safe_hotkey_while_typing,
    normalize_hotkey_string,
    pyautogui,
    pynput_kb,
    resolve_action_type,
    tk_event_to_hotkey_string,
)
from src.ui_dialogs import HotkeySettingsDialog, show_confirm_dialog, show_message_dialog
from src.ui_floating import FloatingControlWindow
from src.ui_step_table import MacroStepTable
from src.ui_theme import MONO_FONT_FAMILY, PALETTE, RADIUS, UI_FONT_FAMILY, resolve_color
from src.ui_widgets import CTkPopupMenu, CTkSpinbox

EDITABLE_WIDGET_CLASSES: Set[str] = {
    "TEntry",
    "Entry",
    "TSpinbox",
    "Spinbox",
    "TCombobox",
    "Combobox",
    "Text",
}


class PyMacroCreatorApp:
    """現代極簡扁平化 CustomTkinter 巨集工作站主視窗"""

    LEFT_PANEL_WIDTH = 390
    MAX_HISTORY = 50

    def __init__(self, root: ctk.CTk, initial_project: Optional[str] = None) -> None:
        self.root = root
        self.config = AppConfig()

        # 載入上次主題偏好
        self.theme_mode: str = self.config.get_theme_mode()
        ctk.set_appearance_mode(self.theme_mode)
        ctk.set_default_color_theme("blue")

        self.root.configure(fg_color=PALETTE["bg_app"])
        self.root.geometry(self.config.get_window_geometry())
        self.root.minsize(1020, 650)

        # 字型快取
        self.f_title = ctk.CTkFont(family=UI_FONT_FAMILY, size=14, weight="bold")
        self.f_sub = ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold")
        self.f_body = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)
        self.f_small = ctk.CTkFont(family=UI_FONT_FAMILY, size=11)
        self.f_pill = ctk.CTkFont(family=UI_FONT_FAMILY, size=11, weight="bold")
        self.f_mono = ctk.CTkFont(family=MONO_FONT_FAMILY, size=12)

        # 巨集資料與復原/重做堆疊
        self.steps: List[MacroStep] = []
        self.clipboard_steps: List[MacroStep] = []
        self.undo_stack: List[List[MacroStep]] = []
        self.redo_stack: List[List[MacroStep]] = []

        self.current_file: Optional[str] = None
        self.is_dirty: bool = False
        self.active_category: str = "Mouse"
        self.editing_index: Optional[int] = None
        self._log_visible: bool = True
        self._current_engine_state: str = "Ready"
        self._cursor_stop_event = threading.Event()
        self.floating_win: Optional[FloatingControlWindow] = None
        self._floating_last_pos: Optional[tuple[int, int]] = None
        self.var_floating = ctk.BooleanVar(value=False)

        # 錄製選項
        self.var_rec_moves = ctk.BooleanVar(value=self.config.get_record_mouse_moves())

        # 自定義快捷鍵與防誤觸鎖定
        self.app_hotkeys: Dict[str, str] = copy.deepcopy(DEFAULT_APP_HOTKEYS)
        self._hotkey_lookup: Dict[str, Callable[[], None]] = {}
        self._global_hotkey_listener: Any = None
        self._suspend_hotkeys: bool = False
        self._single_key_capture_cb: Optional[Callable[[str], None]] = None
        self._last_hotkey_trigger_ts: float = 0.0

        self.engine = MacroEngine(
            on_log=self._log_threadsafe,
            on_step_highlight=self._highlight_step_threadsafe,
            on_recorded_step=self._append_recorded_step_threadsafe,
            on_state_change=self._update_state_threadsafe,
        )

        self._build_ui()

        # 綁定安全鍵盤分派器與視窗關閉處理
        self.root.bind("<KeyPress>", self._on_window_key_dispatch)
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)

        self._apply_app_hotkeys()
        self._load_initial_project(initial_project)
        self._update_window_title()
        self._start_cursor_tracker()

    # -------------------- 焦點與視窗標題 --------------------
    def _is_editing_text_widget(self, widget: Any = None) -> bool:
        target = widget or self.root.focus_get()
        if target is None:
            return False
        try:
            return target.winfo_class() in EDITABLE_WIDGET_CLASSES
        except Exception:
            return False

    def _update_window_title(self) -> None:
        fname = os.path.basename(self.current_file) if self.current_file else "未命名專案"
        dirty_mark = " ●" if self.is_dirty else ""
        self.root.title(f"{fname}{dirty_mark} — PyMacroCreator")
        if hasattr(self, "lbl_project_badge"):
            self.lbl_project_badge.configure(text=f"{fname}{dirty_mark}")

    def _mark_dirty(self, dirty: bool = True) -> None:
        self.is_dirty = dirty
        self._update_window_title()

    # -------------------- 主題即時切換 --------------------
    def toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        ctk.set_appearance_mode(self.theme_mode)
        self.config.set_theme_mode(self.theme_mode)
        self.btn_theme.configure(
            text="☀ 淺色" if self.theme_mode == "dark" else "☾ 深色"
        )
        self.step_table.refresh_theme()
        self._update_state_badge(self._current_engine_state)

    def toggle_floating_window(self) -> None:
        if self.var_floating.get():
            if self.floating_win is None or not self.floating_win.winfo_exists():
                self.floating_win = FloatingControlWindow(
                    parent=self.root,
                    on_play=self.play_macro,
                    on_stop=self.engine.stop_playback,
                    on_close_request=self._close_floating_from_popup,
                    initial_pos=self._floating_last_pos,
                    initial_state=self._current_engine_state,
                    theme_mode=self.theme_mode,
                )
        else:
            self._destroy_floating_window()

    def _close_floating_from_popup(self) -> None:
        self.var_floating.set(False)
        self._destroy_floating_window()

    def _destroy_floating_window(self) -> None:
        if self.floating_win is not None:
            try:
                if self.floating_win.winfo_exists():
                    self._floating_last_pos = self.floating_win.get_position()
                    self.floating_win.destroy()
            except Exception:
                pass
            self.floating_win = None

    # -------------------- Undo / Redo 歷史堆疊 --------------------
    def _push_undo_snapshot(self) -> None:
        self.undo_stack.append(copy.deepcopy(self.steps))
        if len(self.undo_stack) > self.MAX_HISTORY:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._mark_dirty(True)

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.steps))
        self.steps = self.undo_stack.pop()
        self._exit_edit_mode()
        self._refresh_table()
        self._mark_dirty(True)
        self._log_threadsafe("已復原上一步操作。")

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.steps))
        self.steps = self.redo_stack.pop()
        self._exit_edit_mode()
        self._refresh_table()
        self._mark_dirty(True)
        self._log_threadsafe("已重做操作。")

    # -------------------- 頂部現代化選單列 (無原生 tk.Menu) --------------------
    def _show_dropdown_under(self, btn: ctk.CTkButton, items: List[Dict[str, Any]], width: int = 235) -> None:
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height() + 4
        menu = CTkPopupMenu(self.root, items=items, width=width)
        menu.show(x, y)

    def _open_file_menu(self, btn: ctk.CTkButton) -> None:
        self._show_dropdown_under(
            btn,
            [
                {"type": "command", "label": "新增專案", "shortcut": "Ctrl+N", "command": self.new_project},
                {"type": "command", "label": "開啟專案...", "shortcut": "Ctrl+O", "command": self.open_project},
                {"type": "separator"},
                {"type": "command", "label": "儲存", "shortcut": "Ctrl+S", "command": self.save_project},
                {"type": "command", "label": "另存新檔...", "shortcut": "Ctrl+Shift+S", "command": self.save_project_as},
                {"type": "separator"},
                {"type": "command", "label": "匯出獨立腳本 (.py)...", "shortcut": "Ctrl+E", "command": self.export_python_script},
                {"type": "separator"},
                {"type": "command", "label": "結束", "shortcut": "", "command": self._on_app_close},
            ],
            width=245,
        )

    def _open_edit_menu(self, btn: ctk.CTkButton) -> None:
        self._show_dropdown_under(
            btn,
            [
                {"type": "command", "label": "復原", "shortcut": "Ctrl+Z", "command": self.undo},
                {"type": "command", "label": "重做", "shortcut": "Ctrl+Y", "command": self.redo},
                {"type": "separator"},
                {"type": "command", "label": "剪下步驟", "shortcut": "Ctrl+X", "command": self.cut_selected_steps},
                {"type": "command", "label": "複製步驟", "shortcut": "Ctrl+C", "command": self.copy_selected_steps},
                {"type": "command", "label": "貼上步驟", "shortcut": "Ctrl+V", "command": self.paste_steps},
                {"type": "command", "label": "快速複製一份", "shortcut": "Ctrl+D", "command": self.duplicate_step},
                {"type": "separator"},
                {"type": "command", "label": "編輯選取步驟", "shortcut": "Enter", "command": self.enter_edit_selected_step},
                {"type": "command", "label": "啟用 / 停用", "shortcut": "Space", "command": self.toggle_step_enabled},
                {"type": "command", "label": "刪除選取步驟", "shortcut": "Delete", "command": self.delete_step},
                {"type": "separator"},
                {"type": "command", "label": "上移", "shortcut": "Alt+↑", "command": lambda: self.move_step(-1)},
                {"type": "command", "label": "下移", "shortcut": "Alt+↓", "command": lambda: self.move_step(1)},
                {"type": "command", "label": "全選", "shortcut": "Ctrl+A", "command": self._select_all_steps},
                {"type": "separator"},
                {"type": "command", "label": "清空全部步驟", "shortcut": "", "command": self.clear_all_steps},
            ],
            width=235,
        )

    def _open_macro_menu(self, btn: ctk.CTkButton) -> None:
        self._show_dropdown_under(
            btn,
            [
                {"type": "command", "label": "播放巨集", "shortcut": format_hotkey_display(self.app_hotkeys.get("play", "f5")), "command": self.play_macro},
                {"type": "command", "label": "暫停 / 繼續", "shortcut": format_hotkey_display(self.app_hotkeys.get("pause", "f7")), "command": self.engine.toggle_pause},
                {"type": "command", "label": "停止播放", "shortcut": format_hotkey_display(self.app_hotkeys.get("stop", "f6")), "command": self.engine.stop_playback},
                {"type": "separator"},
                {"type": "command", "label": "開始 / 停止錄製", "shortcut": format_hotkey_display(self.app_hotkeys.get("record", "f9")), "command": self.toggle_record},
                {
                    "type": "check",
                    "label": "錄製時包含滑鼠移動軌跡",
                    "variable": self.var_rec_moves,
                    "command": lambda: self.config.set_record_mouse_moves(self.var_rec_moves.get()),
                },
                {"type": "separator"},
                {"type": "command", "label": "自定義快捷鍵...", "shortcut": "", "command": self.open_hotkey_settings_dialog},
            ],
            width=255,
        )

    def _open_view_menu(self, btn: ctk.CTkButton) -> None:
        self._show_dropdown_under(
            btn,
            [
                {"type": "command", "label": "切換深色 / 淺色模式", "shortcut": "", "command": self.toggle_theme},
                {"type": "command", "label": "顯示 / 隱藏執行日誌", "shortcut": "", "command": self.toggle_log_panel},
            ],
            width=220,
        )

    def _on_table_right_click(self, event: Any, _idx: int) -> None:
        menu = CTkPopupMenu(
            self.root,
            items=[
                {"type": "command", "label": "編輯此步驟", "shortcut": "Enter", "command": self.enter_edit_selected_step},
                {"type": "command", "label": "啟用 / 停用", "shortcut": "Space", "command": self.toggle_step_enabled},
                {"type": "separator"},
                {"type": "command", "label": "剪下", "shortcut": "Ctrl+X", "command": self.cut_selected_steps},
                {"type": "command", "label": "複製", "shortcut": "Ctrl+C", "command": self.copy_selected_steps},
                {"type": "command", "label": "貼上", "shortcut": "Ctrl+V", "command": self.paste_steps},
                {"type": "command", "label": "快速複製一份", "shortcut": "Ctrl+D", "command": self.duplicate_step},
                {"type": "separator"},
                {"type": "command", "label": "上移", "shortcut": "Alt+↑", "command": lambda: self.move_step(-1)},
                {"type": "command", "label": "下移", "shortcut": "Alt+↓", "command": lambda: self.move_step(1)},
                {"type": "separator"},
                {"type": "command", "label": "刪除", "shortcut": "Delete", "command": self.delete_step},
            ],
            width=220,
        )
        menu.show(event.x_root, event.y_root)

    # -------------------- 整體版面建構 --------------------
    def _build_ui(self) -> None:
        # 1. 頂部整合列：選單列 + 控制工具列
        header_shell = ctk.CTkFrame(
            self.root,
            fg_color=PALETTE["bg_surface"],
            corner_radius=0,
        )
        header_shell.pack(side="top", fill="x")

        # 1a. 極簡扁平選單條
        menu_strip = ctk.CTkFrame(header_shell, fg_color="transparent", height=32)
        menu_strip.pack(fill="x", padx=12, pady=(4, 0))

        for label, handler in [
            ("檔案", self._open_file_menu),
            ("編輯", self._open_edit_menu),
            ("巨集", self._open_macro_menu),
            ("檢視", self._open_view_menu),
        ]:
            btn = ctk.CTkButton(
                menu_strip,
                text=label,
                width=48,
                height=26,
                corner_radius=6,
                fg_color="transparent",
                hover_color=PALETTE["bg_hover"],
                text_color=PALETTE["fg_secondary"],
                font=self.f_body,
            )
            btn.configure(command=lambda b=btn, fn=handler: fn(b))
            btn.pack(side="left", padx=(0, 2))

        # 右側顯示目前檔案名稱標籤與懸浮視窗開關
        self.switch_floating = ctk.CTkSwitch(
            menu_strip,
            text="懸浮視窗",
            variable=self.var_floating,
            command=self.toggle_floating_window,
            width=40,
            switch_width=36,
            switch_height=18,
            font=self.f_small,
            text_color=PALETTE["fg_secondary"],
            progress_color=PALETTE["accent"],
        )
        self.switch_floating.pack(side="right", padx=(10, 4))

        self.lbl_project_badge = ctk.CTkLabel(
            menu_strip,
            text="未命名專案",
            font=self.f_small,
            text_color=PALETTE["fg_muted"],
        )
        self.lbl_project_badge.pack(side="right", padx=(0, 8))

        # 細分隔線
        ctk.CTkFrame(header_shell, height=1, fg_color=PALETTE["border"]).pack(fill="x", pady=(3, 0))

        # 1b. 主操作控制列
        toolbar = ctk.CTkFrame(header_shell, fg_color="transparent")
        toolbar.pack(fill="x", padx=14, pady=9)

        # 左側：狀態徽章 + 播放/暫停/停止/錄製 + 迴圈/倍速
        left_ctrl = ctk.CTkFrame(toolbar, fg_color="transparent")
        left_ctrl.pack(side="left")

        self.lbl_state = ctk.CTkLabel(
            left_ctrl,
            text="● 就緒",
            font=self.f_pill,
            fg_color=resolve_color("success", self.theme_mode),
            text_color="#FFFFFF",
            corner_radius=RADIUS["badge"],
            width=74,
            height=28,
        )
        self.lbl_state.pack(side="left", padx=(0, 10))

        self.btn_play = ctk.CTkButton(
            left_ctrl,
            text="▶ 播放 (F5)",
            height=32,
            width=108,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["success"],
            hover_color=PALETTE["success_hover"],
            text_color="#FFFFFF",
            font=self.f_sub,
            command=self.play_macro,
        )
        self.btn_play.pack(side="left", padx=(0, 5))

        self.btn_pause = ctk.CTkButton(
            left_ctrl,
            text="⏸",
            height=32,
            width=36,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.engine.toggle_pause,
        )
        self.btn_pause.pack(side="left", padx=(0, 5))

        self.btn_stop = ctk.CTkButton(
            left_ctrl,
            text="■",
            height=32,
            width=36,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.engine.stop_playback,
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        self.btn_record = ctk.CTkButton(
            left_ctrl,
            text="● 錄製 (F9)",
            height=32,
            width=108,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["danger"],
            hover_color=PALETTE["danger_hover"],
            text_color="#FFFFFF",
            font=self.f_sub,
            command=self.toggle_record,
        )
        self.btn_record.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(left_ctrl, text="迴圈", font=self.f_small, text_color=PALETTE["fg_secondary"]).pack(
            side="left", padx=(2, 4)
        )
        self.var_loops = ctk.IntVar(value=1)
        CTkSpinbox(
            left_ctrl, variable=self.var_loops, min_value=0, max_value=99999, width=90, height=30
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(left_ctrl, text="倍速", font=self.f_small, text_color=PALETTE["fg_secondary"]).pack(
            side="left", padx=(0, 4)
        )
        self.var_speed = ctk.StringVar(value="1.0")
        ctk.CTkOptionMenu(
            left_ctrl,
            variable=self.var_speed,
            values=["0.5", "1.0", "1.5", "2.0", "5.0"],
            width=72,
            height=30,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            button_color=PALETTE["bg_elevated"],
            button_hover_color=PALETTE["bg_hover"],
            dropdown_fg_color=PALETTE["bg_surface"],
            dropdown_hover_color=PALETTE["bg_hover"],
            dropdown_text_color=PALETTE["fg_primary"],
            text_color=PALETTE["fg_primary"],
            font=self.f_body,
        ).pack(side="left")

        # 右側：常用操作與主題切換
        right_ctrl = ctk.CTkFrame(toolbar, fg_color="transparent")
        right_ctrl.pack(side="right")

        self.btn_theme = ctk.CTkButton(
            right_ctrl,
            text="☀ 淺色" if self.theme_mode == "dark" else "☾ 深色",
            height=32,
            width=76,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.toggle_theme,
        )
        self.btn_theme.pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            right_ctrl,
            text="快捷鍵",
            height=32,
            width=66,
            corner_radius=RADIUS["button"],
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=self.f_body,
            command=self.open_hotkey_settings_dialog,
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            right_ctrl,
            text="匯出 .py",
            height=32,
            width=78,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.export_python_script,
        ).pack(side="right", padx=(4, 2))

        ctk.CTkButton(
            right_ctrl,
            text="儲存",
            height=32,
            width=62,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.save_project,
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            right_ctrl,
            text="開啟",
            height=32,
            width=62,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self.open_project,
        ).pack(side="right", padx=2)

        ctk.CTkFrame(header_shell, height=1, fg_color=PALETTE["border"]).pack(fill="x")

        # 2. 底部狀態列（先 pack bottom 確保永不被擠壓）
        status_shell = ctk.CTkFrame(self.root, fg_color=PALETTE["bg_surface"], corner_radius=0)
        status_shell.pack(side="bottom", fill="x")
        ctk.CTkFrame(status_shell, height=1, fg_color=PALETTE["border"]).pack(fill="x")

        status_bar = ctk.CTkFrame(status_shell, fg_color="transparent", height=32)
        status_bar.pack(fill="x", padx=14, pady=4)

        self.color_swatch = ctk.CTkFrame(
            status_bar,
            width=16,
            height=16,
            corner_radius=4,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=PALETTE["border_strong"],
        )
        self.color_swatch.pack(side="left", padx=(0, 8))

        self.lbl_cursor = ctk.CTkLabel(
            status_bar,
            text="X=0, Y=0 | RGB(255,255,255)",
            font=self.f_small,
            text_color=PALETTE["fg_secondary"],
        )
        self.lbl_cursor.pack(side="left")

        self.btn_capture_cursor = ctk.CTkButton(
            status_bar,
            text="吸取座標 (F2)",
            height=24,
            width=102,
            corner_radius=6,
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            font=self.f_small,
            command=self.capture_cursor_to_fields,
        )
        self.btn_capture_cursor.pack(side="left", padx=(10, 0))

        self.lbl_hotkey_summary = ctk.CTkLabel(
            status_bar,
            text="",
            font=self.f_small,
            text_color=PALETTE["fg_muted"],
        )
        self.lbl_hotkey_summary.pack(side="right")

        self.lbl_count_info = ctk.CTkLabel(
            status_bar,
            text="共 0 步",
            font=self.f_small,
            text_color=PALETTE["fg_secondary"],
        )
        self.lbl_count_info.pack(side="right", padx=(0, 16))

        # 3. 中央工作區（左側固定寬度卡片 + 右側自適應序列與日誌卡片）
        main_area = ctk.CTkFrame(self.root, fg_color="transparent")
        main_area.pack(side="top", fill="both", expand=True, padx=12, pady=12)

        left_card = ctk.CTkFrame(
            main_area,
            width=self.LEFT_PANEL_WIDTH,
            corner_radius=RADIUS["card"],
            fg_color=PALETTE["bg_surface"],
            border_width=1,
            border_color=PALETTE["border"],
        )
        left_card.pack(side="left", fill="y", padx=(0, 12))
        left_card.pack_propagate(False)
        self._build_left_inspector(left_card)

        right_area = ctk.CTkFrame(main_area, fg_color="transparent")
        right_area.pack(side="left", fill="both", expand=True)

        # 右側上方：巨集動作序列卡片
        table_card = ctk.CTkFrame(
            right_area,
            corner_radius=RADIUS["card"],
            fg_color=PALETTE["bg_surface"],
            border_width=1,
            border_color=PALETTE["border"],
        )
        table_card.pack(side="top", fill="both", expand=True)
        self._build_right_table(table_card)

        # 右側下方：可收合執行日誌卡片
        self.log_card = ctk.CTkFrame(
            right_area,
            corner_radius=RADIUS["card"],
            fg_color=PALETTE["bg_surface"],
            border_width=1,
            border_color=PALETTE["border"],
        )
        self.log_card.pack(side="bottom", fill="x", pady=(10, 0))
        self._build_bottom_console(self.log_card)

    # -------------------- 左欄：動作建構器 --------------------
    def _build_left_inspector(self, parent: ctk.CTkFrame) -> None:
        # 編輯模式提示橫幅（平時隱藏）
        self.edit_banner = ctk.CTkFrame(
            parent,
            fg_color=PALETTE["accent_subtle"],
            corner_radius=RADIUS["button"],
            height=36,
        )
        self.lbl_edit_banner = ctk.CTkLabel(
            self.edit_banner,
            text="正在編輯步驟 #1",
            font=self.f_sub,
            text_color=PALETTE["accent_fg"],
        )
        self.lbl_edit_banner.pack(side="left", padx=(12, 4), pady=6)

        ctk.CTkButton(
            self.edit_banner,
            text="✕ 取消編輯",
            height=24,
            width=76,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["accent_fg"],
            font=self.f_small,
            command=self._exit_edit_mode,
        ).pack(side="right", padx=(4, 8), pady=5)

        # 上半固定區：標題、分類膠囊、動作選擇
        self.left_top_section = ctk.CTkFrame(parent, fg_color="transparent")
        self.left_top_section.pack(side="top", fill="x", padx=14, pady=(14, 8))

        self.lbl_builder_title = ctk.CTkLabel(
            self.left_top_section,
            text="新增動作",
            font=self.f_title,
            text_color=PALETTE["fg_primary"],
            anchor="w",
        )
        self.lbl_builder_title.pack(fill="x", pady=(0, 10))

        cat_grid = ctk.CTkFrame(self.left_top_section, fg_color="transparent")
        cat_grid.pack(fill="x", pady=(0, 10))
        for col in range(4):
            cat_grid.grid_columnconfigure(col, weight=1, uniform="cat")

        self.cat_buttons: Dict[str, ctk.CTkButton] = {}
        for idx, (cat_key, cat_label) in enumerate(CATEGORY_LABELS.items()):
            r, col = divmod(idx, 4)
            btn = ctk.CTkButton(
                cat_grid,
                text=cat_label,
                height=30,
                corner_radius=RADIUS["pill"],
                fg_color=PALETTE["bg_elevated"],
                hover_color=PALETTE["bg_hover"],
                text_color=PALETTE["fg_secondary"],
                font=self.f_small,
                command=lambda k=cat_key: self._select_category(k),
            )
            btn.grid(row=r, column=col, sticky="ew", padx=2, pady=2)
            self.cat_buttons[cat_key] = btn

        self.var_action = ctk.StringVar()
        self.cb_action = ctk.CTkOptionMenu(
            self.left_top_section,
            variable=self.var_action,
            values=[""],
            height=34,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            button_color=PALETTE["bg_elevated"],
            button_hover_color=PALETTE["bg_hover"],
            dropdown_fg_color=PALETTE["bg_surface"],
            dropdown_hover_color=PALETTE["bg_hover"],
            dropdown_text_color=PALETTE["fg_primary"],
            text_color=PALETTE["fg_primary"],
            font=self.f_body,
            command=lambda _val: self._rebuild_param_fields(),
        )
        self.cb_action.pack(fill="x")

        ctk.CTkFrame(parent, height=1, fg_color=PALETTE["border"]).pack(
            side="top", fill="x", padx=14, pady=(2, 0)
        )

        # 底部固定區：共用欄位 + 提交按鈕
        bottom_section = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_section.pack(side="bottom", fill="x", padx=14, pady=(10, 14))

        ctk.CTkFrame(parent, height=1, fg_color=PALETTE["border"]).pack(
            side="bottom", fill="x", padx=14
        )

        common_box = ctk.CTkFrame(bottom_section, fg_color="transparent")
        common_box.pack(fill="x", pady=(0, 10))
        common_box.grid_columnconfigure(1, weight=1)
        common_box.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            common_box, text="延遲(ms)", font=self.f_small, text_color=PALETTE["fg_secondary"]
        ).grid(row=0, column=0, sticky="w", pady=4)
        self.var_delay = ctk.IntVar(value=100)
        CTkSpinbox(
            common_box, variable=self.var_delay, min_value=0, max_value=600000, step=50, width=104, height=30
        ).grid(row=0, column=1, sticky="ew", padx=(6, 10), pady=4)

        ctk.CTkLabel(
            common_box, text="重複", font=self.f_small, text_color=PALETTE["fg_secondary"]
        ).grid(row=0, column=2, sticky="w", pady=4)
        self.var_repeat = ctk.IntVar(value=1)
        CTkSpinbox(
            common_box, variable=self.var_repeat, min_value=1, max_value=9999, step=1, width=88, height=30
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=4)

        ctk.CTkLabel(
            common_box, text="備註", font=self.f_small, text_color=PALETTE["fg_secondary"]
        ).grid(row=1, column=0, sticky="w", pady=4)
        self.var_comment = ctk.StringVar(value="")
        ctk.CTkEntry(
            common_box,
            textvariable=self.var_comment,
            height=30,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            border_color=PALETTE["border_strong"],
            border_width=1,
            text_color=PALETTE["fg_primary"],
            placeholder_text="選填步驟說明...",
            font=self.f_body,
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=4)

        # 提交與取消按鈕
        self.action_btn_row = ctk.CTkFrame(bottom_section, fg_color="transparent")
        self.action_btn_row.pack(fill="x")
        self.action_btn_row.grid_columnconfigure(0, weight=1)

        self.btn_submit_step = ctk.CTkButton(
            self.action_btn_row,
            text="＋ 插入步驟",
            height=36,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color="#FFFFFF",
            font=self.f_sub,
            command=self._on_submit_step,
        )
        self.btn_submit_step.grid(row=0, column=0, sticky="ew")

        self.btn_cancel_edit = ctk.CTkButton(
            self.action_btn_row,
            text="取消",
            height=36,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_body,
            command=self._exit_edit_mode,
        )

        self.lbl_builder_hint = ctk.CTkLabel(
            bottom_section,
            text="提示：單擊右側表格僅選取位置，雙擊才載入編輯",
            font=self.f_small,
            text_color=PALETTE["fg_muted"],
            anchor="w",
        )
        self.lbl_builder_hint.pack(fill="x", pady=(8, 0))

        # 中間可捲動參數區
        self.param_container = ctk.CTkScrollableFrame(
            parent,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=PALETTE["scrollbar_fg"],
            scrollbar_button_hover_color=PALETTE["scrollbar_hover"],
        )
        self.param_container.pack(side="top", fill="both", expand=True, padx=10, pady=6)

        self.param_vars: Dict[str, Any] = {}
        self._select_category(self.active_category)

    def _select_category(self, category: str) -> None:
        self.active_category = category
        self._refresh_category_buttons()
        raw_actions = ACTION_CATEGORIES.get(category, [])
        display_actions = [ACTION_DISPLAY_NAMES.get(a, a) for a in raw_actions]
        self.cb_action.configure(values=display_actions)
        if display_actions:
            self.var_action.set(display_actions[0])
            self._rebuild_param_fields()

    def _refresh_category_buttons(self) -> None:
        for k, btn in self.cat_buttons.items():
            if k == self.active_category:
                btn.configure(
                    fg_color=PALETTE["accent"],
                    hover_color=PALETTE["accent_hover"],
                    text_color="#FFFFFF",
                    font=self.f_pill,
                )
            else:
                btn.configure(
                    fg_color=PALETTE["bg_elevated"],
                    hover_color=PALETTE["bg_hover"],
                    text_color=PALETTE["fg_secondary"],
                    font=self.f_small,
                )

    def _make_entry(self, parent: Any, var: ctk.StringVar) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent,
            textvariable=var,
            height=32,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            border_color=PALETTE["border_strong"],
            border_width=1,
            text_color=PALETTE["fg_primary"],
            font=self.f_body,
        )

    def _make_combobox(
        self,
        parent: Any,
        var: ctk.StringVar,
        values: List[str],
        state: str = "normal",
        command: Optional[Callable[[str], None]] = None,
    ) -> ctk.CTkComboBox:
        return ctk.CTkComboBox(
            parent,
            variable=var,
            values=values if values else [""],
            state=state,
            height=32,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            border_color=PALETTE["border_strong"],
            border_width=1,
            button_color=PALETTE["bg_elevated"],
            button_hover_color=PALETTE["bg_hover"],
            dropdown_fg_color=PALETTE["bg_surface"],
            dropdown_hover_color=PALETTE["bg_hover"],
            dropdown_text_color=PALETTE["fg_primary"],
            text_color=PALETTE["fg_primary"],
            font=self.f_body,
            command=command,
        )

    def _make_secondary_btn(
        self, parent: Any, text: str, command: Callable[[], None], height: int = 30
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            height=height,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=self.f_small,
            command=command,
        )

    def _rebuild_param_fields(self) -> None:
        self._single_key_capture_cb = None
        for child in self.param_container.winfo_children():
            child.destroy()
        self.param_vars.clear()
        try:
            self.param_container._parent_canvas.yview_moveto(0)
        except Exception:
            pass

        act = resolve_action_type(self.var_action.get())
        self.param_container.grid_columnconfigure(0, weight=0)
        self.param_container.grid_columnconfigure(1, weight=1)
        self.param_container.grid_columnconfigure(2, weight=0)

        # ---- 1. 視窗控制系列 ----
        if act in ("Activate Window", "Resize Window", "Move Window", "Set Window Bounds"):
            ctk.CTkLabel(
                self.param_container, text="視窗標題", font=self.f_body, text_color=PALETTE["fg_primary"]
            ).grid(row=0, column=0, sticky="w", pady=5, padx=(2, 8))

            open_titles = WindowManager.list_open_windows()
            default_title = open_titles[0] if open_titles else "記事本"
            title_var = ctk.StringVar(value=default_title)
            self.param_vars["title"] = title_var

            cb_win = self._make_combobox(
                self.param_container,
                title_var,
                open_titles if open_titles else ["記事本", "Notepad", "Chrome"],
            )
            cb_win.grid(row=0, column=1, sticky="ew", pady=5)

            win_helper = ctk.CTkFrame(self.param_container, fg_color="transparent")
            win_helper.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
            win_helper.grid_columnconfigure(0, weight=1)
            win_helper.grid_columnconfigure(1, weight=1)

            def _refresh_window_list() -> None:
                latest = WindowManager.list_open_windows()
                cb_win.configure(values=latest if latest else ["記事本"])
                if latest and not title_var.get().strip():
                    title_var.set(latest[0])
                self._log_threadsafe(f"已掃描到 {len(latest)} 個開啟中的視窗。")

            def _inspect_target_window() -> None:
                q = title_var.get().strip()
                info = WindowManager.get_window_rect(q)
                if info is None:
                    self._log_threadsafe(f"[警告] 找不到符合「{q}」的視窗。")
                    return
                wx, wy, ww, wh, full_t = info
                if "x" in self.param_vars:
                    self.param_vars["x"].set(str(wx))
                if "y" in self.param_vars:
                    self.param_vars["y"].set(str(wy))
                if "width" in self.param_vars:
                    self.param_vars["width"].set(str(ww))
                if "height" in self.param_vars:
                    self.param_vars["height"].set(str(wh))
                self._log_threadsafe(f"已讀取「{full_t}」位置 ({wx}, {wy})，大小 {ww}×{wh}")

            self._make_secondary_btn(win_helper, "刷新視窗清單", _refresh_window_list).grid(
                row=0, column=0, sticky="ew", padx=(0, 4)
            )
            self._make_secondary_btn(win_helper, "讀取目前位置/大小", _inspect_target_window).grid(
                row=0, column=1, sticky="ew", padx=(4, 0)
            )

            row_cursor = 2
            if act in ("Move Window", "Set Window Bounds"):
                for key, label in [("x", "位置 X"), ("y", "位置 Y")]:
                    ctk.CTkLabel(
                        self.param_container, text=label, font=self.f_body, text_color=PALETTE["fg_primary"]
                    ).grid(row=row_cursor, column=0, sticky="w", pady=5, padx=(2, 8))
                    v = ctk.StringVar(value="0")
                    self.param_vars[key] = v
                    self._make_entry(self.param_container, v).grid(row=row_cursor, column=1, sticky="ew", pady=5)
                    row_cursor += 1

            if act in ("Resize Window", "Set Window Bounds"):
                for key, label, default_v in [("width", "寬度 Width", "1280"), ("height", "高度 Height", "720")]:
                    ctk.CTkLabel(
                        self.param_container, text=label, font=self.f_body, text_color=PALETTE["fg_primary"]
                    ).grid(row=row_cursor, column=0, sticky="w", pady=5, padx=(2, 8))
                    v = ctk.StringVar(value=default_v)
                    self.param_vars[key] = v
                    self._make_entry(self.param_container, v).grid(row=row_cursor, column=1, sticky="ew", pady=5)
                    row_cursor += 1

                preset_row = ctk.CTkFrame(self.param_container, fg_color="transparent")
                preset_row.grid(row=row_cursor, column=0, columnspan=2, sticky="ew", pady=(4, 6))
                for col_i, (w_val, h_val) in enumerate([(800, 600), (1280, 720), (1600, 900), (1920, 1080)]):
                    preset_row.grid_columnconfigure(col_i, weight=1)
                    ctk.CTkButton(
                        preset_row,
                        text=f"{w_val}×{h_val}",
                        height=26,
                        corner_radius=RADIUS["pill"],
                        fg_color=PALETTE["bg_elevated"],
                        hover_color=PALETTE["bg_hover"],
                        text_color=PALETTE["fg_secondary"],
                        font=self.f_small,
                        command=lambda w=w_val, h=h_val: (
                            self.param_vars["width"].set(str(w)),
                            self.param_vars["height"].set(str(h)),
                        ),
                    ).grid(row=0, column=col_i, sticky="ew", padx=2)
                row_cursor += 1

            def _test_window_action_now() -> None:
                temp_step = self._collect_step_from_palette()
                self.engine._execute_single_action(temp_step, speed_factor=1.0)

            self._make_secondary_btn(
                self.param_container, "立即測試執行", _test_window_action_now, height=32
            ).grid(row=row_cursor, column=0, columnspan=2, sticky="ew", pady=(6, 4))
            return

        # ---- 2. 鍵盤單鍵 ----
        if act in ("Key Press", "Key Down", "Key Up"):
            ctk.CTkLabel(
                self.param_container, text="按鍵分類", font=self.f_small, text_color=PALETTE["fg_secondary"]
            ).grid(row=0, column=0, sticky="w", pady=5, padx=(2, 8))

            cat_filter_var = ctk.StringVar(value="全部按鍵")
            key_var = ctk.StringVar(value="up (↑ 方向鍵上 (Up))")
            self.param_vars["key"] = key_var

            cb_key = self._make_combobox(
                self.param_container, key_var, get_key_dropdown_values("全部按鍵")
            )

            def _on_key_cat_changed(choice: str) -> None:
                vals = get_key_dropdown_values(choice)
                cb_key.configure(values=vals if vals else [""])
                if vals:
                    key_var.set(vals[0])

            ctk.CTkOptionMenu(
                self.param_container,
                variable=cat_filter_var,
                values=["全部按鍵"] + list(KEY_CATALOG.keys()),
                height=32,
                corner_radius=RADIUS["input"],
                fg_color=PALETTE["bg_input"],
                button_color=PALETTE["bg_elevated"],
                button_hover_color=PALETTE["bg_hover"],
                dropdown_fg_color=PALETTE["bg_surface"],
                dropdown_hover_color=PALETTE["bg_hover"],
                dropdown_text_color=PALETTE["fg_primary"],
                text_color=PALETTE["fg_primary"],
                font=self.f_body,
                command=_on_key_cat_changed,
            ).grid(row=0, column=1, sticky="ew", pady=5)

            ctk.CTkLabel(
                self.param_container, text="目標按鍵", font=self.f_body, text_color=PALETTE["fg_primary"]
            ).grid(row=1, column=0, sticky="w", pady=5, padx=(2, 8))
            cb_key.grid(row=1, column=1, sticky="ew", pady=5)

            btn_detect = self._make_secondary_btn(
                self.param_container, "點此後按下鍵盤任意鍵自動填入", lambda: None, height=32
            )
            btn_detect.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 8))

            def _start_key_capture() -> None:
                btn_detect.configure(
                    text="請按下鍵盤任意鍵...",
                    fg_color=PALETTE["accent"],
                    text_color="#FFFFFF",
                )
                self.root.focus_set()

                def _on_captured(mapped_key: str) -> None:
                    matched_display = mapped_key
                    for item in get_key_dropdown_values("全部按鍵"):
                        if item.startswith(f"{mapped_key} ("):
                            matched_display = item
                            break
                    key_var.set(matched_display)
                    if btn_detect.winfo_exists():
                        btn_detect.configure(
                            text="點此後按下鍵盤任意鍵自動填入",
                            fg_color=PALETTE["bg_elevated"],
                            text_color=PALETTE["fg_primary"],
                        )

                self._single_key_capture_cb = _on_captured

            btn_detect.configure(command=_start_key_capture)

            quick_row = ctk.CTkFrame(self.param_container, fg_color="transparent")
            quick_row.grid(row=3, column=0, columnspan=2, sticky="ew")
            quick_keys = [
                ("up (↑ 方向鍵上 (Up))", "↑"),
                ("down (↓ 方向鍵下 (Down))", "↓"),
                ("left (← 方向鍵左 (Left))", "←"),
                ("right (→ 方向鍵右 (Right))", "→"),
                ("enter (Enter 確認/換行)", "Enter"),
                ("space (Space 空白鍵)", "Space"),
            ]
            for col_i, (code, label) in enumerate(quick_keys):
                quick_row.grid_columnconfigure(col_i, weight=1)
                ctk.CTkButton(
                    quick_row,
                    text=label,
                    height=28,
                    width=36,
                    corner_radius=RADIUS["pill"],
                    fg_color=PALETTE["bg_elevated"],
                    hover_color=PALETTE["bg_hover"],
                    text_color=PALETTE["fg_primary"],
                    font=self.f_small,
                    command=lambda val=code: key_var.set(val),
                ).grid(row=0, column=col_i, sticky="ew", padx=2)
            return

        # ---- 3. 組合快捷鍵 ----
        if act == "Hotkey Combo":
            ctk.CTkLabel(
                self.param_container, text="組合按鍵", font=self.f_body, text_color=PALETTE["fg_primary"]
            ).grid(row=0, column=0, sticky="w", pady=5, padx=(2, 8))
            hk_var = ctk.StringVar(value=HOTKEY_PRESETS[0])
            self.param_vars["keys"] = hk_var
            self._make_combobox(self.param_container, hk_var, HOTKEY_PRESETS).grid(
                row=0, column=1, sticky="ew", pady=5
            )

            builder_box = ctk.CTkFrame(
                self.param_container,
                fg_color=PALETTE["bg_elevated"],
                corner_radius=RADIUS["button"],
            )
            builder_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 4))

            ctk.CTkLabel(
                builder_box, text="快速組合器", font=self.f_small, text_color=PALETTE["fg_secondary"]
            ).pack(anchor="w", padx=10, pady=(8, 4))

            mod_row = ctk.CTkFrame(builder_box, fg_color="transparent")
            mod_row.pack(fill="x", padx=10, pady=2)
            v_ctrl = ctk.BooleanVar(value=True)
            v_shift = ctk.BooleanVar(value=False)
            v_alt = ctk.BooleanVar(value=False)
            v_win = ctk.BooleanVar(value=False)
            for txt, var in [("Ctrl", v_ctrl), ("Shift", v_shift), ("Alt", v_alt), ("Win", v_win)]:
                ctk.CTkCheckBox(
                    mod_row,
                    text=txt,
                    variable=var,
                    width=62,
                    checkbox_width=18,
                    checkbox_height=18,
                    corner_radius=5,
                    font=self.f_small,
                    text_color=PALETTE["fg_primary"],
                ).pack(side="left", padx=(0, 6))

            sub_row = ctk.CTkFrame(builder_box, fg_color="transparent")
            sub_row.pack(fill="x", padx=10, pady=(8, 10))
            main_key_var = ctk.StringVar(value="c (字母 C)")
            self._make_combobox(sub_row, main_key_var, get_key_dropdown_values("全部按鍵")).pack(
                side="left", fill="x", expand=True, padx=(0, 6)
            )

            def _apply_combo() -> None:
                mods: List[str] = []
                if v_ctrl.get():
                    mods.append("ctrl")
                if v_shift.get():
                    mods.append("shift")
                if v_alt.get():
                    mods.append("alt")
                if v_win.get():
                    mods.append("win")
                mk = extract_clean_token(main_key_var.get())
                if mk:
                    mods.append(mk)
                if mods:
                    hk_var.set("+".join(mods))

            ctk.CTkButton(
                sub_row,
                text="套用",
                width=64,
                height=32,
                corner_radius=RADIUS["button"],
                fg_color=PALETTE["accent"],
                hover_color=PALETTE["accent_hover"],
                text_color="#FFFFFF",
                font=self.f_small,
                command=_apply_combo,
            ).pack(side="right")
            return

        # ---- 4. 其他通用動作 ----
        fields: List[tuple[str, str, Any]] = []
        if act in ("Mouse Click", "Mouse Double Click"):
            fields = [("button", "滑鼠按鍵", MOUSE_BUTTON_OPTIONS[0]), ("x", "X 座標", 500), ("y", "Y 座標", 500)]
        elif act == "Mouse Move":
            fields = [("x", "X 座標", 500), ("y", "Y 座標", 500), ("duration", "移動耗時 (秒)", 0.15)]
        elif act == "Mouse Drag":
            fields = [
                ("start_x", "起點 X", 300),
                ("start_y", "起點 Y", 300),
                ("end_x", "終點 X", 600),
                ("end_y", "終點 Y", 600),
                ("button", "拖曳按鍵", MOUSE_BUTTON_OPTIONS[0]),
                ("duration", "耗時 (秒)", 0.3),
            ]
        elif act == "Mouse Scroll":
            fields = [("clicks", "滾動格數 (+上/-下)", -3), ("x", "X 座標", 500), ("y", "Y 座標", 500)]
        elif act == "Send Text":
            fields = [("text", "輸入文字", "Hello World"), ("interval", "字元間隔 (秒)", 0.02)]
        elif act == "Sleep (Fixed)":
            fields = [("ms", "等待毫秒 (ms)", 1000)]
        elif act == "Sleep (Random)":
            fields = [("min_ms", "最小毫秒", 500), ("max_ms", "最大毫秒", 1500)]
        elif act == "If Pixel Color":
            fields = [
                ("x", "檢測 X", 500),
                ("y", "檢測 Y", 500),
                ("r", "R (0~255)", 255),
                ("g", "G (0~255)", 255),
                ("b", "B (0~255)", 255),
                ("tolerance", "容許色差 (±)", 10),
            ]
        elif act in ("If Image On Screen", "Click Image On Screen"):
            fields = [("image_path", "圖片路徑", "target.png"), ("confidence", "信心度 (0.1~1.0)", 0.85)]
        elif act == "Loop Start":
            fields = [("count", "重複次數", 5)]
        elif act == "Run Command":
            fields = [("command", "系統指令", "notepad.exe")]
        elif act == "Comment":
            fields = [("text", "註解內容", "說明此區塊用途")]

        if not fields:
            ctk.CTkLabel(
                self.param_container,
                text="此流程控制步驟無需額外參數，直接插入即可。",
                font=self.f_body,
                text_color=PALETTE["fg_muted"],
                anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=12, padx=4)
            return

        for row_idx, (key, label_desc, default_val) in enumerate(fields):
            ctk.CTkLabel(
                self.param_container,
                text=label_desc,
                font=self.f_body,
                text_color=PALETTE["fg_primary"],
            ).grid(row=row_idx, column=0, sticky="w", pady=5, padx=(2, 8))

            var = ctk.StringVar(value=str(default_val))
            self.param_vars[key] = var

            if key == "button":
                self._make_combobox(self.param_container, var, MOUSE_BUTTON_OPTIONS).grid(
                    row=row_idx, column=1, sticky="ew", pady=5
                )
            else:
                self._make_entry(self.param_container, var).grid(
                    row=row_idx, column=1, sticky="ew", pady=5
                )

            if key == "image_path":
                self._make_secondary_btn(
                    self.param_container, "瀏覽", lambda v=var: self._browse_image(v), height=32
                ).grid(row=row_idx, column=2, padx=(6, 0), pady=5)

    def _browse_image(self, target_var: ctk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="選擇目標圖片",
            filetypes=[("PNG Images", "*.png"), ("All Images", "*.png;*.jpg;*.bmp")],
        )
        if path:
            target_var.set(path)

    # -------------------- 明確的新增 / 編輯模式切換 --------------------
    def enter_edit_selected_step(self, idx: Optional[int] = None) -> None:
        if idx is None:
            idx = self._get_selected_index()
        if idx is None or not (0 <= idx < len(self.steps)):
            return
        self.editing_index = idx
        self._load_step_into_inspector(idx)

        self.lbl_edit_banner.configure(text=f"正在編輯步驟 #{idx + 1}")
        self.edit_banner.pack(
            side="top", fill="x", padx=12, pady=(12, 0), before=self.left_top_section
        )
        self.lbl_builder_title.configure(text=f"編輯步驟 #{idx + 1}")
        self.btn_submit_step.configure(text="✓ 儲存變更")
        self.action_btn_row.grid_columnconfigure(0, weight=2)
        self.action_btn_row.grid_columnconfigure(1, weight=1)
        self.btn_cancel_edit.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.lbl_builder_hint.configure(text="修改完成後點擊「儲存變更」，或按 Esc 回到新增模式")

    def _exit_edit_mode(self) -> None:
        if self.editing_index is None:
            return
        self.editing_index = None
        self.edit_banner.pack_forget()
        self.lbl_builder_title.configure(text="新增動作")
        self.btn_submit_step.configure(text="＋ 插入步驟")
        self.btn_cancel_edit.grid_forget()
        self.action_btn_row.grid_columnconfigure(1, weight=0)
        self.lbl_builder_hint.configure(text="提示：單擊右側表格僅選取位置，雙擊才載入編輯")

    def _on_submit_step(self) -> None:
        if self.editing_index is not None:
            self._save_editing_step()
        else:
            self.add_step_from_palette()

    def _save_editing_step(self) -> None:
        if self.editing_index is None or not (0 <= self.editing_index < len(self.steps)):
            self._exit_edit_mode()
            return
        idx = self.editing_index
        self._push_undo_snapshot()
        prev_enabled = self.steps[idx].enabled
        updated = self._collect_step_from_palette()
        updated.enabled = prev_enabled
        self.steps[idx] = updated
        self._exit_edit_mode()
        self._refresh_table(select_idx=idx)
        self._log_threadsafe(f"已更新步驟 #{idx + 1}")

    # -------------------- 右欄：巨集動作序列 --------------------
    def _build_right_table(self, parent: ctk.CTkFrame) -> None:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        top_bar = ctk.CTkFrame(inner, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            top_bar, text="巨集動作序列", font=self.f_title, text_color=PALETTE["fg_primary"]
        ).pack(side="left")

        btn_bar = ctk.CTkFrame(top_bar, fg_color="transparent")
        btn_bar.pack(side="right")

        def _ghost_btn(text: str, cmd: Callable[[], None], width: int = 44) -> None:
            ctk.CTkButton(
                btn_bar,
                text=text,
                width=width,
                height=28,
                corner_radius=RADIUS["pill"],
                fg_color="transparent",
                hover_color=PALETTE["bg_hover"],
                text_color=PALETTE["fg_secondary"],
                font=self.f_small,
                command=cmd,
            ).pack(side="left", padx=1)

        def _sec_btn(text: str, cmd: Callable[[], None], width: int = 44) -> None:
            ctk.CTkButton(
                btn_bar,
                text=text,
                width=width,
                height=28,
                corner_radius=RADIUS["pill"],
                fg_color=PALETTE["bg_elevated"],
                hover_color=PALETTE["bg_hover"],
                text_color=PALETTE["fg_primary"],
                border_width=1,
                border_color=PALETTE["border_strong"],
                font=self.f_small,
                command=cmd,
            ).pack(side="left", padx=2)

        _ghost_btn("↶", self.undo, width=30)
        _ghost_btn("↷", self.redo, width=30)
        _sec_btn("編輯", self.enter_edit_selected_step, width=50)
        _sec_btn("↑", lambda: self.move_step(-1), width=30)
        _sec_btn("↓", lambda: self.move_step(1), width=30)
        _ghost_btn("複製", self.copy_selected_steps, width=44)
        _ghost_btn("貼上", self.paste_steps, width=44)
        _ghost_btn("啟/停", self.toggle_step_enabled, width=48)
        _ghost_btn("刪除", self.delete_step, width=44)

        self.step_table = MacroStepTable(
            inner,
            on_selection_change=self._update_count_info,
            on_double_click=self.enter_edit_selected_step,
            on_right_click=self._on_table_right_click,
            on_drag_start=self._push_undo_snapshot,
            on_drag_step=lambda delta: self._move_selected_block(delta, record_undo=False),
        )
        self.step_table.pack(fill="both", expand=True)

    # -------------------- 底部可收合日誌卡片 --------------------
    def _build_bottom_console(self, parent: ctk.CTkFrame) -> None:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=(8, 10))

        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            header, text="執行日誌", font=self.f_small, text_color=PALETTE["fg_secondary"]
        ).pack(side="left")

        self.btn_toggle_log = ctk.CTkButton(
            header,
            text="收合",
            width=48,
            height=24,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=self.f_small,
            command=self.toggle_log_panel,
        )
        self.btn_toggle_log.pack(side="right")

        ctk.CTkButton(
            header,
            text="清除",
            width=48,
            height=24,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=self.f_small,
            command=self._clear_log,
        ).pack(side="right", padx=(0, 2))

        self.txt_log = ctk.CTkTextbox(
            inner,
            height=90,
            corner_radius=RADIUS["input"],
            fg_color=PALETTE["bg_input"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border"],
            font=self.f_mono,
            wrap="word",
        )
        self.txt_log.pack(fill="both", expand=True)

    def _clear_log(self) -> None:
        self.txt_log.delete("1.0", "end")

    def toggle_log_panel(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.txt_log.pack(fill="both", expand=True)
            self.btn_toggle_log.configure(text="收合")
        else:
            self.txt_log.pack_forget()
            self.btn_toggle_log.configure(text="展開")

    # -------------------- 表格資料操作與剪貼簿 --------------------
    def _update_count_info(self) -> None:
        total = len(self.steps)
        sel = len(self._get_selected_indices())
        if sel > 0:
            self.lbl_count_info.configure(text=f"已選 {sel} / 共 {total} 步")
        else:
            self.lbl_count_info.configure(text=f"共 {total} 步")

    def _refresh_table(
        self,
        select_idx: Optional[int] = None,
        select_indices: Optional[List[int]] = None,
    ) -> None:
        self.step_table.set_steps(
            self.steps, select_idx=select_idx, select_indices=select_indices
        )

    def _get_selected_indices(self) -> List[int]:
        return self.step_table.get_selected_indices()

    def _get_selected_index(self) -> Optional[int]:
        indices = self._get_selected_indices()
        return indices[0] if indices else None

    def _select_all_steps(self) -> None:
        self.step_table.select_all()

    def _move_selected_block(self, delta: int, record_undo: bool = True) -> bool:
        indices = self._get_selected_indices()
        if not indices:
            return False
        if delta < 0 and indices[0] == 0:
            return False
        if delta > 0 and indices[-1] >= len(self.steps) - 1:
            return False

        if record_undo:
            self._push_undo_snapshot()

        if delta < 0:
            for idx in indices:
                self.steps[idx - 1], self.steps[idx] = self.steps[idx], self.steps[idx - 1]
            new_indices = [idx - 1 for idx in indices]
        else:
            for idx in reversed(indices):
                self.steps[idx + 1], self.steps[idx] = self.steps[idx], self.steps[idx + 1]
            new_indices = [idx + 1 for idx in indices]

        if self.editing_index is not None:
            self._exit_edit_mode()

        self._refresh_table(select_indices=new_indices)
        return True

    def copy_selected_steps(self) -> None:
        indices = self._get_selected_indices()
        if not indices:
            return
        self.clipboard_steps = [copy.deepcopy(self.steps[i]) for i in indices]
        self._log_threadsafe(f"已複製 {len(self.clipboard_steps)} 個步驟。")

    def cut_selected_steps(self) -> None:
        indices = self._get_selected_indices()
        if not indices:
            return
        self._push_undo_snapshot()
        self.clipboard_steps = [copy.deepcopy(self.steps[i]) for i in indices]
        first_idx = indices[0]
        for idx in reversed(indices):
            del self.steps[idx]
        self._exit_edit_mode()
        next_sel = min(first_idx, len(self.steps) - 1) if self.steps else None
        self._refresh_table(select_idx=next_sel)
        self._log_threadsafe(f"已剪下 {len(self.clipboard_steps)} 個步驟。")

    def paste_steps(self) -> None:
        if not self.clipboard_steps:
            return
        self._push_undo_snapshot()
        indices = self._get_selected_indices()
        insert_pos = (indices[-1] + 1) if indices else len(self.steps)
        cloned = [copy.deepcopy(s) for s in self.clipboard_steps]
        for offset, step in enumerate(cloned):
            self.steps.insert(insert_pos + offset, step)
        new_sel = [insert_pos + offset for offset in range(len(cloned))]
        self._exit_edit_mode()
        self._refresh_table(select_indices=new_sel)
        self._log_threadsafe(f"已貼上 {len(cloned)} 個步驟。")

    def _load_step_into_inspector(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.steps):
            return
        step = self.steps[idx]

        target_cat = None
        for cat, act_list in ACTION_CATEGORIES.items():
            if step.action_type in act_list:
                target_cat = cat
                break
        if target_cat and target_cat != self.active_category:
            self.active_category = target_cat
            self._refresh_category_buttons()
            self.cb_action.configure(
                values=[ACTION_DISPLAY_NAMES.get(a, a) for a in ACTION_CATEGORIES[target_cat]]
            )

        self.var_action.set(ACTION_DISPLAY_NAMES.get(step.action_type, step.action_type))
        self._rebuild_param_fields()

        for k, val in step.params.items():
            if k in self.param_vars:
                if k == "key":
                    clean_k = extract_clean_token(str(val))
                    display_k = str(val)
                    for item in get_key_dropdown_values("全部按鍵"):
                        if item.startswith(f"{clean_k} ("):
                            display_k = item
                            break
                    self.param_vars[k].set(display_k)
                else:
                    self.param_vars[k].set(str(val))

        self.var_delay.set(step.delay_ms)
        self.var_repeat.set(step.repeat)
        self.var_comment.set(step.comment)

    def _collect_step_from_palette(self) -> MacroStep:
        act = resolve_action_type(self.var_action.get())
        raw_params: Dict[str, Any] = {}
        for k, v in self.param_vars.items():
            val_str = str(v.get()).strip()
            if k in (
                "x", "y", "width", "height", "start_x", "start_y", "end_x", "end_y",
                "clicks", "ms", "min_ms", "max_ms", "r", "g", "b", "tolerance", "count",
            ):
                try:
                    raw_params[k] = int(float(val_str))
                except ValueError:
                    raw_params[k] = 0
            elif k in ("duration", "interval", "confidence"):
                try:
                    raw_params[k] = float(val_str)
                except ValueError:
                    raw_params[k] = 0.1
            elif k in ("key", "keys", "button"):
                raw_params[k] = extract_clean_token(val_str)
            else:
                raw_params[k] = val_str

        try:
            delay_val = max(0, int(self.var_delay.get()))
        except Exception:
            delay_val = 0
        try:
            repeat_val = max(1, int(self.var_repeat.get()))
        except Exception:
            repeat_val = 1

        return MacroStep(
            action_type=act,
            params=raw_params,
            delay_ms=delay_val,
            repeat=repeat_val,
            enabled=True,
            comment=self.var_comment.get().strip(),
        )

    def add_step_from_palette(self) -> None:
        self._push_undo_snapshot()
        step = self._collect_step_from_palette()
        indices = self._get_selected_indices()
        if indices:
            insert_pos = indices[-1] + 1
            self.steps.insert(insert_pos, step)
            self._refresh_table(select_idx=insert_pos)
        else:
            self.steps.append(step)
            self._refresh_table(select_idx=len(self.steps) - 1)

    def move_step(self, delta: int) -> None:
        self._move_selected_block(delta, record_undo=True)

    def toggle_step_enabled(self) -> None:
        indices = self._get_selected_indices()
        if not indices:
            return
        self._push_undo_snapshot()
        for idx in indices:
            self.steps[idx].enabled = not self.steps[idx].enabled
        self._refresh_table(select_indices=indices)

    def duplicate_step(self) -> None:
        indices = self._get_selected_indices()
        if not indices:
            return
        self._push_undo_snapshot()
        cloned_list = [copy.deepcopy(self.steps[i]) for i in indices]
        insert_pos = indices[-1] + 1
        for offset, cloned in enumerate(cloned_list):
            self.steps.insert(insert_pos + offset, cloned)
        new_selection = [insert_pos + offset for offset in range(len(cloned_list))]
        self._refresh_table(select_indices=new_selection)

    def delete_step(self) -> None:
        indices = self._get_selected_indices()
        if not indices:
            return
        self._push_undo_snapshot()
        first_idx = indices[0]
        for idx in reversed(indices):
            del self.steps[idx]
        self._exit_edit_mode()
        next_sel = min(first_idx, len(self.steps) - 1) if self.steps else None
        self._refresh_table(select_idx=next_sel)

    def clear_all_steps(self) -> None:
        if not self.steps:
            return
        ok = show_confirm_dialog(
            self.root,
            "確認清空",
            "確定要清空目前所有的巨集步驟嗎？",
            yes_text="清空",
            no_text="取消",
            danger=True,
        )
        if ok:
            self._push_undo_snapshot()
            self.steps.clear()
            self._exit_edit_mode()
            self._refresh_table()

    # -------------------- 鍵盤快捷鍵與全域熱鍵 --------------------
    def _trigger_hotkey_action(
        self, norm_hk: str, callback: Callable[[], None], from_global: bool = False
    ) -> None:
        if self._suspend_hotkeys or self._single_key_capture_cb is not None:
            return
        if self._is_editing_text_widget() and not is_safe_hotkey_while_typing(norm_hk):
            return

        now = time.time()
        if now - self._last_hotkey_trigger_ts < 0.25:
            return
        self._last_hotkey_trigger_ts = now
        callback()

    def _on_window_key_dispatch(self, event: Any) -> Optional[str]:
        if self._suspend_hotkeys:
            return None

        if self._single_key_capture_cb is not None:
            ks = getattr(event, "keysym", "")
            if not ks or ks in MODIFIER_KEYSYMS or ks == "??":
                return "break"
            mapped = TK_KEYSYM_MAP.get(ks, ks.lower())
            cb = self._single_key_capture_cb
            self._single_key_capture_cb = None
            cb(mapped)
            return "break"

        pressed_hk = tk_event_to_hotkey_string(event)
        if not pressed_hk:
            return None

        in_text_input = self._is_editing_text_widget(getattr(event, "widget", None))

        # 檔案快捷鍵
        if pressed_hk == "ctrl+s":
            self.save_project()
            return "break"
        if pressed_hk == "ctrl+shift+s":
            self.save_project_as()
            return "break"
        if pressed_hk == "ctrl+o":
            self.open_project()
            return "break"
        if pressed_hk == "ctrl+n":
            self.new_project()
            return "break"
        if pressed_hk == "ctrl+e":
            self.export_python_script()
            return "break"

        # Escape 取消編輯模式
        if pressed_hk == "esc" and self.editing_index is not None:
            self._exit_edit_mode()
            return "break"

        # 序列編輯快捷鍵（焦點不在文字框時）
        if not in_text_input:
            if pressed_hk == "ctrl+c":
                self.copy_selected_steps()
                return "break"
            if pressed_hk == "ctrl+x":
                self.cut_selected_steps()
                return "break"
            if pressed_hk == "ctrl+v":
                self.paste_steps()
                return "break"
            if pressed_hk == "ctrl+d":
                self.duplicate_step()
                return "break"
            if pressed_hk == "ctrl+a":
                self._select_all_steps()
                return "break"
            if pressed_hk == "ctrl+z":
                self.undo()
                return "break"
            if pressed_hk in ("ctrl+y", "ctrl+shift+z"):
                self.redo()
                return "break"
            if pressed_hk == "delete":
                self.delete_step()
                return "break"
            if pressed_hk == "space":
                self.toggle_step_enabled()
                return "break"
            if pressed_hk == "enter":
                self.enter_edit_selected_step()
                return "break"
            if pressed_hk == "alt+up":
                self.move_step(-1)
                return "break"
            if pressed_hk == "alt+down":
                self.move_step(1)
                return "break"

        matched_cb = self._hotkey_lookup.get(pressed_hk)
        if matched_cb is not None:
            if in_text_input and not is_safe_hotkey_while_typing(pressed_hk):
                return None
            self._trigger_hotkey_action(pressed_hk, matched_cb, from_global=False)
            return "break"

        return None

    def _apply_app_hotkeys(self) -> None:
        action_callbacks: Dict[str, Callable[[], None]] = {
            "play": self.play_macro,
            "pause": self.engine.toggle_pause,
            "stop": self.engine.stop_playback,
            "record": self.toggle_record,
            "stop_record": self.engine.stop_recording,
            "capture_cursor": self.capture_cursor_to_fields,
        }

        self._hotkey_lookup.clear()
        for act_key, cb in action_callbacks.items():
            norm_hk = normalize_hotkey_string(self.app_hotkeys.get(act_key, ""))
            if norm_hk:
                self.app_hotkeys[act_key] = norm_hk
                self._hotkey_lookup[norm_hk] = cb

        self.engine.update_record_hotkeys(
            self.app_hotkeys.get("record", "f9"),
            self.app_hotkeys.get("stop_record", "f10"),
        )

        if self._global_hotkey_listener is not None:
            try:
                self._global_hotkey_listener.stop()
            except Exception:
                pass
            self._global_hotkey_listener = None

        if HAS_PYNPUT and hasattr(pynput_kb, "GlobalHotKeys"):
            pynput_map: Dict[str, Callable[[], None]] = {}
            for act_key, cb in action_callbacks.items():
                norm_hk = self.app_hotkeys.get(act_key, "")
                p_seq = hotkey_to_pynput_sequence(norm_hk)
                if p_seq:
                    pynput_map[p_seq] = (
                        lambda hk=norm_hk, fn=cb: self.root.after(
                            0, lambda: self._trigger_hotkey_action(hk, fn, from_global=True)
                        )
                    )
            if pynput_map:
                try:
                    self._global_hotkey_listener = pynput_kb.GlobalHotKeys(pynput_map)
                    self._global_hotkey_listener.daemon = True
                    self._global_hotkey_listener.start()
                except Exception:
                    self._global_hotkey_listener = None

        d_play = format_hotkey_display(self.app_hotkeys.get("play", "f5"))
        d_pause = format_hotkey_display(self.app_hotkeys.get("pause", "f7"))
        d_stop = format_hotkey_display(self.app_hotkeys.get("stop", "f6"))
        d_rec = format_hotkey_display(self.app_hotkeys.get("record", "f9"))
        d_cap = format_hotkey_display(self.app_hotkeys.get("capture_cursor", "f2"))

        self.btn_play.configure(text=f"▶ 播放 ({d_play})")
        self.btn_record.configure(text=f"● 錄製 ({d_rec})")
        self.btn_capture_cursor.configure(text=f"吸取座標 ({d_cap})")
        self.lbl_hotkey_summary.configure(
            text=f"{d_play} 播放 · {d_pause} 暫停 · {d_stop} 停止 · {d_rec} 錄製"
        )

    def open_hotkey_settings_dialog(self) -> None:
        self._suspend_hotkeys = True

        def _on_save(new_map: Dict[str, str]) -> None:
            self.app_hotkeys = new_map
            self._apply_app_hotkeys()
            self._log_threadsafe("已更新自定義快捷鍵。")

        def _on_close() -> None:
            self._suspend_hotkeys = False

        HotkeySettingsDialog(
            parent=self.root,
            current_hotkeys=self.app_hotkeys,
            on_save=_on_save,
            on_close=_on_close,
        )

    # -------------------- 游標座標吸管 (背景執行緒非同步輪詢，避免阻塞 UI 縮放) --------------------
    def _start_cursor_tracker(self) -> None:
        if not HAS_PYAUTOGUI:
            return

        def _worker() -> None:
            last_state: Optional[tuple[int, int, int, int, int]] = None
            while not self._cursor_stop_event.is_set():
                try:
                    x, y = pyautogui.position()
                    r, g, b = pyautogui.pixel(x, y)
                    cur = (int(x), int(y), int(r), int(g), int(b))
                    if cur != last_state:
                        last_state = cur
                        hex_color = f"#{cur[2]:02x}{cur[3]:02x}{cur[4]:02x}"
                        txt = f"X={cur[0]}, Y={cur[1]} | RGB({cur[2]},{cur[3]},{cur[4]})"

                        def _apply(hc: str = hex_color, t: str = txt) -> None:
                            if self.root.winfo_exists():
                                self.color_swatch.configure(fg_color=hc)
                                self.lbl_cursor.configure(text=t)

                        self.root.after(0, _apply)
                except Exception:
                    pass
                self._cursor_stop_event.wait(0.16)

        threading.Thread(target=_worker, daemon=True).start()

    def capture_cursor_to_fields(self) -> None:
        if not HAS_PYAUTOGUI:
            self._log_threadsafe("[提示] 未安裝 PyAutoGUI，無法讀取即時座標。")
            return
        try:
            x, y = pyautogui.position()
            r, g, b = pyautogui.pixel(x, y)
            if "x" in self.param_vars:
                self.param_vars["x"].set(str(x))
            if "y" in self.param_vars:
                self.param_vars["y"].set(str(y))
            if "r" in self.param_vars:
                self.param_vars["r"].set(str(r))
            if "g" in self.param_vars:
                self.param_vars["g"].set(str(g))
            if "b" in self.param_vars:
                self.param_vars["b"].set(str(b))
            self._log_threadsafe(f"已吸取座標 ({x}, {y}) 與顏色 RGB({r}, {g}, {b})")
        except Exception as exc:
            self._log_threadsafe(f"[錯誤] 吸取座標失敗: {exc}")

    # -------------------- 錄製與播放 --------------------
    def toggle_record(self) -> None:
        if self.engine.is_recording:
            self.engine.stop_recording()
        else:
            stop_hint = format_hotkey_display(self.app_hotkeys.get("stop_record", "f10"))
            rec_hint = format_hotkey_display(self.app_hotkeys.get("record", "f9"))
            self.engine.start_recording(
                record_moves=self.var_rec_moves.get(),
                stop_hotkey_hint=f"{rec_hint} / {stop_hint}",
            )

    def play_macro(self) -> None:
        try:
            speed = float(self.var_speed.get())
        except ValueError:
            speed = 1.0
        try:
            loops = max(0, int(self.var_loops.get()))
        except Exception:
            loops = 1
        self.engine.start_playback(self.steps, loop_count=loops, speed_factor=speed)

    # -------------------- 專案開啟、儲存、自動載入上次存檔 --------------------
    def _load_initial_project(self, cli_project: Optional[str] = None) -> None:
        # 1. 優先載入命令列 --project 指定檔案
        if cli_project and os.path.isfile(cli_project):
            if self._load_project_file(cli_project, silent=True):
                self._log_threadsafe(f"已載入指定專案: {cli_project}")
                return

        # 2. 自動載入上次開啟 / 儲存的存檔
        last_path = self.config.get_last_project_path()
        if last_path and os.path.isfile(last_path):
            if self._load_project_file(last_path, silent=True):
                self._log_threadsafe(f"已自動開啟上次使用的存檔: {last_path}")
                return

        # 3. 否則載入預設範例
        self._load_sample_macro()

    def _confirm_discard_unsaved(self) -> bool:
        if not self.is_dirty:
            return True
        res = show_confirm_dialog(
            self.root,
            "尚未儲存",
            "目前專案有未儲存的變更，是否要先儲存？",
            yes_text="儲存",
            no_text="不儲存",
            allow_cancel=True,
        )
        if res is None:
            return False
        if res is True:
            return self.save_project()
        return True

    def _on_app_close(self) -> None:
        if not self._confirm_discard_unsaved():
            return

        # 儲存視窗大小、錄製設定與目前開啟的存檔路徑
        try:
            self.config.set_window_geometry(self.root.geometry().split("+")[0])
        except Exception:
            pass
        self.config.set_record_mouse_moves(self.var_rec_moves.get())
        if self.current_file and os.path.isfile(self.current_file):
            self.config.set_last_project_path(self.current_file)

        CTkPopupMenu.dismiss_active()
        self._cursor_stop_event.set()
        self._destroy_floating_window()
        if self._global_hotkey_listener is not None:
            try:
                self._global_hotkey_listener.stop()
            except Exception:
                pass
        self.engine.stop_playback()
        self.engine.stop_recording()
        self.root.destroy()

    def new_project(self) -> None:
        if not self._confirm_discard_unsaved():
            return
        self.steps.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_file = None
        self._exit_edit_mode()
        self._refresh_table()
        self._mark_dirty(False)
        self._log_threadsafe("已建立空白專案。")

    def _write_project_file(self, path: str) -> bool:
        try:
            loops_val = int(self.var_loops.get())
        except Exception:
            loops_val = 1
        try:
            speed_val = float(self.var_speed.get())
        except Exception:
            speed_val = 1.0

        payload = {
            "version": "4.0",
            "created_at": datetime.now().isoformat(),
            "loop_count": loops_val,
            "speed_factor": speed_val,
            "hotkeys": self.app_hotkeys,
            "steps": [asdict(s) for s in self.steps],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.current_file = os.path.abspath(path)
            self.config.set_last_project_path(self.current_file)
            self._mark_dirty(False)
            self._log_threadsafe(f"已儲存至: {self.current_file}")
            return True
        except Exception as exc:
            show_message_dialog(self.root, "儲存失敗", f"無法儲存檔案：\n{exc}", kind="error")
            return False

    def save_project(self) -> bool:
        if self.current_file:
            return self._write_project_file(self.current_file)
        return self.save_project_as()

    def save_project_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="儲存巨集專案",
            defaultextension=".pmc.json",
            filetypes=[("PyMacroCreator Project", "*.pmc.json"), ("JSON Files", "*.json")],
        )
        if not path:
            return False
        return self._write_project_file(path)

    def _load_project_file(self, path: str, silent: bool = False) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_loops.set(int(data.get("loop_count", 1)))
            speed_str = str(data.get("speed_factor", 1.0))
            self.var_speed.set(speed_str)
            if "hotkeys" in data and isinstance(data["hotkeys"], dict):
                for k in DEFAULT_APP_HOTKEYS:
                    if k in data["hotkeys"]:
                        norm = normalize_hotkey_string(str(data["hotkeys"][k]))
                        if norm:
                            self.app_hotkeys[k] = norm
                self._apply_app_hotkeys()
            self.steps = [MacroStep(**item) for item in data.get("steps", [])]
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.current_file = os.path.abspath(path)
            self.config.set_last_project_path(self.current_file)
            self._exit_edit_mode()
            self._refresh_table()
            self._mark_dirty(False)
            if not silent:
                self._log_threadsafe(f"已載入專案: {self.current_file} (共 {len(self.steps)} 步)")
            return True
        except Exception as exc:
            if not silent:
                show_message_dialog(self.root, "開啟失敗", f"無法讀取專案檔案：\n{exc}", kind="error")
            else:
                self._log_threadsafe(f"[警告] 無法自動載入上次存檔 ({path}): {exc}")
            return False

    def open_project(self) -> None:
        if not self._confirm_discard_unsaved():
            return
        path = filedialog.askopenfilename(
            title="開啟巨集專案",
            filetypes=[("PyMacroCreator Project", "*.pmc.json"), ("JSON Files", "*.json")],
        )
        if not path:
            return
        self._load_project_file(path, silent=False)

    def export_python_script(self) -> None:
        path = filedialog.asksaveasfilename(
            title="匯出獨立 Python 腳本 (.py)",
            defaultextension=".py",
            filetypes=[("Python Script", "*.py")],
        )
        if not path:
            return
        try:
            loops_val = int(self.var_loops.get())
        except Exception:
            loops_val = 1
        try:
            speed_val = float(self.var_speed.get())
        except Exception:
            speed_val = 1.0

        code = PythonScriptExporter.generate_code(
            self.steps, loop_count=loops_val, speed_factor=speed_val
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        self._log_threadsafe(f"已匯出獨立腳本: {path}")
        show_message_dialog(
            self.root, "匯出成功", f"已匯出獨立可執行腳本至：\n{path}", kind="info"
        )

    # -------------------- 預設範例與執行緒安全更新 --------------------
    def _load_sample_macro(self) -> None:
        self.steps = get_default_sample_steps()
        self._refresh_table()
        self._log_threadsafe(
            "PyMacroCreator v4.0 就緒。支援 Ctrl+C/V/X/D/Z/Y 編輯步驟，雙擊步驟可進入編輯模式。"
        )

    def _log_threadsafe(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")

        def _append() -> None:
            if not self.root.winfo_exists():
                return
            self.txt_log.insert("end", f"[{ts}] {msg}\n")
            self.txt_log.see("end")

        self.root.after(0, _append)

    def _highlight_step_threadsafe(self, idx: int) -> None:
        def _sel() -> None:
            if self.root.winfo_exists():
                self.step_table.highlight_index(idx)

        self.root.after(0, _sel)

    def _append_recorded_step_threadsafe(self, step: MacroStep) -> None:
        def _add() -> None:
            if not self.root.winfo_exists():
                return
            self.steps.append(step)
            self._mark_dirty(True)
            self._refresh_table(select_idx=len(self.steps) - 1)

        self.root.after(0, _add)

    def _update_state_badge(self, state: str) -> None:
        self._current_engine_state = state
        badge_map = {
            "Ready": ("● 就緒", "success"),
            "Playing": ("▶ 播放中", "accent"),
            "Paused": ("⏸ 已暫停", "warning"),
            "Recording": ("● 錄製中", "danger"),
        }
        txt, col_key = badge_map.get(state, (f"● {state}", "fg_muted"))
        self.lbl_state.configure(text=txt, fg_color=resolve_color(col_key, self.theme_mode))
        if self.floating_win is not None and self.floating_win.winfo_exists():
            self.floating_win.update_state(state, self.theme_mode)

    def _update_state_threadsafe(self, state: str) -> None:
        self.root.after(0, lambda: self._update_state_badge(state) if self.root.winfo_exists() else None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PyMacroCreator v4.0 — 現代極簡扁平化 Python 巨集錄製與自動化工作站"
    )
    parser.add_argument("--project", "-p", type=str, help="載入指定的 .pmc.json 巨集專案檔")
    parser.add_argument("--run", action="store_true", help="以命令列模式直接執行指定的巨集專案")
    parser.add_argument("--export", "-e", type=str, help="將巨集專案匯出為獨立 .py 腳本路徑")
    args = parser.parse_args()

    if args.run or args.export:
        if args.project and os.path.exists(args.project):
            with open(args.project, "r", encoding="utf-8") as f:
                data = json.load(f)
            steps = [MacroStep(**s) for s in data.get("steps", [])]
            loops = int(data.get("loop_count", 1))
            speed = float(data.get("speed_factor", 1.0))
        else:
            steps = get_default_sample_steps()
            loops = 1
            speed = 1.0

        if args.export:
            code = PythonScriptExporter.generate_code(steps, loop_count=loops, speed_factor=speed)
            with open(args.export, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"[PyMacroCreator] 已匯出獨立腳本至: {args.export}")
        if args.run:
            engine = MacroEngine(
                on_log=lambda m: print(m),
                on_step_highlight=lambda idx: None,
                on_recorded_step=lambda s: None,
                on_state_change=lambda st: None,
            )
            engine.start_playback(steps, loop_count=loops, speed_factor=speed, blocking=True)
        return

    if not HAS_CTK:
        print("錯誤: 尚未安裝 customtkinter 套件，請先執行：pip install customtkinter")
        return

    root = ctk.CTk()
    PyMacroCreatorApp(root, initial_project=args.project)
    root.mainloop()


if __name__ == "__main__":
    main()
