#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Windows High-DPI 支援，避免介面模糊
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


# 嘗試載入自動化相關套件
try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01
    HAS_PYAUTOGUI = True
except Exception:
    pyautogui = None
    HAS_PYAUTOGUI = False

# 嘗試載入 pygetwindow 視窗控制套件
try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except Exception:
    gw = None
    HAS_PYGETWINDOW = False

try:
    from pynput import keyboard as pynput_kb
    from pynput import mouse as pynput_mouse

    HAS_PYNPUT = True
except Exception:
    pynput_kb = None
    pynput_mouse = None
    HAS_PYNPUT = False


# =====================================================================
# 0. 視窗控制核心管理員 (Window Manager: 切換、調整大小、移動位置)
# =====================================================================

class WindowManager:
    """負責搜尋、切換 (Activate)、調整大小 (Resize) 與移動 (Move) 系統視窗。"""

    @staticmethod
    def list_open_windows() -> List[str]:
        titles: List[str] = []

        if sys.platform == "win32":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

                def _enum_cb(hwnd: int, _lparam: int) -> bool:
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            t = buf.value.strip()
                            if t and t not in titles:
                                titles.append(t)
                    return True

                user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
                if titles:
                    return sorted(titles)
            except Exception:
                pass

        if HAS_PYGETWINDOW:
            try:
                for t in gw.getAllTitles():
                    clean_t = str(t).strip()
                    if clean_t and clean_t not in titles:
                        titles.append(clean_t)
            except Exception:
                pass

        return sorted(titles)

    @staticmethod
    def _find_win32_hwnd(title_query: str, exact_match: bool = False) -> Optional[int]:
        if sys.platform != "win32" or not title_query:
            return None
        try:
            import ctypes

            user32 = ctypes.windll.user32
            target_q = title_query.strip().lower()
            matched_hwnds: List[int] = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def _enum_cb(hwnd: int, _lparam: int) -> bool:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        win_title = buf.value.strip()
                        win_title_low = win_title.lower()
                        if (exact_match and win_title_low == target_q) or (
                            not exact_match and target_q in win_title_low
                        ):
                            matched_hwnds.append(hwnd)
                return True

            user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
            return matched_hwnds[0] if matched_hwnds else None
        except Exception:
            return None

    @staticmethod
    def _find_gw_window(title_query: str, exact_match: bool = False) -> Any:
        if not HAS_PYGETWINDOW or not title_query:
            return None
        try:
            target_q = title_query.strip().lower()
            for w in gw.getAllWindows():
                t = getattr(w, "title", "").strip()
                if not t:
                    continue
                t_low = t.lower()
                if (exact_match and t_low == target_q) or (not exact_match and target_q in t_low):
                    return w
        except Exception:
            pass
        return None

    @classmethod
    def get_window_rect(cls, title_query: str) -> Optional[Tuple[int, int, int, int, str]]:
        if sys.platform == "win32":
            hwnd = cls._find_win32_hwnd(title_query)
            if hwnd:
                try:
                    import ctypes
                    from ctypes import wintypes

                    user32 = ctypes.windll.user32
                    rect = wintypes.RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        length = user32.GetWindowTextLengthW(hwnd)
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        x = int(rect.left)
                        y = int(rect.top)
                        w = max(1, int(rect.right - rect.left))
                        h = max(1, int(rect.bottom - rect.top))
                        return (x, y, w, h, buf.value.strip())
                except Exception:
                    pass

        win = cls._find_gw_window(title_query)
        if win is not None:
            try:
                return (
                    int(win.left),
                    int(win.top),
                    int(win.width),
                    int(win.height),
                    str(win.title).strip(),
                )
            except Exception:
                pass
        return None

    @classmethod
    def activate_window(cls, title_query: str, exact_match: bool = False) -> Tuple[bool, str]:
        if not title_query or not title_query.strip():
            return False, "未指定視窗標題關鍵字"

        if sys.platform == "win32":
            hwnd = cls._find_win32_hwnd(title_query, exact_match=exact_match)
            if hwnd:
                try:
                    import ctypes

                    user32 = ctypes.windll.user32
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    else:
                        user32.ShowWindow(hwnd, 5)  # SW_SHOW

                    if not user32.SetForegroundWindow(hwnd):
                        user32.keybd_event(0x12, 0, 0, 0)
                        user32.SetForegroundWindow(hwnd)
                        user32.keybd_event(0x12, 0, 2, 0)

                    user32.BringWindowToTop(hwnd)
                    return True, f"已切換至視窗 [{title_query}]"
                except Exception as exc:
                    return False, f"Win32 切換視窗失敗: {exc}"

        win = cls._find_gw_window(title_query, exact_match=exact_match)
        if win is not None:
            try:
                if getattr(win, "isMinimized", False):
                    win.restore()
                win.activate()
                return True, f"已切換至視窗 [{win.title}]"
            except Exception as exc:
                return False, f"切換視窗失敗: {exc}"

        return False, f"找不到符合「{title_query}」的視窗"

    @classmethod
    def resize_window(
        cls, title_query: str, width: int, height: int, exact_match: bool = False
    ) -> Tuple[bool, str]:
        if not title_query or not title_query.strip():
            return False, "未指定視窗標題關鍵字"
        w = max(50, int(width))
        h = max(50, int(height))

        if sys.platform == "win32":
            hwnd = cls._find_win32_hwnd(title_query, exact_match=exact_match)
            if hwnd:
                try:
                    import ctypes
                    from ctypes import wintypes

                    user32 = ctypes.windll.user32
                    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
                        user32.ShowWindow(hwnd, 9)
                        time.sleep(0.05)

                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    user32.MoveWindow(hwnd, int(rect.left), int(rect.top), w, h, True)
                    return True, f"已將視窗 [{title_query}] 大小設為 {w}x{h}"
                except Exception as exc:
                    return False, f"Win32 調整視窗大小失敗: {exc}"

        win = cls._find_gw_window(title_query, exact_match=exact_match)
        if win is not None:
            try:
                if getattr(win, "isMinimized", False) or getattr(win, "isMaximized", False):
                    win.restore()
                win.resizeTo(w, h)
                return True, f"已將視窗 [{win.title}] 大小設為 {w}x{h}"
            except Exception as exc:
                return False, f"調整視窗大小失敗: {exc}"

        return False, f"找不到符合「{title_query}」的視窗"

    @classmethod
    def move_window(
        cls, title_query: str, x: int, y: int, exact_match: bool = False
    ) -> Tuple[bool, str]:
        if not title_query or not title_query.strip():
            return False, "未指定視窗標題關鍵字"
        target_x = int(x)
        target_y = int(y)

        if sys.platform == "win32":
            hwnd = cls._find_win32_hwnd(title_query, exact_match=exact_match)
            if hwnd:
                try:
                    import ctypes
                    from ctypes import wintypes

                    user32 = ctypes.windll.user32
                    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
                        user32.ShowWindow(hwnd, 9)
                        time.sleep(0.05)

                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    cur_w = max(50, int(rect.right - rect.left))
                    cur_h = max(50, int(rect.bottom - rect.top))
                    user32.MoveWindow(hwnd, target_x, target_y, cur_w, cur_h, True)
                    return True, f"已將視窗 [{title_query}] 移動至 ({target_x}, {target_y})"
                except Exception as exc:
                    return False, f"Win32 移動視窗失敗: {exc}"

        win = cls._find_gw_window(title_query, exact_match=exact_match)
        if win is not None:
            try:
                if getattr(win, "isMinimized", False) or getattr(win, "isMaximized", False):
                    win.restore()
                win.moveTo(target_x, target_y)
                return True, f"已將視窗 [{win.title}] 移動至 ({target_x}, {target_y})"
            except Exception as exc:
                return False, f"移動視窗失敗: {exc}"

        return False, f"找不到符合「{title_query}」的視窗"

    @classmethod
    def set_window_bounds(
        cls,
        title_query: str,
        x: int,
        y: int,
        width: int,
        height: int,
        activate: bool = True,
        exact_match: bool = False,
    ) -> Tuple[bool, str]:
        if activate:
            cls.activate_window(title_query, exact_match=exact_match)
        ok_move, msg_move = cls.move_window(title_query, x, y, exact_match=exact_match)
        if not ok_move:
            return False, msg_move
        ok_size, msg_size = cls.resize_window(title_query, width, height, exact_match=exact_match)
        if not ok_size:
            return False, msg_size
        return True, f"已設定視窗 [{title_query}] 位置 ({x}, {y}) 與大小 {width}x{height}"


