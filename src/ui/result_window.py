"""
结果悬浮窗模块

实现无边框悬浮窗口，用于显示OCR识别和LLM翻译结果。
支持智能定位、主题切换、复制功能和自动关闭。
"""

import sys
import logging
import platform
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QTextEdit, QFrame, QApplication,
                           QGraphicsDropShadowEffect, QScrollArea, QSizePolicy,
                           QSizeGrip, QSplitter)
from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QPropertyAnimation,
                        QEasingCurve, QRect, QPoint, QSize)
from PyQt6.QtGui import (QFont, QColor, QPalette, QPixmap, QIcon,
                       QFontMetrics, QPainter, QClipboard, QTextOption)

from ..config.config_manager import ConfigManager, get_config_manager


class ResultType(Enum):
    """结果类型枚举"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    EMPTY = "empty"


@dataclass
class ResultData:
    """结果数据类"""
    original_text: str = ""
    translated_text: str = ""
    result_type: ResultType = ResultType.SUCCESS
    error_message: str = ""
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ModernButton(QPushButton):
    """现代化按钮组件"""

    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(text, parent)
        self.icon_text = icon_text
        self.setup_style()

    def setup_style(self):
        """设置按钮样式"""
        self.setFixedHeight(32)
        self.setMinimumWidth(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_theme(self, is_dark: bool = False):
        """更新主题"""
        if is_dark:
            self.setStyleSheet("""
                ModernButton {
                    background-color: #404040;
                    border: 1px solid #606060;
                    border-radius: 6px;
                    color: #ffffff;
                    font-weight: 500;
                    padding: 6px 12px;
                }
                ModernButton:hover {
                    background-color: #505050;
                    border-color: #707070;
                }
                ModernButton:pressed {
                    background-color: #303030;
                }
                ModernButton:checked {
                    background-color: #0078d4;
                    border-color: #106ebe;
                    color: #ffffff;
                }
                ModernButton:checked:hover {
                    background-color: #106ebe;
                    border-color: #005a9e;
                }
            """)
        else:
            self.setStyleSheet("""
                ModernButton {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    color: #495057;
                    font-weight: 500;
                    padding: 6px 12px;
                }
                ModernButton:hover {
                    background-color: #e9ecef;
                    border-color: #adb5bd;
                }
                ModernButton:pressed {
                    background-color: #dee2e6;
                }
                ModernButton:checked {
                    background-color: #0078d4;
                    border-color: #0056b3;
                    color: #ffffff;
                }
                ModernButton:checked:hover {
                    background-color: #0056b3;
                    border-color: #004085;
                }
            """)


class ResultWindow(QWidget):
    """结果悬浮窗口"""

    # 信号
    window_closed = pyqtSignal()
    copy_requested = pyqtSignal(str, str)  # 文本内容, 类型(original/translated)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 配置管理器
        self.config_manager: Optional[ConfigManager] = None

        # 窗口属性
        self.auto_close_timer: Optional[QTimer] = None
        self.fade_animation: Optional[QPropertyAnimation] = None
        self.current_result: Optional[ResultData] = None

        # 平台信息
        self.platform = platform.system().lower()

        # 窗口拖拽相关
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_area_height = 48

        # 主要控件提前创建，避免初始化失败时属性缺失
        self.original_text = QTextEdit()
        self.result_text = QTextEdit()
        self._wrap_mode = getattr(
            QTextOption.WrapMode,
            "WrapAtWordBoundaryOrAnywhere",
            QTextOption.WrapMode.WordWrap
        )
        self.original_frame: Optional[QFrame] = None
        self.result_frame: Optional[QFrame] = None
        self.content_splitter: Optional[QSplitter] = None

        # 初始化
        self.init_config()
        self.setup_window()
        self.setup_ui()
        self.setup_animations()
        self.setup_auto_close()
        self.setup_size_persistence()

        self.logger.info("结果窗口初始化完成")

    def init_config(self):
        """初始化配置"""
        try:
            self.config_manager = get_config_manager()
            if self.config_manager:
                self.config_manager.config_changed.connect(self.on_config_changed)

        except Exception as e:
            self.logger.error(f"初始化配置失败: {e}")

    def setup_window(self):
        """设置窗口属性"""
        try:
            # 无边框窗口
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )

            # 窗口属性
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            # 设置窗口图标
            try:
                from pathlib import Path
                icon_path = Path(__file__).parent.parent.parent / "ico.png"
                if icon_path.exists():
                    self.setWindowIcon(QIcon(str(icon_path)))
            except Exception as e:
                self.logger.warning(f"设置窗口图标失败: {e}")

            # 设置初始大小
            self.setMinimumSize(480, 320)
            self.resize(720, 540)

            # 应用配置
            self.apply_config()

        except Exception as e:
            self.logger.error(f"设置窗口属性失败: {e}")

    def setup_ui(self):
        """设置用户界面"""
        try:
            # 主布局
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # 创建主容器
            self.main_container = QFrame()
            self.main_container.setObjectName("mainContainer")
            main_layout.addWidget(self.main_container)

            # 容器布局
            container_layout = QVBoxLayout(self.main_container)
            container_layout.setContentsMargins(16, 16, 16, 16)
            container_layout.setSpacing(12)

            # 标题栏
            title_layout = self.create_title_bar()
            container_layout.addLayout(title_layout)

            # 内容区域
            content_widget = self.create_content_area()
            container_layout.addWidget(content_widget)

            # 按钮区域
            button_layout = self.create_button_area()
            container_layout.addLayout(button_layout)

            # 添加尺寸调节控件
            size_grip_layout = QHBoxLayout()
            size_grip_layout.setContentsMargins(0, 0, 0, 0)
            size_grip_layout.addStretch()
            self.size_grip = QSizeGrip(self)
            self.size_grip.setFixedSize(16, 16)
            size_grip_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
            container_layout.addLayout(size_grip_layout)

            # 调整布局拉伸系数，让内容区域占据剩余空间
            container_layout.setStretch(0, 0)  # 标题栏
            container_layout.setStretch(1, 1)  # 内容区域
            container_layout.setStretch(2, 0)  # 按钮区域
            container_layout.setStretch(3, 0)  # 尺寸调节

            # 应用主题
            self.apply_theme()

            # 添加阴影效果
            self.add_shadow_effect()

        except Exception as e:
            self.logger.error(f"设置UI失败: {e}")

    def create_title_bar(self) -> QHBoxLayout:
        """创建标题栏"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        self.title_label = QLabel("翻译结果")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)

        # 弹性空间
        layout.addStretch()

        # 关闭按钮
        self.close_btn = ModernButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close_window)
        layout.addWidget(self.close_btn)

        return layout

    def create_content_area(self) -> QWidget:
        """创建内容区域"""
        content_widget = QWidget()
        content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 原文区域
        self.original_frame = QFrame()
        self.original_frame.setObjectName("originalFrame")
        self.original_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        original_layout = QVBoxLayout(self.original_frame)
        original_layout.setContentsMargins(12, 8, 12, 8)

        self.original_label = QLabel("原文:")
        self.original_label.setObjectName("sectionLabel")
        original_layout.addWidget(self.original_label)

        self.original_text.setObjectName("originalText")
        self.original_text.setReadOnly(True)
        self.original_text.setWordWrapMode(self._wrap_mode)
        self.original_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.original_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.original_text.setMinimumWidth(320)
        self.original_text.setMinimumHeight(0)
        original_layout.addWidget(self.original_text)

        self.content_splitter.addWidget(self.original_frame)

        # 翻译结果区域
        self.result_frame = QFrame()
        self.result_frame.setObjectName("resultFrame")
        self.result_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        result_layout = QVBoxLayout(self.result_frame)
        result_layout.setContentsMargins(12, 8, 12, 8)

        self.result_label = QLabel("翻译结果:")
        self.result_label.setObjectName("sectionLabel")
        result_layout.addWidget(self.result_label)

        self.result_text.setObjectName("resultText")
        self.result_text.setReadOnly(True)
        self.result_text.setWordWrapMode(self._wrap_mode)
        self.result_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.result_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.result_text.setMinimumWidth(320)
        self.result_text.setMinimumHeight(0)
        result_layout.addWidget(self.result_text)

        self.content_splitter.addWidget(self.result_frame)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 1)

        layout.addWidget(self.content_splitter)

        return content_widget

    def create_button_area(self) -> QHBoxLayout:
        """创建按钮区域"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)

        # 复制原文按钮
        self.copy_original_btn = ModernButton("复制原文", "📋")
        self.copy_original_btn.clicked.connect(self.copy_original)
        layout.addWidget(self.copy_original_btn)

        # 复制结果按钮
        self.copy_result_btn = ModernButton("复制结果", "📋")
        self.copy_result_btn.clicked.connect(self.copy_result)
        layout.addWidget(self.copy_result_btn)

        # 弹性空间
        layout.addStretch()

        # 置顶按钮
        self.pin_btn = ModernButton("📌")
        self.pin_btn.setFixedWidth(40)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("置顶窗口")
        self.pin_btn.clicked.connect(self.toggle_pin)
        layout.addWidget(self.pin_btn)

        return layout

    def add_shadow_effect(self):
        """添加阴影效果"""
        try:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(20)
            shadow.setColor(QColor(0, 0, 0, 100))
            shadow.setOffset(0, 4)
            self.main_container.setGraphicsEffect(shadow)

        except Exception as e:
            self.logger.error(f"添加阴影效果失败: {e}")

    def setup_animations(self):
        """设置动画"""
        try:
            # 淡入淡出动画
            self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
            self.fade_animation.setDuration(300)
            self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        except Exception as e:
            self.logger.error(f"设置动画失败: {e}")

    def setup_auto_close(self):
        """设置自动关闭"""
        try:
            self.auto_close_timer = QTimer()
            self.auto_close_timer.setSingleShot(True)
            self.auto_close_timer.timeout.connect(self.auto_close)

        except Exception as e:
            self.logger.error(f"设置自动关闭失败: {e}")

    def setup_size_persistence(self):
        """设置窗口尺寸持久化"""
        try:
            self._size_save_timer = QTimer(self)
            self._size_save_timer.setSingleShot(True)
            self._size_save_timer.setInterval(800)
            self._size_save_timer.timeout.connect(self.persist_window_size)

        except Exception as e:
            self.logger.error(f"设置窗口尺寸持久化失败: {e}")
            self._size_save_timer = None

    def apply_config(self):
        """应用配置"""
        try:
            if not self.config_manager:
                return

            settings = self.config_manager.get_settings()

            # 应用透明度
            opacity = settings.ui.opacity
            self.setWindowOpacity(opacity)

            # 应用字体大小
            font_size = settings.ui.font_size
            self.apply_font_size(font_size)

            # 应用置顶设置
            if settings.ui.window_stay_on_top:
                self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            else:
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)

            # 应用窗口尺寸
            width = getattr(settings.ui, "result_window_width", 720)
            height = getattr(settings.ui, "result_window_height", 540)
            target_size = QSize(
                max(self.minimumWidth(), int(width)),
                max(self.minimumHeight(), int(height))
            )
            if self.size() != target_size:
                self.resize(target_size)

        except Exception as e:
            self.logger.error(f"应用配置失败: {e}")

    def apply_font_size(self, font_size: int):
        """应用字体大小"""
        try:
            font = self.font()
            font.setPointSize(font_size)
            self.setFont(font)

            # 应用到文本组件
            if hasattr(self, 'original_text'):
                self.original_text.setFont(font)
            if hasattr(self, 'result_text'):
                self.result_text.setFont(font)

        except Exception as e:
            self.logger.error(f"应用字体大小失败: {e}")

    def apply_theme(self):
        """应用主题"""
        try:
            if not self.config_manager:
                return

            settings = self.config_manager.get_settings()
            is_dark = settings.ui.theme == "dark"

            # 主容器样式
            if is_dark:
                self.main_container.setStyleSheet("""
                    QFrame#mainContainer {
                        background-color: #2b2b2b;
                        border: 1px solid #404040;
                        border-radius: 12px;
                    }
                    QLabel#titleLabel {
                        color: #ffffff;
                        font-weight: bold;
                        font-size: 14px;
                        margin-bottom: 4px;
                    }
                    QLabel#sectionLabel {
                        color: #cccccc;
                        font-weight: 500;
                        font-size: 12px;
                        margin-bottom: 4px;
                    }
                    QFrame#originalFrame, QFrame#resultFrame {
                        background-color: #363636;
                        border: 1px solid #505050;
                        border-radius: 8px;
                    }
                    QTextEdit#originalText, QTextEdit#resultText {
                        background-color: #404040;
                        border: 1px solid #606060;
                        border-radius: 6px;
                        color: #ffffff;
                        selection-background-color: #0078d4;
                        padding: 8px;
                    }
                    QScrollBar:vertical {
                        background-color: #505050;
                        width: 12px;
                        border-radius: 6px;
                    }
                    QScrollBar::handle:vertical {
                        background-color: #707070;
                        border-radius: 6px;
                        min-height: 20px;
                    }
                    QScrollBar::handle:vertical:hover {
                        background-color: #808080;
                    }
                """)
            else:
                self.main_container.setStyleSheet("""
                    QFrame#mainContainer {
                        background-color: #ffffff;
                        border: 1px solid #e1e5e9;
                        border-radius: 12px;
                    }
                    QLabel#titleLabel {
                        color: #212529;
                        font-weight: bold;
                        font-size: 14px;
                        margin-bottom: 4px;
                    }
                    QLabel#sectionLabel {
                        color: #6c757d;
                        font-weight: 500;
                        font-size: 12px;
                        margin-bottom: 4px;
                    }
                    QFrame#originalFrame, QFrame#resultFrame {
                        background-color: #f8f9fa;
                        border: 1px solid #dee2e6;
                        border-radius: 8px;
                    }
                    QTextEdit#originalText, QTextEdit#resultText {
                        background-color: #ffffff;
                        border: 1px solid #ced4da;
                        border-radius: 6px;
                        color: #495057;
                        selection-background-color: #0078d4;
                        padding: 8px;
                    }
                    QScrollBar:vertical {
                        background-color: #f8f9fa;
                        width: 12px;
                        border-radius: 6px;
                    }
                    QScrollBar::handle:vertical {
                        background-color: #ced4da;
                        border-radius: 6px;
                        min-height: 20px;
                    }
                    QScrollBar::handle:vertical:hover {
                        background-color: #adb5bd;
                    }
                """)

            # 更新按钮主题
            for btn in [self.copy_original_btn, self.copy_result_btn, self.pin_btn]:
                if hasattr(btn, 'update_theme'):
                    btn.update_theme(is_dark)

        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def show_result(self, result_data: ResultData, screenshot_region: Tuple[int, int, int, int] = None):
        """显示结果"""
        try:
            self.current_result = result_data

            if result_data.result_type == ResultType.SUCCESS:
                self.show_success_result(result_data)
            elif result_data.result_type == ResultType.ERROR:
                self.show_error_result(result_data)
            elif result_data.result_type == ResultType.WARNING:
                self.show_warning_result(result_data)
            elif result_data.result_type == ResultType.EMPTY:
                self.show_empty_result()

            # 定位窗口
            if screenshot_region:
                self.position_near_region(screenshot_region)
            else:
                self.position_center()

            # 显示窗口并播放淡入动画
            self.show_with_animation()

            # 启动自动关闭定时器
            self.start_auto_close_timer()

            self.logger.info(f"显示结果: 类型={result_data.result_type}")

        except Exception as e:
            self.logger.error(f"显示结果失败: {e}")

    def show_success_result(self, result_data: ResultData):
        """显示成功结果"""
        self.title_label.setText("翻译结果")
        self.original_text.setPlainText(result_data.original_text)
        self.result_text.setPlainText(result_data.translated_text)

        # 显示相关组件
        self.original_frame.setVisible(bool(result_data.original_text))
        self.result_frame.setVisible(bool(result_data.translated_text))
        self.copy_original_btn.setEnabled(bool(result_data.original_text))
        self.copy_result_btn.setEnabled(bool(result_data.translated_text))

    def show_error_result(self, result_data: ResultData):
        """显示错误结果"""
        self.title_label.setText("处理错误")
        self.original_text.setPlainText(result_data.original_text or "")
        self.result_text.setPlainText(f"错误: {result_data.error_message}")

        self.original_frame.setVisible(bool(result_data.original_text))
        self.result_frame.setVisible(True)
        self.copy_original_btn.setEnabled(bool(result_data.original_text))
        self.copy_result_btn.setEnabled(False)

    def show_warning_result(self, result_data: ResultData):
        """显示警告结果"""
        self.title_label.setText("处理警告")
        self.original_text.setPlainText(result_data.original_text or "")
        self.result_text.setPlainText(result_data.translated_text or result_data.error_message)

        self.original_frame.setVisible(bool(result_data.original_text))
        self.result_frame.setVisible(True)
        self.copy_original_btn.setEnabled(bool(result_data.original_text))
        self.copy_result_btn.setEnabled(bool(result_data.translated_text))

    def show_empty_result(self):
        """显示空结果"""
        self.title_label.setText("未检测到文本")
        self.original_text.setPlainText("")
        self.result_text.setPlainText("未能从图像中识别到文本内容")

        self.original_frame.setVisible(False)
        self.result_frame.setVisible(True)
        self.copy_original_btn.setEnabled(False)
        self.copy_result_btn.setEnabled(False)

    def position_near_region(self, region: Tuple[int, int, int, int]):
        """在截图区域附近定位窗口"""
        try:
            x, y, width, height = region
            window_width = self.width()
            window_height = self.height()

            # 获取屏幕尺寸
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()

            # 计算最佳位置
            # 优先尝试右侧
            target_x = x + width + 20
            target_y = y

            # 如果右侧超出屏幕，尝试左侧
            if target_x + window_width > screen_width:
                target_x = x - window_width - 20

            # 如果左侧也超出屏幕，尝试下方
            if target_x < 0:
                target_x = x
                target_y = y + height + 20

            # 如果下方超出屏幕，尝试上方
            if target_y + window_height > screen_height:
                target_y = y - window_height - 20

            # 确保不超出屏幕边界
            target_x = max(10, min(target_x, screen_width - window_width - 10))
            target_y = max(10, min(target_y, screen_height - window_height - 10))

            self.move(target_x, target_y)

            self.logger.debug(f"窗口定位: ({target_x}, {target_y})")

        except Exception as e:
            self.logger.error(f"定位窗口失败: {e}")
            self.position_center()

    def position_center(self):
        """居中定位窗口"""
        try:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()

            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2

            self.move(x, y)

        except Exception as e:
            self.logger.error(f"居中定位失败: {e}")

    def show_with_animation(self):
        """显示窗口并播放动画"""
        try:
            # 设置初始透明度
            self.setWindowOpacity(0.0)
            self.show()

            # 播放淡入动画
            if self.fade_animation:
                target_opacity = 1.0
                if self.config_manager:
                    settings = self.config_manager.get_settings()
                    target_opacity = settings.ui.opacity

                self.fade_animation.setStartValue(0.0)
                self.fade_animation.setEndValue(target_opacity)
                self.fade_animation.start()

        except Exception as e:
            self.logger.error(f"显示动画失败: {e}")
            self.show()

    def start_auto_close_timer(self):
        """启动自动关闭定时器"""
        try:
            if self.auto_close_timer and not self.pin_btn.isChecked():
                # 根据内容长度调整关闭时间
                base_time = 8000  # 8秒基础时间
                if self.current_result:
                    text_length = len(self.current_result.original_text) + len(self.current_result.translated_text)
                    extra_time = min(text_length * 50, 12000)  # 最多额外12秒
                    timeout = base_time + extra_time
                else:
                    timeout = base_time

                self.auto_close_timer.start(timeout)
                self.logger.debug(f"自动关闭定时器启动: {timeout}ms")

        except Exception as e:
            self.logger.error(f"启动自动关闭定时器失败: {e}")

    def copy_original(self):
        """复制原文"""
        try:
            if self.current_result and self.current_result.original_text:
                clipboard = QApplication.clipboard()
                clipboard.setText(self.current_result.original_text)
                self.copy_requested.emit(self.current_result.original_text, "original")
                self.show_copy_feedback("原文已复制")

        except Exception as e:
            self.logger.error(f"复制原文失败: {e}")

    def copy_result(self):
        """复制翻译结果"""
        try:
            if self.current_result and self.current_result.translated_text:
                clipboard = QApplication.clipboard()
                clipboard.setText(self.current_result.translated_text)
                self.copy_requested.emit(self.current_result.translated_text, "translated")
                self.show_copy_feedback("翻译结果已复制")

        except Exception as e:
            self.logger.error(f"复制翻译结果失败: {e}")

    def show_copy_feedback(self, message: str):
        """显示复制反馈"""
        try:
            # 临时更改标题显示反馈
            original_title = self.title_label.text()
            self.title_label.setText(message)

            # 2秒后恢复原标题
            QTimer.singleShot(2000, lambda: self.title_label.setText(original_title))

        except Exception as e:
            self.logger.error(f"显示复制反馈失败: {e}")

    def toggle_pin(self, checked: bool):
        """切换置顶状态"""
        try:
            # 更新按钮的检查状态
            self.pin_btn.setChecked(checked)

            if checked:
                # 停止自动关闭
                if self.auto_close_timer:
                    self.auto_close_timer.stop()
                self.pin_btn.setToolTip("取消置顶")
                self.logger.debug("窗口已置顶")
            else:
                # 重新启动自动关闭
                self.start_auto_close_timer()
                self.pin_btn.setToolTip("置顶窗口")
                self.logger.debug("窗口已取消置顶")

            self.logger.debug(f"切换置顶状态: {checked}")

        except Exception as e:
            self.logger.error(f"切换置顶状态失败: {e}")

    def auto_close(self):
        """自动关闭"""
        try:
            if not self.pin_btn.isChecked():
                self.close_window()

        except Exception as e:
            self.logger.error(f"自动关闭失败: {e}")

    def close_window(self):
        """关闭窗口"""
        try:
            if hasattr(self, '_size_save_timer') and self._size_save_timer:
                self._size_save_timer.stop()
            self.persist_window_size()

            if self.auto_close_timer:
                self.auto_close_timer.stop()

            if self.fade_animation:
                try:
                    self.fade_animation.finished.disconnect(self.close)
                except TypeError:
                    pass
                self.fade_animation.setStartValue(self.windowOpacity())
                self.fade_animation.setEndValue(0.0)
                self.fade_animation.finished.connect(self.close)
                self.fade_animation.start()
            else:
                self.close()

        except Exception as e:
            self.logger.error(f"关闭窗口失败: {e}")
            self.close()

    def closeEvent(self, event):
        """处理关闭事件，防止控件被销毁后仍被访问"""
        try:
            if hasattr(self, '_size_save_timer') and self._size_save_timer:
                self._size_save_timer.stop()
            self.persist_window_size()

            if self.auto_close_timer:
                self.auto_close_timer.stop()
            if self.fade_animation:
                try:
                    self.fade_animation.finished.disconnect(self.close)
                except TypeError:
                    pass
            self.setWindowOpacity(1.0)
            self.window_closed.emit()
            self.logger.info("结果窗口已关闭")
        except Exception as e:
            self.logger.error(f"处理关闭事件失败: {e}")
        finally:
            super().closeEvent(event)

    def mousePressEvent(self, event):
        """处理鼠标按下事件以支持拖拽"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                if pos.y() <= self._drag_area_height:  # 仅允许在顶部区域拖拽
                    self._dragging = True
                    global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                    self._drag_offset = global_pos - self.frameGeometry().topLeft()
                    event.accept()
                    return
        except Exception as e:
            self.logger.error(f"处理鼠标按下事件失败: {e}")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        try:
            if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self.move(global_pos - self._drag_offset)
                event.accept()
                return
        except Exception as e:
            self.logger.error(f"处理鼠标移动事件失败: {e}")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._dragging:
                self._dragging = False
                event.accept()
                return
        except Exception as e:
            self.logger.error(f"处理鼠标释放事件失败: {e}")
        super().mouseReleaseEvent(event)

    def on_config_changed(self, section: str):
        """配置变更处理"""
        try:
            if section == "ui":
                self.apply_config()
                self.apply_theme()

        except Exception as e:
            self.logger.error(f"处理配置变更失败: {e}")

    def keyPressEvent(self, event):
        """按键事件处理"""
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.close_window()
            elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Ctrl+C 复制当前选中的文本
                pass
            else:
                super().keyPressEvent(event)

        except Exception as e:
            self.logger.error(f"按键事件处理失败: {e}")

    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                new_pin_state = not self.pin_btn.isChecked()
                self.toggle_pin(new_pin_state)

        except Exception as e:
            self.logger.error(f"鼠标双击事件处理失败: {e}")

    def enterEvent(self, event):
        """鼠标进入事件"""
        try:
            # 鼠标进入时停止自动关闭定时器
            if self.auto_close_timer:
                self.auto_close_timer.stop()

        except Exception as e:
            self.logger.error(f"鼠标进入事件处理失败: {e}")

    def leaveEvent(self, event):
        """鼠标离开事件"""
        try:
            # 鼠标离开时重新启动自动关闭定时器
            if not self.pin_btn.isChecked():
                self.start_auto_close_timer()

        except Exception as e:
            self.logger.error(f"鼠标离开事件处理失败: {e}")

    def resizeEvent(self, event):
        """处理窗口尺寸变更"""
        try:
            if hasattr(self, '_size_save_timer') and self._size_save_timer:
                if event and (not event.oldSize().isValid() or event.size() != event.oldSize()):
                    self._size_save_timer.start()
        except Exception as e:
            self.logger.error(f"处理尺寸变更失败: {e}")

        super().resizeEvent(event)

    def persist_window_size(self):
        """保存窗口尺寸到配置"""
        try:
            if not self.config_manager:
                return

            width = max(self.minimumWidth(), int(self.width()))
            height = max(self.minimumHeight(), int(self.height()))

            settings = self.config_manager.get_settings()
            current_width = getattr(settings.ui, 'result_window_width', width)
            current_height = getattr(settings.ui, 'result_window_height', height)

            if current_width == width and current_height == height:
                return

            self.config_manager.update_ui_settings(
                result_window_width=width,
                result_window_height=height
            )
            self.config_manager.save()

            self.logger.debug(f"窗口尺寸已保存: {width}x{height}")

        except Exception as e:
            self.logger.error(f"保存窗口尺寸失败: {e}")


def create_result_window(parent=None) -> ResultWindow:
    """创建结果窗口实例"""
    return ResultWindow(parent)
