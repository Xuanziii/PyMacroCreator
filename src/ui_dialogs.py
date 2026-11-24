#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 純 CustomTkinter 現代微圓角對話框
包含：
1. HotkeySettingsDialog: 自定義全域與視窗快捷鍵設定視窗
2. show_confirm_dialog / show_message_dialog: 支援深淺主題的極簡確認與提示視窗
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from src.macro_core import (
    DEFAULT_APP_HOTKEYS,
    HOTKEY_ACTION_LABELS,
    format_hotkey_display,
    normalize_hotkey_string,
    tk_event_to_hotkey_string,
)
from src.ui_theme import PALETTE, RADIUS, UI_FONT_FAMILY


def _center_toplevel(dlg: ctk.CTkToplevel, parent: Any, width: int, height: int) -> None:
    dlg.update_idletasks()
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + max(0, (pw - width) // 2)
        y = py + max(0, (ph - height) // 2)
    except Exception:
        x = (dlg.winfo_screenwidth() - width) // 2
        y = (dlg.winfo_screenheight() - height) // 2
    dlg.geometry(f"{width}x{height}+{x}+{y}")


def show_message_dialog(
    parent: Any,
    title: str,
    message: str,
    kind: str = "info",
) -> None:
    """純 CustomTkinter 提示對話框 (info / warning / error)。"""
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.configure(fg_color=PALETTE["bg_surface"])
    dlg.transient(parent)
    dlg.grab_set()

    accent = (
        PALETTE["danger"]
        if kind == "error"
        else (PALETTE["warning"] if kind == "warning" else PALETTE["accent"])
    )

    body = ctk.CTkFrame(dlg, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=22, pady=20)

    ctk.CTkLabel(
        body,
        text=title,
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=14, weight="bold"),
        text_color=PALETTE["fg_primary"],
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    ctk.CTkLabel(
        body,
        text=message,
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12),
        text_color=PALETTE["fg_secondary"],
        anchor="w",
        justify="left",
        wraplength=360,
    ).pack(fill="x", pady=(0, 18))

    ctk.CTkButton(
        body,
        text="確定",
        width=92,
        height=32,
        corner_radius=RADIUS["button"],
        fg_color=accent,
        hover_color=PALETTE["accent_hover"] if kind == "info" else accent,
        text_color="#FFFFFF",
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold"),
        command=dlg.destroy,
    ).pack(anchor="e")

    _center_toplevel(dlg, parent, 410, 175)
    dlg.bind("<Return>", lambda _e: dlg.destroy())
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.wait_window()


def show_confirm_dialog(
    parent: Any,
    title: str,
    message: str,
    yes_text: str = "確定",
    no_text: str = "取消",
    allow_cancel: bool = False,
    danger: bool = False,
) -> Optional[bool]:
    """
    純 CustomTkinter 確認對話框。
    - allow_cancel=False: 回傳 True (是) 或 False (否)
    - allow_cancel=True:  回傳 True (儲存)、False (不儲存)、None (取消)
    """
    result: List[Optional[bool]] = [None if allow_cancel else False]

    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.configure(fg_color=PALETTE["bg_surface"])
    dlg.transient(parent)
    dlg.grab_set()

    body = ctk.CTkFrame(dlg, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=22, pady=20)

    ctk.CTkLabel(
        body,
        text=title,
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=14, weight="bold"),
        text_color=PALETTE["fg_primary"],
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    ctk.CTkLabel(
        body,
        text=message,
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12),
        text_color=PALETTE["fg_secondary"],
        anchor="w",
        justify="left",
        wraplength=370,
    ).pack(fill="x", pady=(0, 20))

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    btn_row.pack(fill="x")

    def _choose(val: Optional[bool]) -> None:
        result[0] = val
        dlg.destroy()

    if allow_cancel:
        ctk.CTkButton(
            btn_row,
            text="取消",
            width=82,
            height=32,
            corner_radius=RADIUS["button"],
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12),
            command=lambda: _choose(None),
        ).pack(side="left")

    ctk.CTkButton(
        btn_row,
        text=yes_text,
        width=92,
        height=32,
        corner_radius=RADIUS["button"],
        fg_color=PALETTE["danger"] if danger else PALETTE["accent"],
        hover_color=PALETTE["danger_hover"] if danger else PALETTE["accent_hover"],
        text_color="#FFFFFF",
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold"),
        command=lambda: _choose(True),
    ).pack(side="right")

    ctk.CTkButton(
        btn_row,
        text=no_text,
        width=92,
        height=32,
        corner_radius=RADIUS["button"],
        fg_color=PALETTE["bg_elevated"],
        hover_color=PALETTE["bg_hover"],
        text_color=PALETTE["fg_primary"],
        border_width=1,
        border_color=PALETTE["border_strong"],
        font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12),
        command=lambda: _choose(False),
    ).pack(side="right", padx=(0, 8))

    _center_toplevel(dlg, parent, 420, 175)
    dlg.protocol("WM_DELETE_WINDOW", lambda: _choose(None if allow_cancel else False))
    dlg.bind("<Escape>", lambda _e: _choose(None if allow_cancel else False))
    dlg.wait_window()
    return result[0]


