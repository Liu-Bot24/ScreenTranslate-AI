# -*- coding: utf-8 -*-
"""
ScreenTranslate-AI 主程序入口

集成所有模块，实现完整的截图→OCR→翻译→显示→历史记录工作流。
支持系统托盘界面和全局热键控制。
"""

import sys
import os
import logging
import platform
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, pyqtSlot, Qt, QRect
from PyQt6.QtGui import QIcon, QImage
from PIL import Image

# 导入项目模块
from .config.config_manager import get_config_manager, cleanup_config_manager
from .core.hotkey_manager import get_hotkey_manager, cleanup_hotkey_manager
from .core.ocr_engine import get_ocr_engine, cleanup_ocr_engine
from .core.llm_client import LLMClient, LLMConfig, LLMResponse, LLMError
from .utils.history_manager import get_history_manager, cleanup_history_manager
from .utils.prompt_templates import format_prompt
from .ui.system_tray import create_tray_application
from .ui.result_window import ResultWindow, ResultData, ResultType
from .ui.settings_window import SettingsWindow
from .ui.screenshot_overlay import ScreenshotOverlay
from .ui.history_window import create_history_window


class WorkflowThread(QThread):
    """工作流处理线程"""

    # 信号
    workflow_started = pyqtSignal()
    ocr_completed = pyqtSignal(str)  # OCR结果
    translation_completed = pyqtSignal(object)  # LLMResponse
    workflow_completed = pyqtSignal(object)  # ResultData
    error_occurred = pyqtSignal(str, str)  # 错误类型, 错误消息

    def __init__(self, image, screenshot_region):
        super().__init__()
        self.image = image
        self.screenshot_region = screenshot_region  # (x, y, width, height)
        self.logger = logging.getLogger(__name__)

        # 模块引用
        self.ocr_engine = None
        self.llm_client = None
        self.history_manager = None
        self.config_manager = None

    def run(self):
        """执行完整工作流"""
        try:
            self.workflow_started.emit()

            # 初始化模块
            self._init_modules()

            # 1. OCR识别
            ocr_text = self._perform_ocr()
            if not ocr_text.strip():
                self._emit_error("OCR", "未识别到任何文本内容")
                return

            self.ocr_completed.emit(ocr_text)

            # 2. LLM翻译
            translation_response = self._perform_translation(ocr_text)
            if not translation_response:
                self._emit_error("Translation", "翻译请求失败")
                return

            self.translation_completed.emit(translation_response)

            # 3. 保存历史记录
            self._save_to_history(ocr_text, translation_response.content)

            # 4. 构造结果数据
            result_data = ResultData(
                original_text=ocr_text,
                translated_text=translation_response.content,
                result_type=ResultType.SUCCESS,
                metadata={
                    'screenshot_region': self.screenshot_region,
                    'provider': translation_response.provider,
                    'model': translation_response.model,
                    'timestamp': datetime.now().isoformat()
                }
            )

            self.workflow_completed.emit(result_data)
            self.logger.info("工作流执行完成")

        except Exception as e:
            self.logger.error(f"工作流执行失败: {e}")
            self._emit_error("Workflow", f"工作流执行失败: {str(e)}")

    def _init_modules(self):
        """初始化模块"""
        self.config_manager = get_config_manager()
        self.ocr_engine = get_ocr_engine()
        self.llm_client = LLMClient()
        self.history_manager = get_history_manager()

    def _perform_ocr(self) -> str:
        """执行OCR识别"""
        try:
            self.logger.info("开始OCR识别")
            text = self.ocr_engine.recognize_image(self.image)
            self.logger.info(f"OCR识别完成，文本长度: {len(text)}")
            return text
        except Exception as e:
            self.logger.error(f"OCR识别失败: {e}")
            raise

    def _perform_translation(self, text: str) -> Optional[LLMResponse]:
        """执行翻译"""
        try:
            self.logger.info("开始LLM翻译")

            # 获取配置
            settings = self.config_manager.get_settings()

            # 构造LLM配置
            from .core.llm_client import APIProvider
            provider = APIProvider(settings.llm.provider)

            llm_config = LLMConfig(
                provider=provider,
                api_key=settings.llm.api_key,
                api_endpoint=settings.llm.api_endpoint,
                model_name=settings.llm.model_name,
                max_tokens=settings.llm.max_tokens,
                temperature=settings.llm.temperature,
                timeout=settings.llm.timeout
            )

            # 选择并格式化Prompt
            template_name = settings.prompt.active_template or "translate"
            prompt = format_prompt(
                template_name=template_name,
                text=text,
                target_language=settings.translation.target_language,
                source_language=settings.translation.source_language
            )

            if not prompt:
                self.logger.warning(
                    "Prompt模板 '%s' 不存在，使用默认模板 'translate'",
                    template_name
                )
                prompt = format_prompt(
                    template_name="translate",
                    text=text,
                    target_language=settings.translation.target_language,
                    source_language=settings.translation.source_language
                )

            if not prompt:
                raise ValueError("无法加载可用的Prompt模板")

            # 设置配置并同步调用翻译
            self.llm_client.set_config(llm_config)
            import asyncio
            response = asyncio.run(self.llm_client.generate_response(prompt))

            self.logger.info("LLM翻译完成")
            return response

        except Exception as e:
            self.logger.error(f"LLM翻译失败: {e}")
            raise

    def _save_to_history(self, original_text: str, translated_text: str):
        """保存到历史记录"""
        try:
            if self.history_manager:
                settings = self.config_manager.get_settings()
                record_id = self.history_manager.add_record(
                    original_text=original_text,
                    translated_text=translated_text,
                    source_language=settings.translation.source_language,
                    target_language=settings.translation.target_language,
                    metadata={
                        'screenshot_region': self.screenshot_region,
                        'provider': settings.llm.provider,
                        'model': settings.llm.model_name
                    }
                )
                if record_id:
                    self.logger.info(f"已保存到历史记录: {record_id}")
        except Exception as e:
            self.logger.error(f"保存历史记录失败: {e}")

    def _emit_error(self, error_type: str, message: str):
        """发出错误信号"""
        self.error_occurred.emit(error_type, message)