# =====================================================================
# 1. 鍵盤按鍵清單與快捷鍵工具
# =====================================================================

KEY_CATALOG: Dict[str, List[Tuple[str, str]]] = {
    "常用與方向鍵": [
        ("up", "↑ 方向鍵上 (Up)"),
        ("down", "↓ 方向鍵下 (Down)"),
        ("left", "← 方向鍵左 (Left)"),
        ("right", "→ 方向鍵右 (Right)"),
        ("enter", "Enter 確認/換行"),
        ("space", "Space 空白鍵"),
        ("tab", "Tab 跳格鍵"),
        ("esc", "Esc 取消/離開"),
        ("backspace", "Backspace 倒退刪除"),
        ("delete", "Delete 向後刪除"),
    ],
    "修飾與編輯導覽鍵": [
        ("shift", "Shift 鍵"),
        ("ctrl", "Ctrl 鍵"),
        ("alt", "Alt 鍵"),
        ("win", "Windows 視窗鍵"),
        ("capslock", "CapsLock 大寫鎖定"),
        ("pageup", "Page Up 上一頁"),
        ("pagedown", "Page Down 下一頁"),
        ("home", "Home 行首/頂端"),
        ("end", "End 行尾/底部"),
        ("insert", "Insert 插入鍵"),
        ("printscreen", "PrintScreen 螢幕截圖"),
    ],
    "功能鍵 (F1 ~ F12)": [(f"f{i}", f"F{i} 功能鍵") for i in range(1, 13)],
    "字母與數字鍵 (A~Z, 0~9)": (
        [(chr(c), f"字母 {chr(c).upper()}") for c in range(ord("a"), ord("z") + 1)]
        + [(str(d), f"數字 {d}") for d in range(10)]
    ),
    "九宮格數字與多媒體": [
        ("num0", "九宮格 0"),
        ("num1", "九宮格 1"),
        ("num2", "九宮格 2"),
        ("num3", "九宮格 3"),
        ("num4", "九宮格 4"),
        ("num5", "九宮格 5"),
        ("num6", "九宮格 6"),
        ("num7", "九宮格 7"),
        ("num8", "九宮格 8"),
        ("num9", "九宮格 9"),
        ("volumeup", "音量調高"),
        ("volumedown", "音量調低"),
        ("volumemute", "靜音切換"),
    ],
}

HOTKEY_PRESETS: List[str] = [
    "ctrl+c (複製)",
    "ctrl+v (貼上)",
    "ctrl+x (剪下)",
    "ctrl+z (復原)",
    "ctrl+y (重做)",
    "ctrl+a (全選)",
    "ctrl+s (儲存)",
    "ctrl+f (尋找)",
    "ctrl+w (關閉分頁)",
    "alt+tab (切換視窗)",
    "alt+f4 (關閉程式)",
    "win+d (顯示桌面)",
    "win+e (檔案總管)",
    "ctrl+shift+esc (工作管理員)",
]

MOUSE_BUTTON_OPTIONS: List[str] = [
    "left (滑鼠左鍵)",
    "right (滑鼠右鍵)",
    "middle (滑鼠中鍵)",
]

TK_KEYSYM_MAP: Dict[str, str] = {
    "Return": "enter",
    "KP_Enter": "enter",
    "Escape": "esc",
    "BackSpace": "backspace",
    "Tab": "tab",
    "ISO_Left_Tab": "tab",
    "space": "space",
    "Delete": "delete",
    "KP_Delete": "delete",
    "Insert": "insert",
    "KP_Insert": "num0",
    "Home": "home",
    "KP_Home": "num7",
    "End": "end",
    "KP_End": "num1",
    "Prior": "pageup",
    "KP_Prior": "num9",
    "Next": "pagedown",
    "KP_Next": "num3",
    "Up": "up",
    "KP_Up": "num8",
    "Down": "down",
    "KP_Down": "num2",
    "Left": "left",
    "KP_Left": "num4",
    "Right": "right",
    "KP_Right": "num6",
    "KP_Begin": "num5",
    "KP_0": "num0",
    "KP_1": "num1",
    "KP_2": "num2",
    "KP_3": "num3",
    "KP_4": "num4",
    "KP_5": "num5",
    "KP_6": "num6",
    "KP_7": "num7",
    "KP_8": "num8",
    "KP_9": "num9",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Super_L": "win",
    "Super_R": "win",
    "Win_L": "win",
    "Win_R": "win",
    "Caps_Lock": "capslock",
    "Print": "printscreen",
    "minus": "-",
    "equal": "=",
    "bracketleft": "[",
    "bracketright": "]",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "grave": "`",
}

