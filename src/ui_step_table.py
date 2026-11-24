#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 高效能虛擬化 Canvas 巨集步驟表格 (MacroStepTable)
特點：
- 使用單一 tk.Canvas + CTkScrollbar 虛擬化繪製可見列，徹底消除大量 CTk 元件在視窗縮放時的重繪卡頓。
- 保留完整微圓角卡片列外觀、深淺雙主題即時切換、流程縮排與動作語意色彩。
- 支援單選 / Ctrl 多選 / Shift 區間選取 / 全選、滑鼠拖曳排序、雙擊編輯與右鍵選單。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import customtkinter as ctk

from src.macro_core import MacroStep
from src.ui_theme import PALETTE, RADIUS, UI_FONT_FAMILY, resolve_color


def _create_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    r: float,
    **kwargs: Any,
) -> int:
    """在 tk.Canvas 上繪製平滑微圓角矩形。"""
    r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class MacroStepTable(ctk.CTkFrame):
    """高效能虛擬化 Canvas 巨集步驟清單表格。"""

    # (key, header_text, min_or_fixed_width, flex_weight, anchor)
    COL_SPECS: List[Tuple[str, str, int, int, str]] = [
        ("idx", "#", 38, 0, "center"),
        ("enabled", "狀態", 44, 0, "center"),
        ("type", "動作類型", 168, 0, "w"),
        ("details", "參數明細", 220, 3, "w"),
        ("delay", "延遲", 72, 0, "e"),
        ("repeat", "次數", 48, 0, "center"),
        ("comment", "備註", 110, 1, "w"),
    ]

    ROW_HEIGHT = 34
    ROW_GAP = 3
    ROW_STRIDE = ROW_HEIGHT + ROW_GAP

    def __init__(
        self,
        master: Any,
        on_selection_change: Callable[[], None],
        on_double_click: Callable[[int], None],
        on_right_click: Callable[[Any, int], None],
        on_drag_start: Callable[[], None],
        on_drag_step: Callable[[int], bool],
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_selection_change = on_selection_change
        self.on_double_click = on_double_click
        self.on_right_click = on_right_click
        self.on_drag_start = on_drag_start
        self.on_drag_step = on_drag_step

        self._steps: List[MacroStep] = []
        self._indents: List[int] = []
        self._selected: Set[int] = set()
        self._anchor: Optional[int] = None
        self._hover_idx: Optional[int] = None
        self._scroll_top: float = 0.0  # pixel offset from top

        # 拖曳狀態
        self._drag_active: bool = False
        self._drag_snapshot_taken: bool = False
        self._drag_last_row: Optional[int] = None

        # 重繪排程節流
        self._redraw_pending: bool = False

        self._fonts: Dict[str, Any] = {
            "header": ctk.CTkFont(family=UI_FONT_FAMILY, size=11, weight="bold"),
            "normal": (UI_FONT_FAMILY, 9),
            "bold": (UI_FONT_FAMILY, 9, "bold"),
            "italic": (UI_FONT_FAMILY, 9, "italic"),
            "small": (UI_FONT_FAMILY, 8),
            "empty": (UI_FONT_FAMILY, 10),
        }

        self._build_header()
        self._build_body()

    @staticmethod
    def _current_mode() -> str:
        return "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"

    def _c(self, key: str) -> str:
        return resolve_color(key, self._current_mode())

    def _build_header(self) -> None:
        self.header_frame = ctk.CTkFrame(
            self,
            height=32,
            corner_radius=RADIUS["row"],
            fg_color=PALETTE["bg_elevated"],
        )
        self.header_frame.pack(fill="x", pady=(0, 4))
        self.header_frame.grid_propagate(False)

        for col_idx, (_key, title, width, weight, anchor) in enumerate(self.COL_SPECS):
            self.header_frame.grid_columnconfigure(
                col_idx, weight=weight, minsize=width if weight == 0 else max(80, width // 2)
            )
            lbl = ctk.CTkLabel(
                self.header_frame,
                text=title,
                font=self._fonts["header"],
                text_color=PALETTE["fg_secondary"],
                anchor=anchor,
                width=width if weight == 0 else 10,
            )
            padx = (8, 4) if col_idx == 0 else ((4, 18) if col_idx == len(self.COL_SPECS) - 1 else (4, 4))
            lbl.grid(row=0, column=col_idx, sticky="ew", padx=padx, pady=5)

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            body,
            bg=self._c("bg_surface"),
            highlightthickness=0,
            bd=0,
        )
        self.scrollbar = ctk.CTkScrollbar(
            body,
            orientation="vertical",
            command=self._on_scrollbar,
            button_color=PALETTE["scrollbar_fg"],
            button_hover_color=PALETTE["scrollbar_hover"],
        )

        self.scrollbar.pack(side="right", fill="y", padx=(4, 0))
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

    def refresh_theme(self) -> None:
        """主題切換時重繪 Canvas 背景與列色彩。"""
        self.canvas.configure(bg=self._c("bg_surface"))
        self._schedule_redraw()

    # -------------------- 欄位幾何計算 --------------------
    def _compute_columns(self, total_w: int) -> List[Tuple[int, int, str]]:
        """回傳每欄 (x_start, col_width, anchor)。"""
        usable_w = max(320, total_w - 8)
        fixed_total = sum(w for _, _, w, weight, _ in self.COL_SPECS if weight == 0)
        flex_base = sum(w for _, _, w, weight, _ in self.COL_SPECS if weight > 0)
        flex_weight_sum = sum(weight for _, _, _, weight, _ in self.COL_SPECS if weight > 0)
        extra = max(0, usable_w - fixed_total - flex_base)

        cols: List[Tuple[int, int, str]] = []
        cursor = 4
        for _key, _title, base_w, weight, anchor in self.COL_SPECS:
            if weight == 0:
                cw = base_w
            else:
                cw = base_w + int(extra * (weight / max(1, flex_weight_sum)))
            cols.append((cursor, cw, anchor))
            cursor += cw
        return cols

    # -------------------- 捲動控制 --------------------
    def _total_content_height(self) -> int:
        return len(self._steps) * self.ROW_STRIDE + 4

    def _clamp_scroll(self) -> None:
        ch = max(1, self.canvas.winfo_height())
        total_h = self._total_content_height()
        max_top = max(0.0, float(total_h - ch))
        self._scroll_top = max(0.0, min(self._scroll_top, max_top))
        if total_h <= ch:
            self.scrollbar.set(0.0, 1.0)
        else:
            first = self._scroll_top / total_h
            last = min(1.0, (self._scroll_top + ch) / total_h)
            self.scrollbar.set(first, last)

    def _on_scrollbar(self, action: str, *args: Any) -> None:
        ch = max(1, self.canvas.winfo_height())
        total_h = self._total_content_height()
        if action == "moveto":
            frac = float(args[0])
            self._scroll_top = frac * total_h
        elif action == "scroll":
            units = int(args[0])
            what = args[1] if len(args) > 1 else "units"
            step = ch * 0.85 if what == "pages" else self.ROW_STRIDE * 2
            self._scroll_top += units * step
        self._clamp_scroll()
        self._redraw()

    def _on_mousewheel(self, event: Any) -> None:
        delta = -1 * (event.delta / 120)
        self._scroll_top += delta * self.ROW_STRIDE * 2
        self._clamp_scroll()
        self._redraw()

    def _on_canvas_configure(self, _event: Any) -> None:
        self._clamp_scroll()
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self._redraw_pending:
            return
        self._redraw_pending = True
        self.after_idle(self._do_scheduled_redraw)

    def _do_scheduled_redraw(self) -> None:
        self._redraw_pending = False
        if self.winfo_exists():
            self._redraw()

    # -------------------- 虛擬化繪製 --------------------
    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        c.configure(bg=self._c("bg_surface"))

        if not self._steps:
            c.create_text(
                cw // 2,
                min(120, ch // 2),
                text="尚無巨集步驟 — 請由左側新增動作，或點擊上方「錄製」開始記錄",
                fill=self._c("fg_muted"),
                font=self._fonts["empty"],
                anchor="center",
            )
            return

        cols = self._compute_columns(cw)
        first_idx = max(0, int(self._scroll_top // self.ROW_STRIDE))
        last_idx = min(len(self._steps) - 1, int((self._scroll_top + ch) // self.ROW_STRIDE) + 1)

        col_bg_surface = self._c("bg_surface")
        col_bg_alt = self._c("bg_row_alt")
        col_bg_hover = self._c("bg_row_hover")
        col_bg_sel = self._c("bg_row_selected")
        col_fg_primary = self._c("fg_primary")
        col_fg_sec = self._c("fg_secondary")
        col_fg_muted = self._c("fg_muted")
        col_success = self._c("success")
        col_flow = self._c("tag_flow")
        col_win = self._c("tag_window")
        col_comment = self._c("tag_comment")
        col_disabled = self._c("tag_disabled")

        for idx in range(first_idx, last_idx + 1):
            step = self._steps[idx]
            indent = self._indents[idx] if idx < len(self._indents) else 0
            prefix = "    " * indent

            y1 = idx * self.ROW_STRIDE - self._scroll_top + 2
            y2 = y1 + self.ROW_HEIGHT

            if idx in self._selected:
                bg = col_bg_sel
            elif idx == self._hover_idx:
                bg = col_bg_hover
            else:
                bg = col_bg_alt if (idx % 2 == 1) else col_bg_surface

            _create_rounded_rect(c, 2, y1, cw - 4, y2, RADIUS["row"], fill=bg, outline="")

            if not step.enabled:
                type_col = col_disabled
                detail_col = col_disabled
                status_col = col_disabled
                type_font = self._fonts["normal"]
            elif step.action_type in (
                "Loop Start", "Loop End", "If Pixel Color", "If Image On Screen", "Else", "EndIf"
            ):
                type_col = col_flow
                detail_col = col_fg_primary
                status_col = col_success
                type_font = self._fonts["bold"]
            elif step.action_type in (
                "Activate Window", "Resize Window", "Move Window", "Set Window Bounds"
            ):
                type_col = col_win
                detail_col = col_fg_primary
                status_col = col_success
                type_font = self._fonts["bold"]
            elif step.action_type == "Comment":
                type_col = col_comment
                detail_col = col_comment
                status_col = col_fg_muted
                type_font = self._fonts["italic"]
            else:
                type_col = col_fg_primary
                detail_col = col_fg_primary
                status_col = col_success
                type_font = self._fonts["normal"]

            ym = (y1 + y2) / 2.0
            details_txt = self._truncate_text(step.format_details(), cols[3][1] - 10)
            comment_txt = self._truncate_text(step.comment, cols[6][1] - 10)

            cell_specs = [
                (str(idx + 1), col_fg_muted, self._fonts["small"]),
                ("●" if step.enabled else "○", status_col, self._fonts["normal"]),
                (f"{prefix}{step.action_type}", type_col, type_font),
                (details_txt, detail_col, self._fonts["normal"]),
                (f"{step.delay_ms} ms", col_fg_sec, self._fonts["small"]),
                (f"{step.repeat}×", col_fg_sec, self._fonts["small"]),
                (comment_txt, col_fg_muted, self._fonts["small"]),
            ]

            for col_i, (txt, fg_col, fnt) in enumerate(cell_specs):
                if not txt:
                    continue
                x_start, col_w, anchor = cols[col_i]
                if anchor == "center":
                    tx = x_start + col_w / 2.0
                elif anchor == "e":
                    tx = x_start + col_w - 6
                else:
                    tx = x_start + 6
                c.create_text(tx, ym, text=txt, fill=fg_col, font=fnt, anchor=anchor)

    @staticmethod
    def _truncate_text(text: str, max_px: int) -> str:
        if not text:
            return ""
        approx_chars = max(8, max_px // 7)
        if len(text) <= approx_chars:
            return text
        return text[: max(3, approx_chars - 1)] + "…"

    # -------------------- 座標反查列索引 --------------------
    def _y_to_row_index(self, y: int) -> Optional[int]:
        if not self._steps:
            return None
        abs_y = y + self._scroll_top - 2
        if abs_y < 0:
            return None
        idx = int(abs_y // self.ROW_STRIDE)
        if 0 <= idx < len(self._steps):
            return idx
        return None

    # -------------------- 滑鼠互動事件 --------------------
    def _on_motion(self, event: Any) -> None:
        idx = self._y_to_row_index(event.y)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self._schedule_redraw()

    def _on_leave(self, _event: Any) -> None:
        if self._hover_idx is not None:
            self._hover_idx = None
            self._schedule_redraw()

    def _on_press(self, event: Any) -> None:
        self.focus_set()
        idx = self._y_to_row_index(event.y)
        if idx is None:
            if self._selected:
                self._selected.clear()
                self._anchor = None
                self._schedule_redraw()
                self.on_selection_change()
            return

        state = getattr(event, "state", 0)
        is_shift = bool(state & 0x0001)
        is_ctrl = bool(state & 0x0004)

        self._drag_active = False
        self._drag_snapshot_taken = False
        self._drag_last_row = idx

        if is_shift and self._anchor is not None:
            start = min(self._anchor, idx)
            end = max(self._anchor, idx)
            self._selected = set(range(start, end + 1))
        elif is_ctrl:
            if idx in self._selected:
                self._selected.remove(idx)
            else:
                self._selected.add(idx)
            self._anchor = idx
        else:
            if idx not in self._selected:
                self._selected = {idx}
            self._anchor = idx

        self._schedule_redraw()
        self.on_selection_change()

    def _on_drag(self, event: Any) -> None:
        if not self._selected or self._drag_last_row is None:
            return

        if event.y < 10:
            self._scroll_top -= self.ROW_STRIDE
            self._clamp_scroll()
        elif event.y > self.canvas.winfo_height() - 10:
            self._scroll_top += self.ROW_STRIDE
            self._clamp_scroll()

        target_idx = self._y_to_row_index(event.y)
        if target_idx is None or target_idx == self._drag_last_row:
            return

        if not self._drag_snapshot_taken:
            self.on_drag_start()
            self._drag_snapshot_taken = True

        self._drag_active = True
        delta = 1 if target_idx > self._drag_last_row else -1
        if self.on_drag_step(delta):
            self._drag_last_row = target_idx
            self.winfo_toplevel().configure(cursor="fleur")

    def _on_release(self, event: Any) -> None:
        self.winfo_toplevel().configure(cursor="")
        if not self._drag_active:
            state = getattr(event, "state", 0)
            is_shift = bool(state & 0x0001)
            is_ctrl = bool(state & 0x0004)
            if not is_shift and not is_ctrl and len(self._selected) > 1:
                idx = self._y_to_row_index(event.y)
                if idx is not None:
                    self._selected = {idx}
                    self._anchor = idx
                    self._schedule_redraw()
                    self.on_selection_change()
        self._drag_active = False
        self._drag_snapshot_taken = False
        self._drag_last_row = None

    def _on_double_click(self, event: Any) -> None:
        idx = self._y_to_row_index(event.y)
        if idx is not None:
            self._selected = {idx}
            self._anchor = idx
            self._schedule_redraw()
            self.on_selection_change()
            self.on_double_click(idx)

    def _on_right_click(self, event: Any) -> None:
        idx = self._y_to_row_index(event.y)
        if idx is not None:
            if idx not in self._selected:
                self._selected = {idx}
                self._anchor = idx
                self._schedule_redraw()
                self.on_selection_change()
            self.on_right_click(event, idx)

    # -------------------- 公開資料操作 API --------------------
    def set_steps(
        self,
        steps: List[MacroStep],
        select_idx: Optional[int] = None,
        select_indices: Optional[List[int]] = None,
    ) -> None:
        self._steps = list(steps)
        self._indents = []
        indent = 0
        for step in self._steps:
            if step.action_type in ("Loop End", "Else", "EndIf"):
                indent = max(0, indent - 1)
            self._indents.append(indent)
            if step.action_type in ("Loop Start", "If Pixel Color", "If Image On Screen", "Else"):
                indent += 1

        new_sel: Set[int] = set()
        if select_indices is not None:
            new_sel.update(i for i in select_indices if 0 <= i < len(self._steps))
        elif select_idx is not None and 0 <= select_idx < len(self._steps):
            new_sel.add(select_idx)
        self._selected = new_sel

        if new_sel:
            self.scroll_to_index(max(new_sel))

        self._clamp_scroll()
        self._redraw()
        self.on_selection_change()

    def get_selected_indices(self) -> List[int]:
        return sorted(i for i in self._selected if 0 <= i < len(self._steps))

    def select_all(self) -> None:
        self._selected = set(range(len(self._steps)))
        self._redraw()
        self.on_selection_change()

    def highlight_index(self, idx: int) -> None:
        if 0 <= idx < len(self._steps):
            self._selected = {idx}
            self.scroll_to_index(idx)
            self._redraw()
            self.on_selection_change()

    def scroll_to_index(self, idx: int) -> None:
        if not self._steps or not (0 <= idx < len(self._steps)):
            return
        ch = max(1, self.canvas.winfo_height())
        row_top = idx * self.ROW_STRIDE
        row_bottom = row_top + self.ROW_HEIGHT
        if row_top < self._scroll_top:
            self._scroll_top = float(row_top)
        elif row_bottom > self._scroll_top + ch:
            self._scroll_top = float(row_bottom - ch + 8)
        self._clamp_scroll()
