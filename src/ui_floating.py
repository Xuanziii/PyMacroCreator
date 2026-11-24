#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 置頂懸浮快捷控制列 (FloatingControlWindow)
提供極簡微圓角懸浮條，可自由拖曳位置，隨時快速「播放」與「停止」巨集。
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple
import customtkinter as ctk

from src.ui_theme import PALETTE, RADIUS, UI_FONT_FAMILY, resolve_color


class FloatingControlWindow(ctk.CTkToplevel):
    """極簡置頂懸浮控制視窗（含狀態指示、播放、停止與拖曳移動）。"""

    def __init__(
        self,
        parent: Any,
        on_play: Callable[[], None],
        on_stop: Callable[[], None],
        on_close_request: Callable[[], None],
        initial_pos: Optional[Tuple[int, int]] = None,
        initial_state: str = "Ready",
        theme_mode: str = "dark",
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=PALETTE["border_strong"])

        self._on_play = on_play
        self._on_stop = on_stop
        self._on_close_request = on_close_request
        self._theme_mode = theme_mode
        self._engine_state = initial_state

        self._drag_offset_x = 0
        self._drag_offset_y = 0

        self.f_pill = ctk.CTkFont(family=UI_FONT_FAMILY, size=11, weight="bold")
        self.f_btn = ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold")
        self.f_grip = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)

        self._build_ui()
        self.update_state(initial_state, theme_mode)

        self.update_idletasks()
        w = max(276, self.winfo_reqwidth())
        h = max(48, self.winfo_reqheight())
        if initial_pos is not None:
            px, py = initial_pos
        else:
            sw = self.winfo_screenwidth()
            px = max(20, sw - w - 36)
            py = 40
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.deiconify()

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=PALETTE["bg_surface"],
            corner_radius=RADIUS["card"],
            border_width=1,
            border_color=PALETTE["border_strong"],
        )
        card.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=7)

        self.lbl_grip = ctk.CTkLabel(
            inner,
            text="⋮⋮",
            font=self.f_grip,
            text_color=PALETTE["fg_muted"],
            width=16,
            cursor="fleur",
        )
        self.lbl_grip.pack(side="left", padx=(0, 6))

        self.lbl_status = ctk.CTkLabel(
            inner,
            text="● 就緒",
            font=self.f_pill,
            fg_color=resolve_color("success", self._theme_mode),
            text_color="#FFFFFF",
            corner_radius=RADIUS["badge"],
            width=72,
            height=28,
            cursor="fleur",
        )
        self.lbl_status.pack(side="left", padx=(0, 8))

        self.btn_play = ctk.CTkButton(
            inner,
            text="▶ 播放",
            width=76,
            height=30,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["success"],
            hover_color=PALETTE["success_hover"],
            text_color="#FFFFFF",
            font=self.f_btn,
            command=self._on_play,
        )
        self.btn_play.pack(side="left", padx=(0, 5))

        self.btn_stop = ctk.CTkButton(
            inner,
            text="■ 停止",
            width=76,
            height=30,
            corner_radius=RADIUS["button"],
            fg_color=PALETTE["danger"],
            hover_color=PALETTE["danger_hover"],
            text_color="#FFFFFF",
            font=self.f_btn,
            command=self._on_stop,
        )
        self.btn_stop.pack(side="left", padx=(0, 6))

        self.btn_close = ctk.CTkButton(
            inner,
            text="✕",
            width=26,
            height=26,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_muted"],
            font=self.f_grip,
            command=self._on_close_request,
        )
        self.btn_close.pack(side="right")

        for drag_w in (card, inner, self.lbl_grip, self.lbl_status):
            drag_w.bind("<ButtonPress-1>", self._start_drag)
            drag_w.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event: Any) -> None:
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _on_drag(self, event: Any) -> None:
        nx = event.x_root - self._drag_offset_x
        ny = event.y_root - self._drag_offset_y
        self.geometry(f"+{nx}+{ny}")

    def get_position(self) -> Tuple[int, int]:
        return (self.winfo_x(), self.winfo_y())

    def update_state(self, state: str, theme_mode: str) -> None:
        self._engine_state = state
        self._theme_mode = theme_mode
        badge_map = {
            "Ready": ("● 就緒", "success"),
            "Playing": ("▶ 播放", "accent"),
            "Paused": ("⏸ 暫停", "warning"),
            "Recording": ("● 錄製", "danger"),
        }
        txt, col_key = badge_map.get(state, (f"● {state}", "fg_muted"))
        self.lbl_status.configure(text=txt, fg_color=resolve_color(col_key, theme_mode))