MODIFIER_KEYSYMS: Set[str] = {
    "Control_L",
    "Control_R",
    "Shift_L",
    "Shift_R",
    "Alt_L",
    "Alt_R",
    "Super_L",
    "Super_R",
    "Win_L",
    "Win_R",
    "Meta_L",
    "Meta_R",
}

DEFAULT_APP_HOTKEYS: Dict[str, str] = {
    "play": "f5",
    "stop": "f6",
    "pause": "f7",
    "record": "f9",
    "stop_record": "f10",
    "capture_cursor": "f2",
}

HOTKEY_ACTION_LABELS: Dict[str, str] = {
    "play": "播放巨集 (Play)",
    "pause": "暫停 / 繼續 (Pause)",
    "stop": "停止播放 (Stop)",
    "record": "開始 / 停止錄製 (Record)",
    "stop_record": "強制停止錄製 (Stop Rec)",
    "capture_cursor": "擷取游標座標與顏色 (Capture)",
}

RESERVED_EDITOR_SHORTCUTS: Set[str] = {
    "ctrl+c",
    "ctrl+v",
    "ctrl+x",
    "ctrl+a",
    "ctrl+z",
    "ctrl+y",
    "ctrl+shift+z",
    "ctrl+s",
    "ctrl+shift+s",
    "ctrl+o",
    "ctrl+n",
    "ctrl+d",
    "ctrl+e",
}


def normalize_hotkey_string(hk_str: str) -> str:
    if not hk_str or not hk_str.strip():
        return ""
    raw_parts = [p.strip().lower() for p in hk_str.split("+") if p.strip()]
    if not raw_parts:
        return ""

    mods: List[str] = []
    main_key = ""
    for p in raw_parts:
        if p in ("ctrl", "control"):
            if "ctrl" not in mods:
                mods.append("ctrl")
        elif p == "shift":
            if "shift" not in mods:
                mods.append("shift")
        elif p == "alt":
            if "alt" not in mods:
                mods.append("alt")
        elif p in ("win", "cmd", "super"):
            if "win" not in mods:
                mods.append("win")
        else:
            main_key = p

    if not main_key:
        return ""

    ordered_mods = [m for m in ("ctrl", "shift", "alt", "win") if m in mods]
    return "+".join(ordered_mods + [main_key])


def tk_event_to_hotkey_string(event: Any) -> Optional[str]:
    ks = getattr(event, "keysym", "")
    if not ks or ks in MODIFIER_KEYSYMS or ks == "??":
        return None

    mapped_main = TK_KEYSYM_MAP.get(ks, ks.lower())
    if not mapped_main or mapped_main in ("ctrl", "shift", "alt", "win"):
        return None

    state = getattr(event, "state", 0)
    mods: List[str] = []
    if state & 0x0004:
        mods.append("ctrl")
    if state & 0x0001:
        mods.append("shift")
    if (state & 0x0008) or (state & 0x20000):
        mods.append("alt")

    return "+".join(mods + [mapped_main])


def is_safe_hotkey_while_typing(normalized_hk: str) -> bool:
    if not normalized_hk:
        return False
    if normalized_hk in RESERVED_EDITOR_SHORTCUTS:
        return False

    parts = normalized_hk.split("+")
    main_key = parts[-1]
    mods = set(parts[:-1])

    if main_key.startswith("f") and main_key[1:].isdigit():
        return True
    if mods.intersection({"ctrl", "alt", "win"}):
        return True
    return False


def format_hotkey_display(hk_str: str) -> str:
    norm = normalize_hotkey_string(hk_str)
    if not norm:
        return "未設定"
    parts = norm.split("+")
    formatted = []
    for p in parts:
        if p.startswith("f") and p[1:].isdigit():
            formatted.append(p.upper())
        elif len(p) == 1:
            formatted.append(p.upper())
        else:
            formatted.append(p.capitalize())
    return "+".join(formatted)


PYNPUT_SPECIAL_KEYS: Set[str] = {
    "alt", "alt_gr", "alt_l", "alt_r", "backspace", "caps_lock", "cmd", "cmd_l", "cmd_r",
    "ctrl", "ctrl_l", "ctrl_r", "delete", "down", "end", "enter", "esc",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "home", "insert", "left", "media_next", "media_play_pause", "media_previous",
    "media_volume_down", "media_volume_mute", "media_volume_up", "menu", "num_lock",
    "page_down", "page_up", "pause", "print_screen", "right", "scroll_lock",
    "shift", "shift_l", "shift_r", "space", "tab", "up",
}

PYNPUT_KEY_ALIAS: Dict[str, str] = {
    "capslock": "caps_lock",
    "pageup": "page_up",
    "pagedown": "page_down",
    "printscreen": "print_screen",
    "volumeup": "media_volume_up",
    "volumedown": "media_volume_down",
    "volumemute": "media_volume_mute",
    "win": "cmd",
}


def hotkey_to_pynput_sequence(hk_str: str) -> Optional[str]:
    norm = normalize_hotkey_string(hk_str)
    if not norm:
        return None
    pynput_parts: List[str] = []
    for p in norm.split("+"):
        mapped = PYNPUT_KEY_ALIAS.get(p, p)
        if len(mapped) == 1 and mapped.isprintable():
            pynput_parts.append(mapped)
        elif mapped in PYNPUT_SPECIAL_KEYS:
            pynput_parts.append(f"<{mapped}>")
        else:
            return None
    return "+".join(pynput_parts)


def get_key_dropdown_values(category: str = "全部按鍵") -> List[str]:
    items: List[str] = []
    if category == "全部按鍵" or category not in KEY_CATALOG:
        for group in KEY_CATALOG.values():
            for code, desc in group:
                items.append(f"{code} ({desc})")
    else:
        for code, desc in KEY_CATALOG[category]:
            items.append(f"{code} ({desc})")
    return items


def extract_clean_token(raw_value: str) -> str:
    text = str(raw_value).strip()
    if not text:
        return ""
    if " (" in text and text.endswith(")"):
        text = text.split(" (", 1)[0].strip()

    alias_map = {
        "上": "up",
        "下": "down",
        "左": "left",
        "右": "right",
        "方向鍵上": "up",
        "方向鍵下": "down",
        "方向鍵左": "left",
        "方向鍵右": "right",
        "空白": "space",
        "空白鍵": "space",
        "確認": "enter",
        "換行": "enter",
        "左鍵": "left",
        "右鍵": "right",
        "中鍵": "middle",
    }
    lowered = text.lower()
    return alias_map.get(lowered, lowered)


