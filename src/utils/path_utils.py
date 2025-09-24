from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

APP_NAME = "ScreenTranslate-AI"
ENV_DATA_DIR = "SCREENTRANSLATE_DATA_DIR"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 等冻结环境中"""
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    """获取源码环境下的项目根目录"""
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "main.py").exists():
            if candidate.name.lower() == "src" and (candidate.parent / "main.py").exists():
                return candidate.parent
            return candidate
    return current.parents[-1]


def _get_platform_data_root() -> Path:
    """获取不同平台下的默认用户数据根目录"""
    system = platform.system().lower()

    if system == "windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"

    if system == "darwin":
        return Path.home() / "Library" / "Application Support"

    xdg_home = os.getenv("XDG_DATA_HOME")
    if xdg_home:
        return Path(xdg_home)
    return Path.home() / ".local" / "share"


def get_data_dir() -> Path:
    """获取持久化数据目录。"""
    env_override = os.getenv(ENV_DATA_DIR)
    if env_override:
        return Path(env_override).expanduser().resolve()

    if is_frozen():
        return Path(sys.executable).resolve().parent

    return get_project_root() / "data"


def get_runtime_working_dir() -> Path:
    """获取程序运行时应使用的工作目录"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return get_project_root()