class ScreenTranslateApp(QObject):
    """ScreenTranslate主应用程序类"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # 应用程序组件
        self.tray_app = None
        self.workflow_thread = None
        self.result_window = None
        self.settings_window = None
        self.history_window = None

        # 管理器引用
        self.config_manager = None
        self.hotkey_manager = None
        self.history_manager = None

        # 初始化
        self.init_application()

    def init_application(self):
        """初始化应用程序"""
        try:
            self.logger.info("初始化ScreenTranslate应用程序")

            # 检查平台兼容性
            self._check_platform_compatibility()

            # 初始化管理器
            self._init_managers()

            # 创建系统托盘应用
            self.tray_app = create_tray_application()
            self._setup_tray_signals()

            # 创建结果窗口
            self.result_window = ResultWindow()
            self.screenshot_overlay: Optional[ScreenshotOverlay] = None

            self.logger.info("应用程序初始化完成")

        except Exception as e:
            self.logger.error(f"应用程序初始化失败: {e}")
            self._show_critical_error("初始化失败", f"应用程序初始化失败: {e}")
            sys.exit(1)

    def _check_platform_compatibility(self):
        """检查平台兼容性"""
        try:
            system = platform.system().lower()
            self.logger.info(f"运行平台: {system}")

            # 检查系统托盘支持
            from PyQt6.QtWidgets import QSystemTrayIcon
            if not QSystemTrayIcon.isSystemTrayAvailable():
                raise RuntimeError("系统不支持系统托盘功能")

            # 检查权限（特别是macOS）
            if system == "darwin":
                self._check_macos_permissions()

        except Exception as e:
            raise RuntimeError(f"平台兼容性检查失败: {e}")

    def _check_macos_permissions(self):
        """检查macOS权限"""
        try:
            # 检查屏幕录制权限
            import subprocess
            result = subprocess.run([
                "osascript", "-e",
                "tell application \"System Events\" to get the name of every application process"
            ], capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.warning("macOS屏幕录制权限可能未授予")
                QMessageBox.warning(None, "权限提醒",
                                  "在macOS上，您可能需要在 系统偏好设置 > 安全性与隐私 > 隐私 中，"
                                  "为本应用授予 屏幕录制 和 辅助功能 权限。")
        except:
            pass  # 忽略权限检查错误

    def _init_managers(self):
        """初始化管理器"""
        try:
            self.config_manager = get_config_manager()
            self.hotkey_manager = get_hotkey_manager()
            self.history_manager = get_history_manager()

            # 连接配置变更信号
            self.config_manager.config_changed.connect(self._on_config_changed)

            self.logger.info("管理器初始化完成")

        except Exception as e:
            self.logger.error(f"管理器初始化失败: {e}")
            raise

    def _setup_tray_signals(self):
        """设置托盘信号连接"""
        try:
            if self.tray_app and self.tray_app.tray_icon:
                tray_icon = self.tray_app.tray_icon
                tray_icon.set_screenshot_handler(self.start_screenshot_workflow)

                try:
                    tray_icon.settings_requested.disconnect(self.show_settings)
                except TypeError:
                    pass
                tray_icon.settings_requested.connect(self.show_settings)

                try:
                    tray_icon.history_requested.disconnect(self.show_history)
                except TypeError:
                    pass
                tray_icon.history_requested.connect(self.show_history)

        except Exception as e:
            self.logger.error(f"设置托盘信号失败: {e}")

    @pyqtSlot(result=bool)
    def start_screenshot_workflow(self) -> bool:
        """启动截图工作流"""
        try:
            self.logger.info("启动截图工作流")
            screen = QApplication.primaryScreen()
            if not screen:
                raise RuntimeError("无法获取主屏幕信息")

            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                raise RuntimeError("屏幕截图失败")

            screen_geometry = screen.geometry()

            # 清理可能存在的旧遮罩
            self._cleanup_overlay()

            overlay = ScreenshotOverlay(pixmap, screen_geometry)
            overlay.area_selected.connect(self._on_overlay_area_selected)
            overlay.selection_cancelled.connect(self._on_screenshot_cancelled)
            overlay.setParent(None)
            overlay.show_overlay()

            self.screenshot_overlay = overlay
            return True

        except Exception as e:
            self.logger.error(f"启动截图工作流失败: {e}")
            self._show_error("截图错误", f"启动截图时发生错误: {e}")
            return False

    def _cleanup_overlay(self):
        if self.screenshot_overlay:
            self.screenshot_overlay.close()
            self.screenshot_overlay.deleteLater()
            self.screenshot_overlay = None

    def _on_overlay_area_selected(self, x: int, y: int, width: int, height: int):
        try:
            overlay = self.screenshot_overlay
            if not overlay or not overlay.background_pixmap or overlay.background_pixmap.isNull():
                raise RuntimeError("截图遮罩未准备好")

            pixmap = overlay.background_pixmap
            pixel_ratio = pixmap.devicePixelRatio() or 1.0
            physical_rect = QRect(
                int(x * pixel_ratio),
                int(y * pixel_ratio),
                int(width * pixel_ratio),
                int(height * pixel_ratio)
            )

            cropped = pixmap.copy(physical_rect)
            if cropped.isNull():
                raise RuntimeError("截取区域图像失败")

            qimage = cropped.toImage().convertToFormat(QImage.Format.Format_RGB888)
            ptr = qimage.bits()
            ptr.setsize(qimage.height() * qimage.bytesPerLine())
            buffer = bytes(ptr)
            image = Image.frombuffer(
                "RGB",
                (qimage.width(), qimage.height()),
                buffer,
                "raw",
                "RGB",
                qimage.bytesPerLine(),
                1,
            )

            geometry = overlay.geometry()
            logical_left = geometry.x() + x
            logical_top = geometry.y() + y

            self._cleanup_overlay()
            self._on_screenshot_taken(image, logical_left, logical_top, width, height)

        except Exception as e:
            self.logger.error(f"处理截图区域失败: {e}")
            self._cleanup_overlay()
            self._on_screenshot_error(str(e))

    @pyqtSlot(object, int, int, int, int)
    def _on_screenshot_taken(self, image, x, y, width, height):
        """截图完成处理"""
        try:
            self.logger.info(f"截图完成，开始处理工作流: 区域({x}, {y}, {width}x{height})")

            if self.tray_app and self.tray_app.tray_icon:
                self.tray_app.tray_icon.on_screenshot_taken(image, x, y, width, height)

            # 启动工作流线程
            self.workflow_thread = WorkflowThread(image, (x, y, width, height))
            self._setup_workflow_signals()
            self.workflow_thread.start()

        except Exception as e:
            self.logger.error(f"处理截图完成失败: {e}")
            self._show_error("处理错误", f"处理截图时发生错误: {e}")

    def _setup_workflow_signals(self):
        """设置工作流信号连接"""
        if self.workflow_thread:
            self.workflow_thread.workflow_started.connect(self._on_workflow_started)
            self.workflow_thread.ocr_completed.connect(self._on_ocr_completed)
            self.workflow_thread.translation_completed.connect(self._on_translation_completed)
            self.workflow_thread.workflow_completed.connect(self._on_workflow_completed)
            self.workflow_thread.error_occurred.connect(self._on_workflow_error)

    @pyqtSlot()
    def _on_workflow_started(self):
        """工作流开始"""
        self.logger.info("工作流已开始")
        if self.tray_app and self.tray_app.tray_icon:
            self.tray_app.tray_icon.showMessage(
                "ScreenTranslate-AI",
                "正在处理截图，请稍候...",
                self.tray_app.tray_icon.MessageIcon.Information,
                3000
            )

    @pyqtSlot(str)
    def _on_ocr_completed(self, text):
        """OCR完成"""
        self.logger.info(f"OCR识别完成，文本长度: {len(text)}")

    @pyqtSlot(object)
    def _on_translation_completed(self, response):
        """翻译完成"""
        self.logger.info(f"翻译完成，使用模型: {response.model}")

    @pyqtSlot(object)
    def _on_workflow_completed(self, result_data):
        """工作流完成"""
        try:
            self.logger.info("工作流完成，显示结果")

            # 显示结果窗口
            if self.result_window:
                # 计算显示位置（截图区域附近）
                x, y, width, height = result_data.metadata['screenshot_region']
                self.result_window.show_result(result_data, screenshot_region=(x, y, width, height))

            # 托盘通知
            if self.tray_app and self.tray_app.tray_icon:
                self.tray_app.tray_icon.showMessage(
                    "翻译完成",
                    f"已识别 {len(result_data.original_text)} 个字符",
                    self.tray_app.tray_icon.MessageIcon.Information,
                    2000
                )

        except Exception as e:
            self.logger.error(f"处理工作流完成失败: {e}")

    @pyqtSlot(str, str)
    def _on_workflow_error(self, error_type, message):
        """工作流错误处理"""
        try:
            self.logger.error(f"工作流错误 [{error_type}]: {message}")

            # 构造错误结果数据
            error_result = ResultData(
                result_type=ResultType.ERROR,
                error_message=f"[{error_type}] {message}"
            )

            # 显示错误结果
            if self.result_window:
                self.result_window.show_result(error_result)

            # 托盘通知
            if self.tray_app and self.tray_app.tray_icon:
                self.tray_app.tray_icon.showMessage(
                    f"{error_type}错误",
                    message,
                    self.tray_app.tray_icon.MessageIcon.Warning,
                    5000
                )

        except Exception as e:
            self.logger.error(f"处理工作流错误失败: {e}")

    @pyqtSlot()
    def _on_screenshot_cancelled(self):
        """截图取消处理"""
        self.logger.info("截图已取消")
        self._cleanup_overlay()
        if self.tray_app and self.tray_app.tray_icon:
            self.tray_app.tray_icon.on_screenshot_cancelled()

    @pyqtSlot(str)
    def _on_screenshot_error(self, error):
        """截图错误处理"""
        self.logger.error(f"截图错误: {error}")
        if self.tray_app and self.tray_app.tray_icon:
            self.tray_app.tray_icon.on_screenshot_error(error)
        self._show_error("截图错误", error)

    @pyqtSlot()
    def show_settings(self):
        """显示设置窗口"""
        try:
            if not self.settings_window:
                self.settings_window = SettingsWindow()
                if self.tray_app and self.tray_app.tray_icon:
                    self.tray_app.tray_icon.set_settings_window(self.settings_window)
                self.settings_window.settings_applied.connect(self._on_settings_applied)
                self.settings_window.settings_reset.connect(self._on_settings_reset)

            if self.settings_window.isMinimized():
                self.settings_window.showNormal()

            self.settings_window.show()
            self.settings_window.raise_()
            self.settings_window.activateWindow()

        except Exception as e:
            self.logger.error(f"显示设置窗口失败: {e}")
            self._show_error("设置窗口", f"无法显示设置窗口: {e}")

    @pyqtSlot()
    def show_history(self):
        """显示历史窗口"""
        try:
            if not self.history_window:
                self.history_window = create_history_window()
                if self.tray_app and self.tray_app.tray_icon:
                    self.tray_app.tray_icon.set_history_window(self.history_window)

            if self.history_window.isMinimized():
                self.history_window.showNormal()

            self.history_window.show()
            self.history_window.raise_()
            self.history_window.activateWindow()

        except Exception as e:
            self.logger.error(f"显示历史窗口失败: {e}")
            self._show_error("历史记录", f"无法显示历史记录窗口: {e}")

    def _on_settings_applied(self):
        """设置保存事件"""
        self.logger.info("设置已应用")

    def _on_settings_reset(self):
        """设置重置事件"""
        self.logger.info("设置已恢复默认值")

    # 其他方法不变...

    @pyqtSlot(str)
    def _on_config_changed(self, section):
        """配置变更处理"""
        try:
            self.logger.info(f"配置已更新: {section}")
            # 配置变更会自动传播到各个管理器

        except Exception as e:
            self.logger.error(f"处理配置变更失败: {e}")

    def cleanup(self):
        """清理应用程序资源"""
        try:
            self.logger.info("开始清理应用程序资源")

            # 停止工作流线程
            if self.workflow_thread and self.workflow_thread.isRunning():
                self.workflow_thread.quit()
                self.workflow_thread.wait(3000)

            # 清理窗口
            if self.result_window:
                self.result_window.close()
            if self.settings_window:
                self.settings_window.close()
            if self.history_window:
                self.history_window.close()

            # 清理托盘应用
            if self.tray_app:
                self.tray_app.cleanup()

            # 清理截图遮罩
            self._cleanup_overlay()

            # 清理全局管理器
            cleanup_ocr_engine()
            cleanup_history_manager()
            cleanup_hotkey_manager()
            cleanup_config_manager()

            self.logger.info("应用程序资源清理完成")

        except Exception as e:
            self.logger.error(f"清理应用程序资源失败: {e}")

    def _show_error(self, title: str, message: str):
        """显示错误消息"""
        QMessageBox.critical(None, title, message)

    def _show_critical_error(self, title: str, message: str):
        """显示致命错误消息"""
        QMessageBox.critical(None, title, message)


def setup_logging():
    """设置日志系统"""
    try:
        # 创建日志目录
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # 配置日志格式
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        # 配置根日志记录器
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(
                    log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log",
                    encoding='utf-8'
                )
            ]
        )

        # 设置第三方库日志级别
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

        logger = logging.getLogger(__name__)
        logger.info("日志系统初始化完成")

    except Exception as e:
        print(f"设置日志系统失败: {e}")


def main():
    """主函数"""
    try:
        # 设置日志
        setup_logging()

        if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        logger = logging.getLogger(__name__)

        # 创建QApplication
        app = QApplication(sys.argv)
        app.setApplicationName("ScreenTranslate-AI")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("ScreenTranslate")
        app.setOrganizationDomain("screentranslate.ai")

        # 设置应用图标
        try:
            icon_path = Path(__file__).parent.parent / "ico.png"
            if icon_path.exists():
                app.setWindowIcon(QIcon(str(icon_path)))
            else:
                # 备用方案：查找resources目录
                backup_icon_path = Path(__file__).parent.parent / "resources" / "icons" / "app_icon.png"
                if backup_icon_path.exists():
                    app.setWindowIcon(QIcon(str(backup_icon_path)))
        except Exception as e:
            logging.getLogger(__name__).warning(f"设置应用图标失败: {e}")

        # 设置退出行为
        app.setQuitOnLastWindowClosed(False)

        logger.info("="*50)
        logger.info("ScreenTranslate-AI 应用程序启动")
        logger.info(f"平台: {platform.system()} {platform.release()}")
        logger.info(f"Python: {sys.version}")
        logger.info("="*50)

        # 创建主应用程序
        main_app = ScreenTranslateApp()

        # 设置退出处理
        app.aboutToQuit.connect(main_app.cleanup)

        # 运行应用程序
        logger.info("应用程序开始运行")
        exit_code = app.exec()

        logger.info(f"应用程序退出，退出码: {exit_code}")
        return exit_code

    except KeyboardInterrupt:
        logger.info("收到键盘中断信号，退出应用程序")
        return 0

    except Exception as e:
        logger.error(f"应用程序运行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 显示错误对话框
        try:
            QMessageBox.critical(None, "启动错误", f"应用程序启动失败:\n{e}")
        except:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
