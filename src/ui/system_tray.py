"""
系统托盘界面模块

实现系统托盘图标和菜单，管理应用程序生命周期。
支持跨平台托盘功能，集成热键管理和配置系统。
"""

import sys
import platform
import logging
from pathlib import Path
from typing import Optional, Dict, Callable

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QMessageBox,
                           QWidget, QMainWindow)
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QFont, QAction

from ..config.config_manager import ConfigManager, get_config_manager
from ..core.hotkey_manager import HotkeyManager, get_hotkey_manager
from .settings_window import SettingsWindow


class SystemTrayIcon(QSystemTrayIcon):
    """系统托盘图标类"""

    # 自定义信号
    screenshot_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    history_requested = pyqtSignal()
    about_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 管理器实例
        self.config_manager: Optional[ConfigManager] = None
        self.hotkey_manager: Optional[HotkeyManager] = None
        self._screenshot_handler: Optional[Callable[[], bool]] = None

        # 设置窗口和历史窗口引用
        self.settings_window: Optional[QWidget] = None
        self.history_window: Optional[QWidget] = None

        # 系统平台
        self.platform = platform.system().lower()

        # 初始化
        self.init_managers()
        self.setup_icon()
        self.setup_menu()
        self.setup_signals()

        # 启动热键监听
        self.start_hotkey_listening()

        self.logger.info("系统托盘已初始化")

    def init_managers(self):
        """初始化管理器"""
        try:
            # 获取配置管理器
            self.config_manager = get_config_manager()

            # 获取热键管理器
            self.hotkey_manager = get_hotkey_manager()

            self.logger.info("管理器初始化完成")

        except Exception as e:
            self.logger.error(f"管理器初始化失败: {e}")
            self.show_error_message("初始化失败", f"管理器初始化失败: {e}")

    def setup_icon(self):
        """设置托盘图标"""
        try:
            # 首先尝试从根目录加载 ico.png
            project_root = Path(__file__).parent.parent.parent
            icon_path = project_root / "ico.png"

            if icon_path.exists():
                icon = QIcon(str(icon_path))
                self.logger.info(f"加载托盘图标: {icon_path}")
            else:
                # 备用方案：尝试从资源目录加载图标
                backup_icon_path = project_root / "resources" / "icons" / "tray_icon.png"
                if backup_icon_path.exists():
                    icon = QIcon(str(backup_icon_path))
                    self.logger.info(f"加载备用托盘图标: {backup_icon_path}")
                else:
                    # 如果没有图标文件，创建默认图标
                    icon = self.create_default_icon()
                    self.logger.info("使用默认托盘图标")

            self.setIcon(icon)

            # 设置悬停提示
            self.setToolTip("ScreenTranslate-AI - 屏幕翻译助手")

        except Exception as e:
            self.logger.error(f"设置托盘图标失败: {e}")
            # 使用系统默认图标
            self.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))

    def create_default_icon(self) -> QIcon:
        """创建默认托盘图标"""
        try:
            # 创建32x32像素的图标
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 绘制圆形背景
            painter.setBrush(Qt.GlobalColor.blue)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, 28, 28)

            # 绘制文字 "ST"
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "ST")

            painter.end()

            return QIcon(pixmap)

        except Exception as e:
            self.logger.error(f"创建默认图标失败: {e}")
            return QIcon()

    def setup_menu(self):
        """设置右键菜单"""
        try:
            menu = QMenu()

            # 截图动作
            screenshot_action = QAction("开始截图", self)
            screenshot_action.setToolTip("触发屏幕截图功能")
            screenshot_action.triggered.connect(self.trigger_screenshot)
            menu.addAction(screenshot_action)

            menu.addSeparator()

            # 设置动作
            settings_action = QAction("设置", self)
            settings_action.setToolTip("打开设置窗口")
            settings_action.triggered.connect(self.show_settings)
            menu.addAction(settings_action)

            # 历史记录动作
            history_action = QAction("历史记录", self)
            history_action.setToolTip("查看翻译历史")
            history_action.triggered.connect(self.show_history)
            menu.addAction(history_action)

            menu.addSeparator()

            # 关于动作
            about_action = QAction("关于", self)
            about_action.triggered.connect(self.show_about)
            menu.addAction(about_action)

            # 退出动作
            quit_action = QAction("退出", self)
            quit_action.setToolTip("退出应用程序")
            quit_action.triggered.connect(self.quit_application)
            menu.addAction(quit_action)

            self.setContextMenu(menu)

            self.logger.info("托盘菜单设置完成")

        except Exception as e:
            self.logger.error(f"设置托盘菜单失败: {e}")

    def setup_signals(self):
        """设置信号连接"""
        try:
            # 托盘图标激活信号
            self.activated.connect(self.on_tray_activated)

            # 配置变更信号
            if self.config_manager:
                self.config_manager.config_changed.connect(self.on_config_changed)

            # 热键触发信号
            if self.hotkey_manager:
                self.hotkey_manager.hotkey_triggered.connect(self.on_hotkey_triggered)
                self.hotkey_manager.status_changed.connect(self.on_hotkey_status_changed)
                self.hotkey_manager.error_occurred.connect(
                    lambda message: self.show_warning_message("热键错误", message)
                )

            self.logger.info("信号连接设置完成")

        except Exception as e:
            self.logger.error(f"设置信号连接失败: {e}")

    def set_screenshot_handler(self, handler: Optional[Callable[[], bool]]):
        """设置截图处理回调"""
        self._screenshot_handler = handler

    def start_hotkey_listening(self):
        """启动热键监听"""
        try:
            if self.hotkey_manager:
                if self.config_manager:
                    self._apply_hotkey_settings()

                    settings = self.config_manager.get_settings()
                    if not settings.hotkey.enabled:
                        self.logger.info("热键在设置中被禁用，保持关闭状态")
                        return

                # 设置截图回调
                self.hotkey_manager.set_hotkey_callback("screenshot", self.trigger_screenshot)

                # 开始监听
                success = self.hotkey_manager.start_listening()
                if success:
                    if self.config_manager:
                        settings = self.config_manager.get_settings()
                        display = settings.hotkey.get_display_text()
                    else:
                        display = ""
                    self.logger.info("热键监听已启动: %s", display)
                else:
                    self.logger.warning("热键监听启动失败")
                    self.show_warning_message("热键警告",
                                           "无法启动热键监听，请检查权限设置。\n"
                                           "在macOS上，您可能需要在系统偏好设置中启用辅助功能权限。")

        except Exception as e:
            self.logger.error(f"启动热键监听失败: {e}")

    def _apply_hotkey_settings(self):
        """同步配置中的热键设置"""
        try:
            if not (self.config_manager and self.hotkey_manager):
                return

            settings = self.config_manager.get_settings()
            modifiers = settings.hotkey.modifiers if settings else []
            key = settings.hotkey.key if settings else ""

            if not key:
                key = "x"  # fallback to default

            updated = self.hotkey_manager.update_hotkey_config(
                "screenshot",
                modifiers,
                key
            )

            if updated:
                self.logger.info(
                    "热键同步完成: %s",
                    settings.hotkey.get_display_text() if settings else ""
                )

        except Exception as e:
            self.logger.error(f"同步热键配置失败: {e}")

    def on_tray_activated(self, reason):
        """托盘图标激活处理"""
        try:
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                # 双击触发截图
                self.trigger_screenshot()
                self.logger.debug("托盘图标双击，触发截图")

            elif reason == QSystemTrayIcon.ActivationReason.Trigger:
                # 单击行为（在某些平台上）
                if self.platform == "linux":
                    # Linux上单击显示菜单
                    pass
                elif self.platform == "darwin":
                    # macOS上的行为
                    pass

        except Exception as e:
            self.logger.error(f"托盘激活处理失败: {e}")

    def trigger_screenshot(self) -> bool:
        """触发截图"""
        try:
            self.logger.debug("系统托盘请求截图")
            self.screenshot_requested.emit()

            handled = False
            if self._screenshot_handler:
                try:
                    handled = bool(self._screenshot_handler())
                except Exception as callback_error:
                    handled = False
                    self.logger.error(f"截图处理回调执行失败: {callback_error}")
                    self.show_error_message("截图错误", f"触发截图时发生错误: {callback_error}")
                    return False

            if handled:
                self.logger.info("截图流程已启动")
                self.showMessage("ScreenTranslate-AI",
                               "截图已启动，请选择要翻译的区域",
                               QSystemTrayIcon.MessageIcon.Information, 3000)
            else:
                if self._screenshot_handler:
                    self.logger.warning("截图处理回调返回 False")
                    self.show_warning_message("截图失败", "无法启动截图功能")
                else:
                    self.logger.debug("未设置截图处理回调，仅发出截图请求信号")

            return handled

        except Exception as e:
            self.logger.error(f"触发截图失败: {e}")
            self.show_error_message("截图错误", f"触发截图时发生错误: {e}")
            return False

    def show_settings(self):
        """显示设置窗口"""
        try:
            if self.settings_window:
                if self.settings_window.isMinimized():
                    self.settings_window.showNormal()
                self.settings_window.show()
                self.settings_window.raise_()
                self.settings_window.activateWindow()
            else:
                self.settings_requested.emit()
                self.logger.info("请求显示设置窗口")

        except Exception as e:
            self.logger.error(f"显示设置窗口失败: {e}")

    def show_history(self):
        """显示历史记录窗口"""
        try:
            if self.history_window:
                if self.history_window.isMinimized():
                    self.history_window.showNormal()
                self.history_window.show()
                self.history_window.raise_()
                self.history_window.activateWindow()
            else:
                self.history_requested.emit()
                self.logger.info("请求显示历史记录窗口")

        except Exception as e:
            self.logger.error(f"显示历史记录窗口失败: {e}")

    def show_about(self):
        """显示关于对话框"""
        try:
            # 获取当前热键配置
            config_manager = get_config_manager()
            settings = config_manager.get_settings()
            hotkey_display = settings.hotkey.get_display_text()

            about_text = f"""
<h3>ScreenTranslate-AI</h3>
<p>版本: 1.0.0</p>
<p>一款通过截图、OCR和大型语言模型实现屏幕内容即时翻译和解释的桌面效率工具。</p>
<p><b>功能特性:</b></p>
<ul>
<li>全局快捷键截图</li>
<li>智能文字识别(OCR)</li>
<li>多语言实时翻译</li>
<li>历史记录管理</li>
<li>自定义配置</li>
</ul>
<p><b>当前热键:</b> {hotkey_display}</p>
<p><b>双击托盘图标:</b> 开始截图</p>
            """

            QMessageBox.about(None, "关于 ScreenTranslate-AI", about_text)
            self.logger.info("显示关于对话框")

        except Exception as e:
            self.logger.error(f"显示关于对话框失败: {e}")

    def quit_application(self):
        """退出应用程序"""
        try:
            # 询问用户确认
            reply = QMessageBox.question(None, "退出确认",
                                       "确定要退出 ScreenTranslate-AI 吗？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                self.logger.info("用户确认退出应用程序")
                self.cleanup()
                QApplication.quit()

        except Exception as e:
            self.logger.error(f"退出应用程序失败: {e}")
            # 强制退出
            QApplication.quit()

    def cleanup(self):
        """清理资源"""
        try:
            self.logger.info("开始清理系统托盘资源")

            # 停止热键监听
            if self.hotkey_manager:
                self.hotkey_manager.stop_listening()

            # 保存配置
            if self.config_manager:
                self.config_manager.save()

            # 隐藏托盘图标
            self.hide()

            self.logger.info("系统托盘资源清理完成")

        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")

    def on_config_changed(self, section: str):
        """配置变更处理"""
        try:
            if section == "hotkey":
                if self.hotkey_manager:
                    # 先停止当前监听
                    if self.hotkey_manager.is_listening():
                        self.hotkey_manager.stop_listening()

                    # 延时后重启监听（让start_hotkey_listening自己处理配置更新）
                    QTimer.singleShot(100, self.start_hotkey_listening)

                self.logger.info("热键配置已更新")

        except Exception as e:
            self.logger.error(f"处理配置变更失败: {e}")

    def on_hotkey_triggered(self, name: str):
        """热键触发处理"""
        try:
            if name == "screenshot":
                self.trigger_screenshot()
                self.logger.debug(f"热键触发: {name}")

        except Exception as e:
            self.logger.error(f"处理热键触发失败: {e}")

    def on_hotkey_status_changed(self, is_listening: bool):
        """热键状态变更处理"""
        try:
            status_text = "启用" if is_listening else "禁用"
            self.logger.info(f"热键状态变更: {status_text}")

        except Exception as e:
            self.logger.error(f"处理热键状态变更失败: {e}")

    def on_screenshot_taken(self, image, x, y, width, height):
        """截图完成处理"""
        try:
            self.logger.info(f"截图完成: 区域({x}, {y}, {width}x{height})")
            self.showMessage("ScreenTranslate-AI",
                           f"截图完成，区域: {width}x{height}",
                           QSystemTrayIcon.MessageIcon.Information, 2000)

            # 这里可以触发OCR和翻译流程
            # TODO: 集成OCR和LLM处理

        except Exception as e:
            self.logger.error(f"处理截图完成失败: {e}")

    def on_screenshot_cancelled(self):
        """截图取消处理"""
        try:
            self.logger.info("截图已取消")

        except Exception as e:
            self.logger.error(f"处理截图取消失败: {e}")

    def on_screenshot_error(self, error: str):
        """截图错误处理"""
        try:
            self.logger.error(f"截图错误: {error}")
            self.show_error_message("截图错误", error)

        except Exception as e:
            self.logger.error(f"处理截图错误失败: {e}")

    def show_error_message(self, title: str, message: str):
        """显示错误消息"""
        try:
            QMessageBox.critical(None, title, message)

        except Exception as e:
            self.logger.error(f"显示错误消息失败: {e}")

    def show_warning_message(self, title: str, message: str):
        """显示警告消息"""
        try:
            QMessageBox.warning(None, title, message)

        except Exception as e:
            self.logger.error(f"显示警告消息失败: {e}")

    def show_info_message(self, title: str, message: str):
        """显示信息消息"""
        try:
            QMessageBox.information(None, title, message)

        except Exception as e:
            self.logger.error(f"显示信息消息失败: {e}")

    def set_settings_window(self, window: QWidget):
        """设置设置窗口引用"""
        self.settings_window = window

    def set_history_window(self, window: QWidget):
        """设置历史记录窗口引用"""
        self.history_window = window

    def is_tray_available(self) -> bool:
        """检查系统托盘是否可用"""
        return QSystemTrayIcon.isSystemTrayAvailable()


class TrayApplication(QObject):
    """托盘应用程序主类"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        self.tray_icon: Optional[SystemTrayIcon] = None
        self.settings_window: Optional[QWidget] = None
        self.history_window: Optional[QWidget] = None

        # 初始化
        self.init_application()

    def init_application(self):
        """初始化应用程序"""
        try:
            # 检查系统托盘支持
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.logger.error("系统不支持系统托盘")
                QMessageBox.critical(None, "系统托盘不可用",
                                   "系统不支持系统托盘功能，应用程序无法运行。")
                return False

            # 创建托盘图标
            self.tray_icon = SystemTrayIcon()

            # 显示托盘图标
            self.tray_icon.show()

            self.logger.info("托盘应用程序初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"初始化托盘应用程序失败: {e}")
            return False

    def show_settings_window(self):
        """显示设置窗口"""
        if self.tray_icon:
            self.tray_icon.show_settings()

    def show_history_window(self):
        """显示历史记录窗口"""
        if self.tray_icon:
            self.tray_icon.show_history()

    def cleanup(self):
        """清理应用程序资源"""
        try:
            if self.tray_icon:
                self.tray_icon.cleanup()

            # 清理全局管理器
            from ..config.config_manager import cleanup_config_manager
            from ..core.hotkey_manager import cleanup_hotkey_manager

            cleanup_config_manager()
            cleanup_hotkey_manager()

            self.logger.info("托盘应用程序资源清理完成")

        except Exception as e:
            self.logger.error(f"清理应用程序资源失败: {e}")


def create_tray_application() -> TrayApplication:
    """创建托盘应用程序实例"""
    return TrayApplication()
