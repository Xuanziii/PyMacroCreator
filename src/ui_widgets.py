#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 現代極簡 CustomTkinter 自訂元件庫
包含：
1. CTkPopupMenu: 支援深淺主題、微圓角、快捷鍵提示與核取項目的現代浮動選單
2. CTkSpinbox: 微圓角數值增減器（取代原生 ttk.Spinbox）
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from src.ui_theme import PALETTE, RADIUS, UI_FONT_FAMILY


class CTkPopupMenu:
    """無邊框微圓角 CustomTkinter 浮動選單（用於頂部下拉選單與右鍵選單）。"""

    _active_popup: Optional[ctk.CTkToplevel] = None

    def __init__(self, master: Any, items: List[Dict[str, Any]], width: int = 230) -> None:
        """
        items 格式範例:
          {"type": "command", "label": "儲存", "shortcut": "Ctrl+S", "command": fn}
          {"type": "check", "label": "包含移動軌跡", "variable": bool_var, "command": fn}
          {"type": "separator"}
        """
        self.master = master
        self.items = items
        self.width = width
        self._popup: Optional[ctk.CTkToplevel] = None
        self._click_bind_id: Optional[str] = None

    @classmethod
    def dismiss_active(cls) -> None:
        if cls._active_popup is not None:
            try:
                if cls._active_popup.winfo_exists():
                    cls._active_popup.destroy()
            except Exception:
                pass
            cls._active_popup = None

    def show(self, x: int, y: int) -> None:
        CTkPopupMenu.dismiss_active()

        popup = ctk.CTkToplevel(self.master)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=PALETTE["border_strong"])

        CTkPopupMenu._active_popup = popup
        self._popup = popup

        container = ctk.CTkFrame(
            popup,
            fg_color=PALETTE["bg_surface"],
            corner_radius=RADIUS["menu"],
            border_width=1,
            border_color=PALETTE["border_strong"],
        )
        container.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=5, pady=5)

        font_item = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)
        font_shortcut = ctk.CTkFont(family=UI_FONT_FAMILY, size=11)

        for item in self.items:
            kind = item.get("type", "command")
            if kind == "separator":
                sep = ctk.CTkFrame(inner, height=1, fg_color=PALETTE["border"])
                sep.pack(fill="x", padx=6, pady=4)
                continue

            label_text = item.get("label", "")
            shortcut_text = item.get("shortcut", "")
            cmd = item.get("command")

            if kind == "check":
                var = item.get("variable")
                checked = bool(var.get()) if var is not None else False
                prefix = "✓  " if checked else "    "
                display_label = f"{prefix}{label_text}"

                def _toggle_check(v=var, fn=cmd) -> None:
                    self.close()
                    if v is not None:
                        v.set(not bool(v.get()))
                    if fn:
                        fn()

                action_fn = _toggle_check
            else:
                display_label = f"  {label_text}"

                def _run_cmd(fn=cmd) -> None:
                    self.close()
                    if fn:
                        fn()

                action_fn = _run_cmd

            row = ctk.CTkFrame(
                inner,
                fg_color="transparent",
                corner_radius=6,
                height=30,
                width=self.width,
            )
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            lbl = ctk.CTkLabel(
                row,
                text=display_label,
                font=font_item,
                text_color=PALETTE["fg_primary"],
                anchor="w",
            )
            lbl.pack(side="left", fill="x", expand=True, padx=(4, 8))

            sc_lbl = None
            if shortcut_text:
                sc_lbl = ctk.CTkLabel(
                    row,
                    text=shortcut_text,
                    font=font_shortcut,
                    text_color=PALETTE["fg_muted"],
                    anchor="e",
                )
                sc_lbl.pack(side="right", padx=(0, 8))

            def _on_enter(_e: Any, r=row) -> None:
                r.configure(fg_color=PALETTE["bg_hover"])

            def _on_leave(_e: Any, r=row) -> None:
                r.configure(fg_color="transparent")

            def _on_click(_e: Any, fn=action_fn) -> None:
                fn()

            widgets = [row, lbl] + ([sc_lbl] if sc_lbl else [])
            for w in widgets:
                w.bind("<Enter>", _on_enter)
                w.bind("<Leave>", _on_leave)
                w.bind("<Button-1>", _on_click)

        popup.update_idletasks()
        pw = max(self.width + 12, popup.winfo_reqwidth())
        ph = popup.winfo_reqheight()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()

        pos_x = min(max(4, x), sw - pw - 8)
        pos_y = min(max(4, y), sh - ph - 40)
        popup.geometry(f"{pw}x{ph}+{pos_x}+{pos_y}")
        popup.deiconify()
        popup.focus_set()

        popup.bind("<Escape>", lambda _e: self.close())
        popup.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, _event: Any = None) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.after(60, self._check_focus_close)

    def _check_focus_close(self) -> None:
        if self._popup is None or not self._popup.winfo_exists():
            return
        try:
            focused = self._popup.focus_get()
            if focused is None or str(focused).split(".")[1] != str(self._popup).split(".")[1]:
                self.close()
        except Exception:
            self.close()

    def close(self) -> None:
        if self._popup is not None:
            try:
                if self._popup.winfo_exists():
                    self._popup.destroy()
            except Exception:
                pass
            if CTkPopupMenu._active_popup is self._popup:
                CTkPopupMenu._active_popup = None
            self._popup = None


class CTkSpinbox(ctk.CTkFrame):
    """微圓角扁平化數值調整器，可取代原生 ttk.Spinbox。"""

    def __init__(
        self,
        master: Any,
        variable: Any,
        min_value: int = 0,
        max_value: int = 999999,
        step: int = 1,
        width: int = 96,
        height: int = 30,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color=PALETTE["bg_input"],
            border_width=1,
            border_color=PALETTE["border_strong"],
            corner_radius=RADIUS["input"],
            **kwargs,
        )
        self.variable = variable
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.grid_propagate(False)
        self.pack_propagate(False)

        font_btn = ctk.CTkFont(family=UI_FONT_FAMILY, size=12, weight="bold")
        font_ent = ctk.CTkFont(family=UI_FONT_FAMILY, size=12)

        self.btn_sub = ctk.CTkButton(
            self,
            text="−",
            width=24,
            height=height - 4,
            corner_radius=5,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=font_btn,
            command=self._decrement,
        )
        self.btn_sub.pack(side="left", padx=(2, 0), pady=2)

        self.entry = ctk.CTkEntry(
            self,
            textvariable=self.variable,
            height=height - 4,
            border_width=0,
            fg_color="transparent",
            text_color=PALETTE["fg_primary"],
            font=font_ent,
            justify="center",
        )
        self.entry.pack(side="left", fill="both", expand=True, pady=2)

        self.btn_add = ctk.CTkButton(
            self,
            text="+",
            width=24,
            height=height - 4,
            corner_radius=5,
            fg_color="transparent",
            hover_color=PALETTE["bg_hover"],
            text_color=PALETTE["fg_secondary"],
            font=font_btn,
            command=self._increment,
        )
        self.btn_add.pack(side="right", padx=(0, 2), pady=2)

    def _get_safe_int(self) -> int:
        try:
            return int(self.variable.get())
        except Exception:
            return self.min_value

    def _increment(self) -> None:
        val = min(self.max_value, self._get_safe_int() + self.step)
        self.variable.set(val)

    def _decrement(self) -> None:
        val = max(self.min_value, self._get_safe_int() - self.step)
        self.variable.set(val)