# =====================================================================
# 2. 資料模型與動作分類 (Macro Step Data Model)
# =====================================================================

ACTION_CATEGORIES: Dict[str, List[str]] = {
    "Mouse": [
        "Mouse Click",
        "Mouse Double Click",
        "Mouse Move",
        "Mouse Drag",
        "Mouse Scroll",
    ],
    "Keyboard": [
        "Key Press",
        "Key Down",
        "Key Up",
        "Send Text",
        "Hotkey Combo",
    ],
    "Window": [
        "Activate Window",
        "Resize Window",
        "Move Window",
        "Set Window Bounds",
    ],
    "Wait / Delay": [
        "Sleep (Fixed)",
        "Sleep (Random)",
    ],
    "Image / Pixel": [
        "If Pixel Color",
        "If Image On Screen",
        "Click Image On Screen",
    ],
    "Control Flow": [
        "Loop Start",
        "Loop End",
        "Else",
        "EndIf",
    ],
    "System / Misc": [
        "Run Command",
        "Comment",
    ],
}

CATEGORY_LABELS: Dict[str, str] = {
    "Mouse": "滑鼠",
    "Keyboard": "鍵盤",
    "Window": "視窗",
    "Wait / Delay": "延遲",
    "Image / Pixel": "找圖/色",
    "Control Flow": "流程",
    "System / Misc": "系統",
}

ACTION_DISPLAY_NAMES: Dict[str, str] = {
    "Mouse Click": "Mouse Click — 滑鼠單擊",
    "Mouse Double Click": "Mouse Double Click — 滑鼠雙擊",
    "Mouse Move": "Mouse Move — 滑鼠移動",
    "Mouse Drag": "Mouse Drag — 滑鼠拖曳",
    "Mouse Scroll": "Mouse Scroll — 滑鼠滾輪",
    "Key Press": "Key Press — 按一下按鍵",
    "Key Down": "Key Down — 按住按鍵",
    "Key Up": "Key Up — 放開按鍵",
    "Send Text": "Send Text — 輸入文字",
    "Hotkey Combo": "Hotkey Combo — 組合快捷鍵",
    "Activate Window": "Activate Window — 切換視窗",
    "Resize Window": "Resize Window — 調整視窗大小",
    "Move Window": "Move Window — 移動視窗位置",
    "Set Window Bounds": "Set Window Bounds — 切換+移動+縮放",
    "Sleep (Fixed)": "Sleep (Fixed) — 固定等待",
    "Sleep (Random)": "Sleep (Random) — 隨機等待",
    "If Pixel Color": "If Pixel Color — 若座標顏色符合",
    "If Image On Screen": "If Image On Screen — 若畫面出現圖片",
    "Click Image On Screen": "Click Image On Screen — 找圖並點擊",
    "Loop Start": "Loop Start — 迴圈開始",
    "Loop End": "Loop End — 迴圈結束",
    "Else": "Else — 否則分支",
    "EndIf": "EndIf — 條件結束",
    "Run Command": "Run Command — 執行系統指令",
    "Comment": "Comment — 註解說明",
}


def resolve_action_type(display_or_key: str) -> str:
    for k, v in ACTION_DISPLAY_NAMES.items():
        if display_or_key == v or display_or_key == k:
            return k
    if " — " in display_or_key:
        return display_or_key.split(" — ", 1)[0].strip()
    return display_or_key.split(" (", 1)[0].strip()


@dataclass
class MacroStep:
    action_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    delay_ms: int = 50
    repeat: int = 1
    enabled: bool = True
    comment: str = ""

    def format_details(self) -> str:
        p = self.params
        t = self.action_type
        if t in ("Mouse Click", "Mouse Double Click"):
            btn = extract_clean_token(p.get("button", "left")).upper()
            return f"[{btn}] ({p.get('x', 0)}, {p.get('y', 0)})"
        if t == "Mouse Move":
            return f"移至 ({p.get('x', 0)}, {p.get('y', 0)}) · {p.get('duration', 0.1)}s"
        if t == "Mouse Drag":
            return (
                f"({p.get('start_x', 0)}, {p.get('start_y', 0)}) → "
                f"({p.get('end_x', 0)}, {p.get('end_y', 0)}) [{extract_clean_token(p.get('button', 'left'))}]"
            )
        if t == "Mouse Scroll":
            return f"滾輪 {p.get('clicks', -3)} 格 @ ({p.get('x', 0)}, {p.get('y', 0)})"
        if t in ("Key Press", "Key Down", "Key Up"):
            key_code = extract_clean_token(p.get("key", "enter"))
            return f"按鍵 <{key_code.upper()}>"
        if t == "Send Text":
            return f"\"{p.get('text', '')}\" (間隔 {p.get('interval', 0.02)}s)"
        if t == "Hotkey Combo":
            keys_code = extract_clean_token(p.get("keys", "ctrl+c"))
            return f"組合鍵 <{keys_code.upper()}>"
        if t == "Activate Window":
            return f"切換 \"{p.get('title', '')}\""
        if t == "Resize Window":
            return f"\"{p.get('title', '')}\" → {p.get('width', 1280)}×{p.get('height', 720)}"
        if t == "Move Window":
            return f"\"{p.get('title', '')}\" → ({p.get('x', 0)}, {p.get('y', 0)})"
        if t == "Set Window Bounds":
            return (
                f"\"{p.get('title', '')}\" → ({p.get('x', 0)}, {p.get('y', 0)}) · "
                f"{p.get('width', 1280)}×{p.get('height', 720)}"
            )
        if t == "Sleep (Fixed)":
            return f"等待 {p.get('ms', 1000)} ms"
        if t == "Sleep (Random)":
            return f"隨機 {p.get('min_ms', 500)} ~ {p.get('max_ms', 1500)} ms"
        if t == "If Pixel Color":
            return (
                f"({p.get('x', 0)}, {p.get('y', 0)}) == "
                f"RGB({p.get('r', 255)}, {p.get('g', 255)}, {p.get('b', 255)}) ±{p.get('tolerance', 10)}"
            )
        if t in ("If Image On Screen", "Click Image On Screen"):
            return (
                f"圖片 '{os.path.basename(str(p.get('image_path', '')))}' "
                f"(信心度 {p.get('confidence', 0.85)})"
            )
        if t == "Loop Start":
            return f"重複 {p.get('count', 5)} 次"
        if t in ("Loop End", "Else", "EndIf"):
            return f"── {t} ──"
        if t == "Run Command":
            return f"執行: {p.get('command', '')}"
        if t == "Comment":
            return f"# {p.get('text', self.comment)}"
        return json.dumps(p, ensure_ascii=False)