class HotkeySettingsDialog(ctk.CTkToplevel):
    """純 CustomTkinter 自定義快捷鍵設定視窗。"""

    def __init__(
        self,
        parent: Any,
        current_hotkeys: Dict[str, str],
        on_save: Callable[[Dict[str, str]], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.title("自定義快捷鍵設定")
        self.resizable(False, False)
        self.configure(fg_color=PALETTE["bg_surface"])
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        self._on_close = on_close
        self._temp_vars: Dict[str, ctk.StringVar] = {}
        self._active_capture: Optional[Tuple[ctk.CTkButton, ctk.StringVar]] = None

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<KeyPress>", self._on_key_press)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=22)
        container.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            container,
            text="自定義全域與視窗快捷鍵",
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=15, weight="bold"),
            text_color=PALETTE["fg_primary"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="點擊「設定」後直接按下鍵盤組合（建議使用 F1~F12 或 Ctrl/Alt 組合鍵）",
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=11),
            text_color=PALETTE["fg_secondary"],
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        font_lbl = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)
        font_btn = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)

        for row_idx, (act_key, label_text) in enumerate(HOTKEY_ACTION_LABELS.items(), start=2):
            ctk.CTkLabel(
                container,
                text=label_text,
                font=font_lbl,
                text_color=PALETTE["fg_primary"],
                anchor="w",
            ).grid(row=row_idx, column=0, sticky="w", pady=6, padx=(0, 12))

            var = ctk.StringVar(value=current_hotkeys.get(act_key, ""))
            self._temp_vars[act_key] = var

            ctk.CTkEntry(
                container,
                textvariable=var,
                height=32,
                corner_radius=RADIUS["input"],
                fg_color=PALETTE["bg_input"],
                border_color=PALETTE["border_strong"],
                border_width=1,
                text_color=PALETTE["fg_primary"],
                font=font_lbl,
            ).grid(row=row_idx, column=1, sticky="ew", pady=6, padx=4)

            btn_cap = ctk.CTkButton(
                container,
                text="設定",
                width=78,
                height=32,
                corner_radius=RADIUS["button"],
                fg_color=PALETTE["bg_elevated"],
                hover_color=PALETTE["bg_hover"],
                text_color=PALETTE["fg_primary"],
                border_width=1,
                border_color=PALETTE["border_strong"],
                font=font_btn,
            )
            btn_cap.grid(row=row_idx, column=2, sticky="ew", pady=6, padx=(6, 0))
            btn_cap.configure(command=lambda b=btn_cap, v=var: self._start_capture(b, v))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.grid(
            row=len(HOTKEY_ACTION_LABELS) + 2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(20, 0),
        )

        ctk.CTkButton(
            footer,
            text="恢復預設",
            width=92,
            height=34,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["bg_elevated"],
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_primary"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            font=font_btn,
            command=self._reset_defaults,
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            text="儲存套用",
            width=100,
            height=34,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold"),
            command=self._save_and_close,
        ).pack(side="right")

        ctk.CTkButton(
            footer,
            text="取消",
            width=80,
            height=34,
            corner_radius=RADIUS["button"],
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=font_btn,
            command=self._close,
        ).pack(side="right", padx=(0, 8))

        _center_toplevel(self, parent, 530, 445)

    def _start_capture(self, btn: ctk.CTkButton, var: ctk.StringVar) -> None:
        if self._active_capture is not None:
            prev_b, _ = self._active_capture
            if prev_b.winfo_exists():
                prev_b.configure(text="設定", fg_color=PALETTE["bg_elevated"], text_color=PALETTE["fg_primary"])
        btn.configure(text="請按鍵...", fg_color=PALETTE["accent"], text_color="#FFFFFF")
        self.focus_set()
        self._active_capture = (btn, var)

    def _on_key_press(self, event: Any) -> Optional[str]:
        if self._active_capture is None:
            return None
        btn_target, var_target = self._active_capture
        hk_combo = tk_event_to_hotkey_string(event)
        if not hk_combo:
            return "break"
        var_target.set(hk_combo)
        if btn_target.winfo_exists():
            btn_target.configure(text="設定", fg_color=PALETTE["bg_elevated"], text_color=PALETTE["fg_primary"])
        self._active_capture = None
        return "break"

    def _reset_defaults(self) -> None:
        self._active_capture = None
        for k, default_v in DEFAULT_APP_HOTKEYS.items():
            if k in self._temp_vars:
                self._temp_vars[k].set(default_v)

    def _save_and_close(self) -> None:
        new_map: Dict[str, str] = {}
        seen: Dict[str, str] = {}
        for k, v in self._temp_vars.items():
            cleaned = normalize_hotkey_string(v.get())
            if not cleaned:
                show_message_dialog(
                    self,
                    "格式錯誤",
                    f"「{HOTKEY_ACTION_LABELS[k]}」的快捷鍵不可為空！",
                    kind="warning",
                )
                return
            if cleaned in seen:
                show_message_dialog(
                    self,
                    "快捷鍵衝突",
                    f"快捷鍵 '{format_hotkey_display(cleaned)}' 重複指定，請更換按鍵！",
                    kind="warning",
                )
                return
            seen[cleaned] = k
            new_map[k] = cleaned

        self._on_save(new_map)
        self._close()

    def _close(self) -> None:
        self._on_close()
        if self.winfo_exists():
            self.destroy()
