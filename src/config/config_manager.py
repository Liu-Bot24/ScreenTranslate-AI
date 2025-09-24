"""
配置管理器模块

负责配置的读取、保存、更新和验证。
支持JSON文件持久化，环境变量覆盖，以及与其他模块的集成。
处理文件权限错误和跨平台兼容性。
"""

import json
import os
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from ..utils.path_utils import get_data_dir
from .settings import AppSettings, DEFAULT_SETTINGS
from ..core.llm_client import LLMConfig, APIProvider


class ConfigManager(QObject):
    """配置管理器"""

    # 配置变更信号
    config_changed = pyqtSignal(str)  # 变更的配置节名称
    # 错误信号
    error_occurred = pyqtSignal(str)

    def __init__(self, config_file: Optional[str] = None):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # 配置文件路径
        if config_file:
            self.config_file = Path(config_file)
        else:
            data_dir = get_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = data_dir / "config.json"

        # 当前配置
        self._settings: AppSettings = AppSettings()

        # 线程锁
        self._lock = threading.RLock()

        # 变更监听器
        self._change_listeners: Dict[str, list[Callable]] = {}

        # 加载配置
        self.load()

    def load(self) -> bool:
        """
        从文件加载配置

        Returns:
            bool: 是否加载成功
        """
        with self._lock:
            try:
                if self.config_file.exists():
                    # 从文件加载
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    self._settings = AppSettings.from_dict(data)
                    self.logger.info(f"配置已从文件加载: {self.config_file}")

                else:
                    # 使用默认配置
                    self._settings = AppSettings()
                    self.logger.info("使用默认配置")

                # 应用环境变量覆盖
                self._settings = self._settings.get_env_overrides()

                # 验证配置
                errors = self._settings.validate()
                if errors:
                    self.logger.warning(f"配置验证警告: {errors}")

                return True

            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析错误: {e}")
                self.error_occurred.emit(f"配置文件格式错误: {e}")
                # 使用默认配置
                self._settings = AppSettings()
                return False

            except Exception as e:
                self.logger.error(f"加载配置失败: {e}")
                self.error_occurred.emit(f"加载配置失败: {e}")
                # 使用默认配置
                self._settings = AppSettings()
                return False

    def save(self) -> bool:
        """
        保存配置到文件

        Returns:
            bool: 是否保存成功
        """
        with self._lock:
            try:
                # 确保目录存在
                self.config_file.parent.mkdir(parents=True, exist_ok=True)

                # 准备保存数据
                data = self._settings.to_dict()

                # 添加保存时间戳
                data["_last_saved"] = datetime.now().isoformat()

                # 创建备份
                self._create_backup()

                # 保存到临时文件，然后替换原文件（原子操作）
                temp_file = self.config_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # 替换原文件
                if self.config_file.exists():
                    self.config_file.unlink()
                temp_file.rename(self.config_file)

                self.logger.info(f"配置已保存到: {self.config_file}")
                return True

            except PermissionError as e:
                self.logger.error(f"权限错误: {e}")
                self.error_occurred.emit(f"没有权限保存配置文件: {e}")
                return False

            except Exception as e:
                self.logger.error(f"保存配置失败: {e}")
                self.error_occurred.emit(f"保存配置失败: {e}")
                return False

    def get_settings(self) -> AppSettings:
        """
        获取当前配置

        Returns:
            AppSettings: 当前配置对象
        """
        with self._lock:
            return self._settings

    def update_llm_settings(self, **kwargs) -> bool:
        """
        更新LLM配置

        Args:
            **kwargs: LLM配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.llm, key):
                        setattr(self._settings.llm, key, value)

                # 验证配置
                errors = self._settings.llm.validate()
                if errors:
                    self.logger.warning(f"LLM配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("llm")
                self.config_changed.emit("llm")

                self.logger.info("LLM配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新LLM配置失败: {e}")
                self.error_occurred.emit(f"更新LLM配置失败: {e}")
                return False

    def update_hotkey_settings(self, **kwargs) -> bool:
        """
        更新热键配置

        Args:
            **kwargs: 热键配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.hotkey, key):
                        setattr(self._settings.hotkey, key, value)

                # 验证配置
                errors = self._settings.hotkey.validate()
                if errors:
                    self.logger.warning(f"热键配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("hotkey")
                self.config_changed.emit("hotkey")

                self.logger.info("热键配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新热键配置失败: {e}")
                self.error_occurred.emit(f"更新热键配置失败: {e}")
                return False

    def update_ui_settings(self, **kwargs) -> bool:
        """
        更新界面配置

        Args:
            **kwargs: 界面配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.ui, key):
                        setattr(self._settings.ui, key, value)

                # 验证配置
                errors = self._settings.ui.validate()
                if errors:
                    self.logger.warning(f"界面配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("ui")
                self.config_changed.emit("ui")

                self.logger.info("界面配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新界面配置失败: {e}")
                self.error_occurred.emit(f"更新界面配置失败: {e}")
                return False

    def update_ocr_settings(self, **kwargs) -> bool:
        """
        更新OCR配置

        Args:
            **kwargs: OCR配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.ocr, key):
                        setattr(self._settings.ocr, key, value)

                # 验证配置
                errors = self._settings.ocr.validate()
                if errors:
                    self.logger.warning(f"OCR配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("ocr")
                self.config_changed.emit("ocr")

                self.logger.info("OCR配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新OCR配置失败: {e}")
                self.error_occurred.emit(f"更新OCR配置失败: {e}")
                return False

    def update_prompt_settings(self, **kwargs) -> bool:
        """
        更新Prompt配置

        Args:
            **kwargs: Prompt配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.prompt, key):
                        setattr(self._settings.prompt, key, value)

                # 验证配置
                errors = self._settings.prompt.validate()
                if errors:
                    self.logger.warning(f"Prompt配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("prompt")
                self.config_changed.emit("prompt")

                self.logger.info("Prompt配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新Prompt配置失败: {e}")
                self.error_occurred.emit(f"更新Prompt配置失败: {e}")
                return False

    def update_history_settings(self, **kwargs) -> bool:
        """
        更新历史记录配置

        Args:
            **kwargs: 历史记录配置参数

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            try:
                # 更新字段
                for key, value in kwargs.items():
                    if hasattr(self._settings.history, key):
                        setattr(self._settings.history, key, value)

                # 验证配置
                errors = self._settings.history.validate()
                if errors:
                    self.logger.warning(f"历史记录配置验证警告: {errors}")

                # 触发变更事件
                self._notify_change("history")
                self.config_changed.emit("history")

                self.logger.info("历史记录配置已更新")
                return True

            except Exception as e:
                self.logger.error(f"更新历史记录配置失败: {e}")
                self.error_occurred.emit(f"更新历史记录配置失败: {e}")
                return False

    def get_llm_config(self) -> LLMConfig:
        """
        获取LLM客户端配置对象

        Returns:
            LLMConfig: LLM配置对象
        """
        with self._lock:
            settings = self._settings.llm

            # 转换提供商
            provider_map = {
                "siliconflow": APIProvider.SILICONFLOW,
                "doubao": APIProvider.DOUBAO,
                "openai": APIProvider.OPENAI,
                "custom": APIProvider.CUSTOM
            }

            provider = provider_map.get(settings.provider, APIProvider.CUSTOM)

            return LLMConfig(
                provider=provider,
                api_key=settings.api_key,
                api_endpoint=settings.api_endpoint,
                model_name=settings.model_name,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens
            )

    def get_hotkey_config(self) -> Dict[str, Any]:
        """
        获取热键配置字典

        Returns:
            Dict[str, Any]: 热键配置
        """
        with self._lock:
            return {
                "modifiers": self._settings.hotkey.modifiers,
                "key": self._settings.hotkey.key,
                "enabled": self._settings.hotkey.enabled
            }

    def reset_to_defaults(self, section: Optional[str] = None) -> bool:
        """
        重置配置为默认值

        Args:
            section: 要重置的配置节，None表示重置全部

        Returns:
            bool: 是否重置成功
        """
        with self._lock:
            try:
                if section is None:
                    # 重置全部配置
                    self._settings = AppSettings()
                    self.logger.info("所有配置已重置为默认值")
                    self.config_changed.emit("all")

                elif section == "llm":
                    self._settings.llm = DEFAULT_SETTINGS.llm
                    self.config_changed.emit("llm")

                elif section == "hotkey":
                    self._settings.hotkey = DEFAULT_SETTINGS.hotkey
                    self.config_changed.emit("hotkey")

                elif section == "ui":
                    self._settings.ui = DEFAULT_SETTINGS.ui
                    self.config_changed.emit("ui")

                elif section == "ocr":
                    self._settings.ocr = DEFAULT_SETTINGS.ocr
                    self.config_changed.emit("ocr")

                elif section == "prompt":
                    self._settings.prompt = DEFAULT_SETTINGS.prompt
                    self.config_changed.emit("prompt")

                elif section == "history":
                    self._settings.history = DEFAULT_SETTINGS.history
                    self.config_changed.emit("history")

                else:
                    self.logger.warning(f"未知的配置节: {section}")
                    return False

                self.logger.info(f"配置节 '{section}' 已重置为默认值")
                return True

            except Exception as e:
                self.logger.error(f"重置配置失败: {e}")
                self.error_occurred.emit(f"重置配置失败: {e}")
                return False

    def add_change_listener(self, section: str, callback: Callable):
        """
        添加配置变更监听器

        Args:
            section: 配置节名称
            callback: 回调函数
        """
        if section not in self._change_listeners:
            self._change_listeners[section] = []
        self._change_listeners[section].append(callback)

    def remove_change_listener(self, section: str, callback: Callable):
        """
        移除配置变更监听器

        Args:
            section: 配置节名称
            callback: 回调函数
        """
        if section in self._change_listeners:
            try:
                self._change_listeners[section].remove(callback)
            except ValueError:
                pass

    def _notify_change(self, section: str):
        """
        通知配置变更

        Args:
            section: 变更的配置节
        """
        if section in self._change_listeners:
            for callback in self._change_listeners[section]:
                try:
                    callback()
                except Exception as e:
                    self.logger.error(f"配置变更回调执行失败: {e}")

    def _create_backup(self):
        """创建配置文件备份"""
        try:
            if self.config_file.exists():
                backup_file = self.config_file.with_suffix('.bak')
                backup_file.write_bytes(self.config_file.read_bytes())
                self.logger.debug(f"配置备份已创建: {backup_file}")
        except Exception as e:
            self.logger.warning(f"创建配置备份失败: {e}")

    def get_config_file_path(self) -> str:
        """
        获取配置文件路径

        Returns:
            str: 配置文件路径
        """
        return str(self.config_file)

    def is_config_valid(self) -> bool:
        """
        检查当前配置是否有效

        Returns:
            bool: 是否有效
        """
        with self._lock:
            return self._settings.is_valid()

    def get_validation_errors(self) -> Dict[str, Any]:
        """
        获取配置验证错误

        Returns:
            Dict[str, Any]: 验证错误
        """
        with self._lock:
            return self._settings.validate()

    def export_config(self, file_path: str) -> bool:
        """
        导出配置到指定文件

        Args:
            file_path: 目标文件路径

        Returns:
            bool: 是否导出成功
        """
        try:
            with self._lock:
                data = self._settings.to_dict()
                # 添加导出信息
                data["_exported_at"] = datetime.now().isoformat()
                data["_exported_from"] = str(self.config_file)

                export_path = Path(file_path)
                export_path.parent.mkdir(parents=True, exist_ok=True)

                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                self.logger.info(f"配置已导出到: {export_path}")
                return True

        except Exception as e:
            self.logger.error(f"导出配置失败: {e}")
            self.error_occurred.emit(f"导出配置失败: {e}")
            return False

    def import_config(self, file_path: str) -> bool:
        """
        从指定文件导入配置

        Args:
            file_path: 源文件路径

        Returns:
            bool: 是否导入成功
        """
        try:
            import_path = Path(file_path)
            if not import_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {import_path}")

            with open(import_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 移除导入/导出元数据
            data.pop("_exported_at", None)
            data.pop("_exported_from", None)
            data.pop("_last_saved", None)

            with self._lock:
                self._settings = AppSettings.from_dict(data)

                # 验证配置
                errors = self._settings.validate()
                if errors:
                    self.logger.warning(f"导入的配置验证警告: {errors}")

                self.logger.info(f"配置已从文件导入: {import_path}")
                self.config_changed.emit("all")
                return True

        except Exception as e:
            self.logger.error(f"导入配置失败: {e}")
            self.error_occurred.emit(f"导入配置失败: {e}")
            return False


# 全局配置管理器实例
_global_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """
    获取全局配置管理器实例（单例模式）

    Returns:
        ConfigManager: 配置管理器实例
    """
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager


def set_config_manager(manager: ConfigManager):
    """
    设置全局配置管理器实例

    Args:
        manager: 配置管理器实例
    """
    global _global_config_manager
    _global_config_manager = manager


def cleanup_config_manager():
    """清理全局配置管理器"""
    global _global_config_manager
    if _global_config_manager:
        # 保存配置
        _global_config_manager.save()
        _global_config_manager = None

