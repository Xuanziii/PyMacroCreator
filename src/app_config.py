#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyMacroCreator — 應用程式偏好設定與上次開啟存檔持久化模組
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional


class AppConfig:
    """管理應用程式設定（主題模式、上次開啟/儲存的專案路徑、視窗大小等）。"""

    DEFAULT_DATA: Dict[str, Any] = {
        "theme_mode": "dark",
        "last_project_path": "",
        "record_mouse_moves": False,
        "window_geometry": "1240x800",
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path:
            self.config_path = config_path
        else:
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidate = os.path.join(base_dir, "pymacrocreator_config.json")
            if self._is_dir_writable(base_dir):
                self.config_path = candidate
            else:
                self.config_path = os.path.join(
                    os.path.expanduser("~"), ".pymacrocreator_config.json"
                )
        self.data: Dict[str, Any] = dict(self.DEFAULT_DATA)
        self.load()

    @staticmethod
    def _is_dir_writable(path: str) -> bool:
        try:
            return os.path.isdir(path) and os.access(path, os.W_OK)
        except Exception:
            return False

    def load(self) -> None:
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except Exception:
            pass

    def save(self) -> None:
        try:
            parent = os.path.dirname(self.config_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_last_project_path(self) -> Optional[str]:
        path = str(self.data.get("last_project_path", "")).strip()
        if path and os.path.isfile(path):
            return path
        return None

    def set_last_project_path(self, path: Optional[str]) -> None:
        if path:
            self.data["last_project_path"] = os.path.abspath(path)
        else:
            self.data["last_project_path"] = ""
        self.save()

    def get_theme_mode(self) -> str:
        mode = str(self.data.get("theme_mode", "dark")).lower()
        return mode if mode in ("dark", "light") else "dark"

    def set_theme_mode(self, mode: str) -> None:
        if mode in ("dark", "light"):
            self.data["theme_mode"] = mode
            self.save()

    def get_record_mouse_moves(self) -> bool:
        return bool(self.data.get("record_mouse_moves", False))

    def set_record_mouse_moves(self, enabled: bool) -> None:
        self.data["record_mouse_moves"] = bool(enabled)
        self.save()

    def get_window_geometry(self) -> str:
        geo = str(self.data.get("window_geometry", "1240x800")).strip()
        return geo if "x" in geo else "1240x800"

    def set_window_geometry(self, geometry: str) -> None:
        if geometry and "x" in geometry:
            self.data["window_geometry"] = geometry
            self.save()