# =====================================================================
# 3. 獨立 Python 腳本產生器 (Code Generator)
# =====================================================================

class PythonScriptExporter:
    """將巨集動作清單編譯為可獨立執行的 Python (.py) 腳本"""

    @staticmethod
    def generate_code(steps: List[MacroStep], loop_count: int = 1, speed_factor: float = 1.0) -> str:
        lines: List[str] = [
            "#!/usr/bin/env python3",
            "# -*- coding: utf-8 -*-",
            '"""',
            f"Auto-generated by PyMacroCreator v4.0 on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            '"""',
            "import os",
            "import random",
            "import subprocess",
            "import sys",
            "import time",
            "import pyautogui",
            "try:",
            "    import pygetwindow as gw",
            "except Exception:",
            "    gw = None",
            "",
            "pyautogui.FAILSAFE = True",
            "pyautogui.PAUSE = 0.01",
            f"SPEED_FACTOR = {speed_factor:.2f}",
            "",
            "def wait_ms(ms: float) -> None:",
            "    if ms > 0:",
            "        time.sleep((ms / 1000.0) / max(SPEED_FACTOR, 0.05))",
            "",
            "def check_pixel_color(x: int, y: int, target_rgb: tuple, tolerance: int = 10) -> bool:",
            "    pix = pyautogui.pixel(x, y)",
            "    return all(abs(int(pix[i]) - int(target_rgb[i])) <= tolerance for i in range(3))",
            "",
            "def _find_window(title_query: str):",
            "    if gw is None or not title_query:",
            "        return None",
            "    q = title_query.strip().lower()",
            "    for w in gw.getAllWindows():",
            "        t = getattr(w, 'title', '').strip()",
            "        if t and q in t.lower():",
            "            return w",
            "    return None",
            "",
            "def activate_window(title_query: str) -> None:",
            "    w = _find_window(title_query)",
            "    if w is not None:",
            "        if getattr(w, 'isMinimized', False):",
            "            w.restore()",
            "        w.activate()",
            "",
            "def resize_window(title_query: str, width: int, height: int) -> None:",
            "    w = _find_window(title_query)",
            "    if w is not None:",
            "        if getattr(w, 'isMinimized', False) or getattr(w, 'isMaximized', False):",
            "            w.restore()",
            "        w.resizeTo(max(50, int(width)), max(50, int(height)))",
            "",
            "def move_window(title_query: str, x: int, y: int) -> None:",
            "    w = _find_window(title_query)",
            "    if w is not None:",
            "        if getattr(w, 'isMinimized', False) or getattr(w, 'isMaximized', False):",
            "            w.restore()",
            "        w.moveTo(int(x), int(y))",
            "",
            "def run_macro() -> None:",
        ]

        indent_level = 1
        block_has_body: List[bool] = [False]

        def add_line(stmt: str) -> None:
            lines.append("    " * indent_level + stmt)
            block_has_body[-1] = True

        enabled_steps = [s for s in steps if s.enabled]
        if not enabled_steps:
            add_line("pass")
        else:
            for idx, step in enumerate(enabled_steps, start=1):
                t = step.action_type
                p = step.params
                if step.comment:
                    lines.append("    " * indent_level + f"# Step {idx}: {step.comment}")

                if t == "Comment":
                    lines.append("    " * indent_level + f"# {p.get('text', '')}")
                    continue

                if t == "Loop Start":
                    cnt = max(1, int(p.get("count", 1)))
                    add_line(f"for _loop_{indent_level} in range({cnt}):")
                    indent_level += 1
                    block_has_body.append(False)
                    continue

                if t == "Loop End":
                    if len(block_has_body) > 1:
                        if not block_has_body.pop():
                            lines.append("    " * indent_level + "pass")
                        indent_level = max(1, indent_level - 1)
                    continue

                if t == "If Pixel Color":
                    x, y = int(p.get("x", 0)), int(p.get("y", 0))
                    r, g, b = int(p.get("r", 255)), int(p.get("g", 255)), int(p.get("b", 255))
                    tol = int(p.get("tolerance", 10))
                    add_line(f"if check_pixel_color({x}, {y}, ({r}, {g}, {b}), {tol}):")
                    indent_level += 1
                    block_has_body.append(False)
                    continue

                if t == "If Image On Screen":
                    img = repr(str(p.get("image_path", "")))
                    conf = float(p.get("confidence", 0.85))
                    add_line(f"if pyautogui.locateOnScreen({img}, confidence={conf}) is not None:")
                    indent_level += 1
                    block_has_body.append(False)
                    continue

                if t == "Else":
                    if len(block_has_body) > 1:
                        if not block_has_body.pop():
                            lines.append("    " * indent_level + "pass")
                        indent_level = max(1, indent_level - 1)
                        add_line("else:")
                        indent_level += 1
                        block_has_body.append(False)
                    continue

                if t == "EndIf":
                    if len(block_has_body) > 1:
                        if not block_has_body.pop():
                            lines.append("    " * indent_level + "pass")
                        indent_level = max(1, indent_level - 1)
                    continue

                rep = max(1, int(step.repeat))
                if rep > 1:
                    add_line(f"for _ in range({rep}):")
                    indent_level += 1
                    block_has_body.append(False)

                if t == "Mouse Click":
                    btn = extract_clean_token(p.get("button", "left")) or "left"
                    add_line(
                        f"pyautogui.click(x={int(p.get('x', 0))}, y={int(p.get('y', 0))}, button={repr(btn)})"
                    )
                elif t == "Mouse Double Click":
                    btn = extract_clean_token(p.get("button", "left")) or "left"
                    add_line(
                        f"pyautogui.doubleClick(x={int(p.get('x', 0))}, y={int(p.get('y', 0))}, button={repr(btn)})"
                    )
                elif t == "Mouse Move":
                    add_line(
                        f"pyautogui.moveTo(x={int(p.get('x', 0))}, y={int(p.get('y', 0))}, duration={float(p.get('duration', 0.1))})"
                    )
                elif t == "Mouse Drag":
                    btn = extract_clean_token(p.get("button", "left")) or "left"
                    add_line(f"pyautogui.moveTo({int(p.get('start_x', 0))}, {int(p.get('start_y', 0))})")
                    add_line(
                        f"pyautogui.dragTo({int(p.get('end_x', 0))}, {int(p.get('end_y', 0))}, "
                        f"duration={float(p.get('duration', 0.2))}, button={repr(btn)})"
                    )
                elif t == "Mouse Scroll":
                    add_line(
                        f"pyautogui.scroll({int(p.get('clicks', -3))}, x={int(p.get('x', 0))}, y={int(p.get('y', 0))})"
                    )
                elif t == "Key Press":
                    k = extract_clean_token(p.get("key", "enter")) or "enter"
                    add_line(f"pyautogui.press({repr(k)})")
                elif t == "Key Down":
                    k = extract_clean_token(p.get("key", "shift")) or "shift"
                    add_line(f"pyautogui.keyDown({repr(k)})")
                elif t == "Key Up":
                    k = extract_clean_token(p.get("key", "shift")) or "shift"
                    add_line(f"pyautogui.keyUp({repr(k)})")
                elif t == "Send Text":
                    add_line(
                        f"pyautogui.write({repr(str(p.get('text', '')))}, interval={float(p.get('interval', 0.02))})"
                    )
                elif t == "Hotkey Combo":
                    raw_hk = extract_clean_token(p.get("keys", "ctrl+c"))
                    keys = [extract_clean_token(k) for k in raw_hk.split("+") if k.strip()]
                    args = ", ".join(repr(k) for k in keys if k)
                    add_line(f"pyautogui.hotkey({args})")
                elif t == "Activate Window":
                    add_line(f"activate_window({repr(str(p.get('title', '')))})")
                elif t == "Resize Window":
                    add_line(
                        f"resize_window({repr(str(p.get('title', '')))}, {int(p.get('width', 1280))}, {int(p.get('height', 720))})"
                    )
                elif t == "Move Window":
                    add_line(
                        f"move_window({repr(str(p.get('title', '')))}, {int(p.get('x', 0))}, {int(p.get('y', 0))})"
                    )
                elif t == "Set Window Bounds":
                    ts = repr(str(p.get("title", "")))
                    add_line(f"activate_window({ts})")
                    add_line(f"move_window({ts}, {int(p.get('x', 0))}, {int(p.get('y', 0))})")
                    add_line(f"resize_window({ts}, {int(p.get('width', 1280))}, {int(p.get('height', 720))})")
                elif t == "Sleep (Fixed)":
                    add_line(f"wait_ms({int(p.get('ms', 1000))})")
                elif t == "Sleep (Random)":
                    add_line(
                        f"wait_ms(random.randint({int(p.get('min_ms', 500))}, {int(p.get('max_ms', 1500))}))"
                    )
                elif t == "Click Image On Screen":
                    img = repr(str(p.get("image_path", "")))
                    conf = float(p.get("confidence", 0.85))
                    add_line(f"_pos = pyautogui.locateCenterOnScreen({img}, confidence={conf})")
                    add_line("if _pos is not None:")
                    add_line("    pyautogui.click(_pos)")
                elif t == "Run Command":
                    add_line(f"subprocess.Popen({repr(str(p.get('command', '')))}, shell=True)")

                if step.delay_ms > 0:
                    add_line(f"wait_ms({int(step.delay_ms)})")

                if rep > 1:
                    if not block_has_body.pop():
                        lines.append("    " * indent_level + "pass")
                    indent_level = max(1, indent_level - 1)

            while len(block_has_body) > 1:
                if not block_has_body.pop():
                    lines.append("    " * indent_level + "pass")
                indent_level = max(1, indent_level - 1)

            if not block_has_body[0]:
                add_line("pass")

        lines.append("")
        lines.append('if __name__ == "__main__":')
        if loop_count == 0:
            lines.append("    while True:")
            lines.append("        run_macro()")
        else:
            lines.append(f"    for _run in range({max(1, int(loop_count))}):")
            lines.append("        run_macro()")
        lines.append("")
        return "\n".join(lines)


