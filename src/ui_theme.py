#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator v4.0 — 極簡扁平化雙主題色彩系統與字型定義 (CustomTkinter)
"""

from __future__ import annotations

import sys
from typing import Dict, Tuple

UI_FONT_FAMILY = (
    "Microsoft JhengHei UI"
    if sys.platform == "win32"
    else ("PingFang TC" if sys.platform == "darwin" else "Sans")
)
MONO_FONT_FAMILY = (
    "Consolas"
    if sys.platform == "win32"
    else ("Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono")
)

# CustomTkinter 原生支援 (light_color, dark_color) 雙色元組，
# 切換 ctk.set_appearance_mode("light" | "dark") 時所有元件會即時同步變色。
ColorPair = Tuple[str, str]

PALETTE: Dict[str, ColorPair] = {
    # 階層背景
    "bg_app": ("#F3F4F6", "#0E1015"),
    "bg_surface": ("#FFFFFF", "#161922"),
    "bg_elevated": ("#F1F5F9", "#1F2430"),
    "bg_input": ("#F8FAFC", "#11141C"),
    "bg_hover": ("#E2E8F0", "#2A3142"),
    "bg_row_alt": ("#F8FAFC", "#1A1E29"),
    "bg_row_hover": ("#EFF6FF", "#232A3B"),
    "bg_row_selected": ("#DBEAFE", "#1E3A5F"),
    # 文字階層
    "fg_primary": ("#0F172A", "#F1F5F9"),
    "fg_secondary": ("#475569", "#94A3B8"),
    "fg_muted": ("#94A3B8", "#64748B"),
    # 邊框與分隔線
    "border": ("#E2E8F0", "#262C3A"),
    "border_strong": ("#CBD5E1", "#333B4D"),
    # 品牌強調色 (Modern Indigo-Blue)
    "accent": ("#2563EB", "#3B82F6"),
    "accent_hover": ("#1D4ED8", "#2563EB"),
    "accent_subtle": ("#DBEAFE", "#1B2E4B"),
    "accent_fg": ("#1D4ED8", "#93C5FD"),
    # 語意狀態色
    "success": ("#059669", "#10B981"),
    "success_hover": ("#047857", "#059669"),
    "danger": ("#DC2626", "#EF4444"),
    "danger_hover": ("#B91C1C", "#DC2626"),
    "warning": ("#D97706", "#F59E0B"),
    # 動作類型標籤色
    "tag_flow": ("#4F46E5", "#818CF8"),
    "tag_window": ("#0284C7", "#38BDF8"),
    "tag_comment": ("#94A3B8", "#64748B"),
    "tag_disabled": ("#CBD5E1", "#475569"),
    # 捲軸
    "scrollbar_fg": ("#CBD5E1", "#2E3546"),
    "scrollbar_hover": ("#94A3B8", "#475569"),
}

# 統一圓角設計語言 (Subtle Rounded Corners)
RADIUS = {
    "card": 10,
    "button": 8,
    "pill": 7,
    "input": 7,
    "row": 6,
    "badge": 12,
    "menu": 9,
}


def resolve_color(key: str, mode: str) -> str:
    """依目前主題模式回傳單一色碼字串（供動態狀態徽章等使用）。"""
    pair = PALETTE[key]
    return pair[1] if mode == "dark" else pair[0]