# =====================================================================
# 4. 巨集執行與錄製引擎 (Playback & Recording Engine)
# =====================================================================

class MacroEngine:
    """負責背景執行緒播放巨集與錄製鍵鼠事件"""

    def __init__(
        self,
        on_log: Callable[[str], None],
        on_step_highlight: Callable[[int], None],
        on_recorded_step: Callable[[MacroStep], None],
        on_state_change: Callable[[str], None],
    ) -> None:
        self.on_log = on_log
        self.on_step_highlight = on_step_highlight
        self.on_recorded_step = on_recorded_step
        self.on_state_change = on_state_change

        self.is_playing = False
        self.is_paused = False
        self.is_recording = False
        self._stop_event = threading.Event()
        self._last_record_ts = 0.0

        self._mouse_listener = None
        self._kb_listener = None
        self.record_mouse_moves = False

        self.ignored_record_keys: Set[str] = {"f9", "f10"}
        self.stop_record_keys: Set[str] = {"f9", "f10"}

    def update_record_hotkeys(self, rec_hk: str, stop_rec_hk: str) -> None:
        def _extract_main(hk: str) -> str:
            parts = [p.strip().lower() for p in hk.split("+") if p.strip()]
            return parts[-1] if parts else ""

        k_rec = _extract_main(rec_hk)
        k_stop = _extract_main(stop_rec_hk)
        self.ignored_record_keys = {k for k in (k_rec, k_stop) if k}
        self.stop_record_keys = {k for k in (k_rec, k_stop) if k}

    def start_recording(
        self,
        record_moves: bool = False,
        stop_hotkey_hint: str = "F10",
    ) -> None:
        if self.is_recording or self.is_playing:
            return
        if not HAS_PYNPUT:
            self.on_log("[提示] 尚未安裝 pynput 套件，無法啟動錄製 (請執行 pip install pynput)。")
            return

        self.record_mouse_moves = record_moves
        self.is_recording = True
        self._last_record_ts = time.time()
        self.on_state_change("Recording")
        self.on_log(f"開始錄製鍵鼠動作（按 {stop_hotkey_hint} 停止錄製）...")

        def _calc_delay() -> int:
            now = time.time()
            diff_ms = int((now - self._last_record_ts) * 1000)
            self._last_record_ts = now
            return max(10, min(diff_ms, 60000))

        def on_click(x: int, y: int, button: Any, pressed: bool) -> None:
            if not self.is_recording or not pressed:
                return
            btn_name = getattr(button, "name", "left")
            if btn_name not in ("left", "right", "middle"):
                btn_name = "left"
            step = MacroStep(
                action_type="Mouse Click",
                params={"button": btn_name, "x": int(x), "y": int(y)},
                delay_ms=_calc_delay(),
                comment="錄製點擊",
            )
            self.on_recorded_step(step)

        def on_scroll(x: int, y: int, dx: int, dy: int) -> None:
            if not self.is_recording or dy == 0:
                return
            step = MacroStep(
                action_type="Mouse Scroll",
                params={"clicks": int(dy * 100), "x": int(x), "y": int(y)},
                delay_ms=_calc_delay(),
                comment="錄製滾輪",
            )
            self.on_recorded_step(step)

        def on_move(x: int, y: int) -> None:
            if not self.is_recording or not self.record_mouse_moves:
                return
            now = time.time()
            if now - self._last_record_ts < 0.15:
                return
            step = MacroStep(
                action_type="Mouse Move",
                params={"x": int(x), "y": int(y), "duration": 0.05},
                delay_ms=_calc_delay(),
                comment="錄製移動",
            )
            self.on_recorded_step(step)

        def on_press(key: Any) -> None:
            if not self.is_recording:
                return
            key_name = getattr(key, "char", None) or getattr(key, "name", str(key))
            clean_key = str(key_name).lower()
            if clean_key in self.stop_record_keys:
                self.stop_recording()
                return
            if clean_key in self.ignored_record_keys:
                return
            step = MacroStep(
                action_type="Key Press",
                params={"key": clean_key},
                delay_ms=_calc_delay(),
                comment="錄製按鍵",
            )
            self.on_recorded_step(step)

        self._mouse_listener = pynput_mouse.Listener(
            on_click=on_click, on_scroll=on_scroll, on_move=on_move
        )
        self._kb_listener = pynput_kb.Listener(on_press=on_press)
        self._mouse_listener.start()
        self._kb_listener.start()

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        self.is_recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None
        self.on_state_change("Ready")
        self.on_log("已停止錄製。")

    def start_playback(
        self,
        steps: List[MacroStep],
        loop_count: int = 1,
        speed_factor: float = 1.0,
        blocking: bool = False,
    ) -> None:
        if self.is_playing or self.is_recording:
            return
        if not steps:
            self.on_log("[提示] 巨集清單為空，請先新增或錄製動作。")
            return

        self.is_playing = True
        self.is_paused = False
        self._stop_event.clear()
        self.on_state_change("Playing")

        if blocking:
            self._playback_worker(copy.deepcopy(steps), loop_count, max(0.1, speed_factor))
        else:
            thread = threading.Thread(
                target=self._playback_worker,
                args=(copy.deepcopy(steps), loop_count, max(0.1, speed_factor)),
                daemon=True,
            )
            thread.start()

    def toggle_pause(self) -> None:
        if not self.is_playing:
            return
        self.is_paused = not self.is_paused
        state = "Paused" if self.is_paused else "Playing"
        self.on_state_change(state)
        self.on_log("巨集已暫停。" if self.is_paused else "巨集繼續執行。")

    def stop_playback(self) -> None:
        if not self.is_playing:
            return
        self._stop_event.set()
        self.is_playing = False
        self.is_paused = False
        self.on_state_change("Ready")
        self.on_log("已中止巨集播放。")

    def _interruptible_sleep(self, ms: float, speed_factor: float) -> None:
        total_sec = (ms / 1000.0) / speed_factor
        end_time = time.time() + total_sec
        while time.time() < end_time:
            if self._stop_event.is_set():
                return
            while self.is_paused and not self._stop_event.is_set():
                time.sleep(0.05)
                end_time += 0.05
            time.sleep(min(0.02, max(0.0, end_time - time.time())))

    def _playback_worker(
        self, steps: List[MacroStep], loop_count: int, speed_factor: float
    ) -> None:
        self.on_log(
            f"開始播放 (共 {len(steps)} 步, 迴圈={'無限' if loop_count == 0 else loop_count}, 倍速={speed_factor}x)"
        )
        run_idx = 0
        try:
            while not self._stop_event.is_set():
                run_idx += 1
                if loop_count > 0 and run_idx > loop_count:
                    break
                self._execute_block(steps, 0, len(steps), speed_factor)
        except Exception as exc:
            self.on_log(f"[錯誤] 播放發生例外: {exc}")
        finally:
            self.is_playing = False
            self.is_paused = False
            self.on_state_change("Ready")
            self.on_log("播放完畢。")

    def _execute_block(
        self, steps: List[MacroStep], start_idx: int, end_idx: int, speed_factor: float
    ) -> None:
        i = start_idx
        while i < end_idx and not self._stop_event.is_set():
            while self.is_paused and not self._stop_event.is_set():
                time.sleep(0.05)

            step = steps[i]
            self.on_step_highlight(i)

            if not step.enabled or step.action_type == "Comment":
                i += 1
                continue

            t = step.action_type
            p = step.params

            if t == "Loop Start":
                loop_end = self._find_matching_end(steps, i, "Loop Start", "Loop End")
                iterations = max(1, int(p.get("count", 1)))
                for _ in range(iterations):
                    if self._stop_event.is_set():
                        break
                    self._execute_block(steps, i + 1, loop_end, speed_factor)
                i = loop_end + 1
                continue

            if t in ("If Pixel Color", "If Image On Screen"):
                else_idx, endif_idx = self._find_if_branches(steps, i)
                cond = self._evaluate_condition(step)
                if cond:
                    branch_end = else_idx if else_idx != -1 else endif_idx
                    self._execute_block(steps, i + 1, branch_end, speed_factor)
                elif else_idx != -1:
                    self._execute_block(steps, else_idx + 1, endif_idx, speed_factor)
                i = endif_idx + 1
                continue

            if t in ("Loop End", "Else", "EndIf"):
                i += 1
                continue

            for _ in range(max(1, int(step.repeat))):
                if self._stop_event.is_set():
                    break
                self._execute_single_action(step, speed_factor)
                if step.delay_ms > 0:
                    self._interruptible_sleep(step.delay_ms, speed_factor)

            i += 1

    @staticmethod
    def _find_matching_end(
        steps: List[MacroStep], start_idx: int, open_tag: str, close_tag: str
    ) -> int:
        depth = 0
        for idx in range(start_idx, len(steps)):
            if steps[idx].action_type == open_tag:
                depth += 1
            elif steps[idx].action_type == close_tag:
                depth -= 1
                if depth == 0:
                    return idx
        return len(steps) - 1

    @staticmethod
    def _find_if_branches(steps: List[MacroStep], start_idx: int) -> Tuple[int, int]:
        depth = 0
        else_idx = -1
        for idx in range(start_idx, len(steps)):
            t = steps[idx].action_type
            if t in ("If Pixel Color", "If Image On Screen"):
                depth += 1
            elif t == "Else" and depth == 1 and else_idx == -1:
                else_idx = idx
            elif t == "EndIf":
                depth -= 1
                if depth == 0:
                    return else_idx, idx
        return else_idx, len(steps) - 1

    def _evaluate_condition(self, step: MacroStep) -> bool:
        if not HAS_PYAUTOGUI:
            self.on_log("[模擬] PyAutoGUI 未啟用，條件預設回傳 True")
            return True
        p = step.params
        if step.action_type == "If Pixel Color":
            x, y = int(p.get("x", 0)), int(p.get("y", 0))
            target = (int(p.get("r", 255)), int(p.get("g", 255)), int(p.get("b", 255)))
            tol = int(p.get("tolerance", 10))
            pix = pyautogui.pixel(x, y)
            return all(abs(int(pix[idx]) - target[idx]) <= tol for idx in range(3))
        if step.action_type == "If Image On Screen":
            path = str(p.get("image_path", ""))
            conf = float(p.get("confidence", 0.85))
            if not os.path.exists(path):
                self.on_log(f"[警告] 找不到圖片: {path}")
                return False
            return pyautogui.locateOnScreen(path, confidence=conf) is not None
        return False

    def _execute_single_action(self, step: MacroStep, speed_factor: float) -> None:
        t = step.action_type
        p = step.params

        if t == "Sleep (Fixed)":
            self._interruptible_sleep(float(p.get("ms", 1000)), speed_factor)
            return
        if t == "Sleep (Random)":
            wait_val = random.randint(int(p.get("min_ms", 500)), int(p.get("max_ms", 1500)))
            self._interruptible_sleep(float(wait_val), speed_factor)
            return
        if t == "Run Command":
            import subprocess

            subprocess.Popen(str(p.get("command", "")), shell=True)
            return

        if t == "Activate Window":
            ok, msg = WindowManager.activate_window(str(p.get("title", "")))
            self.on_log(msg if ok else f"[警告] {msg}")
            return
        if t == "Resize Window":
            ok, msg = WindowManager.resize_window(
                str(p.get("title", "")),
                int(p.get("width", 1280)),
                int(p.get("height", 720)),
            )
            self.on_log(msg if ok else f"[警告] {msg}")
            return
        if t == "Move Window":
            ok, msg = WindowManager.move_window(
                str(p.get("title", "")),
                int(p.get("x", 0)),
                int(p.get("y", 0)),
            )
            self.on_log(msg if ok else f"[警告] {msg}")
            return
        if t == "Set Window Bounds":
            ok, msg = WindowManager.set_window_bounds(
                str(p.get("title", "")),
                int(p.get("x", 0)),
                int(p.get("y", 0)),
                int(p.get("width", 1280)),
                int(p.get("height", 720)),
                activate=True,
            )
            self.on_log(msg if ok else f"[警告] {msg}")
            return

        if not HAS_PYAUTOGUI:
            self.on_log(f"[模擬] {t}: {step.format_details()}")
            return

        if t == "Mouse Click":
            btn = extract_clean_token(p.get("button", "left")) or "left"
            pyautogui.click(x=int(p.get("x", 0)), y=int(p.get("y", 0)), button=btn)
        elif t == "Mouse Double Click":
            btn = extract_clean_token(p.get("button", "left")) or "left"
            pyautogui.doubleClick(x=int(p.get("x", 0)), y=int(p.get("y", 0)), button=btn)
        elif t == "Mouse Move":
            pyautogui.moveTo(
                x=int(p.get("x", 0)),
                y=int(p.get("y", 0)),
                duration=float(p.get("duration", 0.1)) / speed_factor,
            )
        elif t == "Mouse Drag":
            btn = extract_clean_token(p.get("button", "left")) or "left"
            pyautogui.moveTo(int(p.get("start_x", 0)), int(p.get("start_y", 0)))
            pyautogui.dragTo(
                int(p.get("end_x", 0)),
                int(p.get("end_y", 0)),
                duration=float(p.get("duration", 0.2)) / speed_factor,
                button=btn,
            )
        elif t == "Mouse Scroll":
            pyautogui.scroll(
                int(p.get("clicks", -3)),
                x=int(p.get("x", 0)),
                y=int(p.get("y", 0)),
            )
        elif t == "Key Press":
            k = extract_clean_token(p.get("key", "enter")) or "enter"
            pyautogui.press(k)
        elif t == "Key Down":
            k = extract_clean_token(p.get("key", "shift")) or "shift"
            pyautogui.keyDown(k)
        elif t == "Key Up":
            k = extract_clean_token(p.get("key", "shift")) or "shift"
            pyautogui.keyUp(k)
        elif t == "Send Text":
            pyautogui.write(
                str(p.get("text", "")),
                interval=float(p.get("interval", 0.02)) / speed_factor,
            )
        elif t == "Hotkey Combo":
            raw_hk = extract_clean_token(p.get("keys", "ctrl+c"))
            keys = [extract_clean_token(k) for k in raw_hk.split("+") if k.strip()]
            if keys:
                pyautogui.hotkey(*keys)
        elif t == "Click Image On Screen":
            path = str(p.get("image_path", ""))
            conf = float(p.get("confidence", 0.85))
            if os.path.exists(path):
                pos = pyautogui.locateCenterOnScreen(path, confidence=conf)
                if pos is not None:
                    pyautogui.click(pos)




def get_default_sample_steps() -> List[MacroStep]:
    return [
        MacroStep(
            action_type="Comment",
            params={"text": "範例：切換視窗並固定位置與大小後執行按鍵迴圈"},
            delay_ms=0,
            comment="範例說明",
        ),
        MacroStep(
            action_type="Activate Window",
            params={"title": "記事本"},
            delay_ms=200,
            comment="切換至記事本",
        ),
        MacroStep(
            action_type="Set Window Bounds",
            params={"title": "記事本", "x": 100, "y": 100, "width": 1280, "height": 720},
            delay_ms=200,
            comment="固定位置與大小",
        ),
        MacroStep(
            action_type="Loop Start",
            params={"count": 3},
            delay_ms=0,
            comment="重複 3 次",
        ),
        MacroStep(
            action_type="Key Press",
            params={"key": "up"},
            delay_ms=120,
            comment="方向鍵上",
        ),
        MacroStep(
            action_type="Key Press",
            params={"key": "right"},
            delay_ms=120,
            comment="方向鍵右",
        ),
        MacroStep(
            action_type="Loop End",
            params={},
            delay_ms=0,
        ),
    ]

