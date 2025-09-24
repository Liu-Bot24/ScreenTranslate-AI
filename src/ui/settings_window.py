"""
设置窗口界面模块

实现分标签页的设置管理界面，支持通用设置、LLM配置和Prompt管理。
集成配置管理器，提供实时验证和保存功能。
"""

import sys
import os
import platform
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                           QWidget, QLabel, QPushButton, QLineEdit, QComboBox,
                           QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit,
                           QGroupBox, QFormLayout, QGridLayout, QScrollArea,
                           QListWidget, QListWidgetItem, QSplitter,
                           QMessageBox, QFileDialog, QProgressBar,
                           QButtonGroup, QRadioButton, QSlider, QFrame,
                           QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot, QProcess
from PyQt6.QtGui import QFont, QIcon, QPixmap, QKeySequence

from ..config.config_manager import ConfigManager, get_config_manager
from ..config.settings import (AppSettings, SUPPORTED_LANGUAGES, SUPPORTED_THEMES,
                              APIProvider, ModifierKey)
from ..utils.path_utils import get_project_root, get_runtime_working_dir, is_frozen
from ..utils.prompt_templates import PromptTemplateManager, get_available_templates


class HotkeyEdit(QWidget):
    """热键编辑控件"""

    hotkey_changed = pyqtSignal(list, str)  # modifiers, key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modifiers = []
        self.key = ""
        self.platform = platform.system().lower()
        self.setup_ui()

    def setup_ui(self):
        """设置界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 修饰键复选框
        self.ctrl_cb = QCheckBox("Ctrl")
        self.shift_cb = QCheckBox("Shift")
        self.alt_cb = QCheckBox("Alt")

        layout.addWidget(self.ctrl_cb)
        layout.addWidget(self.shift_cb)
        layout.addWidget(self.alt_cb)

        # macOS专用
        if self.platform == "darwin":
            self.cmd_cb = QCheckBox("Cmd")
            layout.addWidget(self.cmd_cb)
            self.cmd_cb.toggled.connect(self.on_hotkey_changed)

        # Windows专用
        if self.platform == "windows":
            self.win_cb = QCheckBox("Win")
            layout.addWidget(self.win_cb)
            self.win_cb.toggled.connect(self.on_hotkey_changed)

        # 主键输入
        layout.addWidget(QLabel("+"))
        self.key_edit = QLineEdit()
        self.key_edit.setMaxLength(1)
        self.key_edit.setPlaceholderText("键")
        self.key_edit.setMaximumWidth(40)
        layout.addWidget(self.key_edit)

        # 连接信号
        self.ctrl_cb.toggled.connect(self.on_hotkey_changed)
        self.shift_cb.toggled.connect(self.on_hotkey_changed)
        self.alt_cb.toggled.connect(self.on_hotkey_changed)
        self.key_edit.textChanged.connect(self.on_hotkey_changed)

    def set_hotkey(self, modifiers: List[str], key: str):
        """设置热键"""
        self.modifiers = modifiers
        self.key = key

        # 清除所有选择
        self.ctrl_cb.setChecked(False)
        self.shift_cb.setChecked(False)
        self.alt_cb.setChecked(False)

        if hasattr(self, 'cmd_cb'):
            self.cmd_cb.setChecked(False)
        if hasattr(self, 'win_cb'):
            self.win_cb.setChecked(False)

        # 设置修饰键
        for modifier in modifiers:
            if modifier == "ctrl":
                self.ctrl_cb.setChecked(True)
            elif modifier == "shift":
                self.shift_cb.setChecked(True)
            elif modifier == "alt":
                self.alt_cb.setChecked(True)
            elif modifier == "cmd" and hasattr(self, 'cmd_cb'):
                self.cmd_cb.setChecked(True)
            elif modifier == "win" and hasattr(self, 'win_cb'):
                self.win_cb.setChecked(True)

        # 设置主键
        self.key_edit.setText(key)

    def get_hotkey(self) -> tuple:
        """获取热键"""
        modifiers = []

        if self.ctrl_cb.isChecked():
            modifiers.append("ctrl")
        if self.shift_cb.isChecked():
            modifiers.append("shift")
        if self.alt_cb.isChecked():
            modifiers.append("alt")
        if hasattr(self, 'cmd_cb') and self.cmd_cb.isChecked():
            modifiers.append("cmd")
        if hasattr(self, 'win_cb') and self.win_cb.isChecked():
            modifiers.append("win")

        return modifiers, self.key_edit.text()

    def on_hotkey_changed(self):
        """热键变更处理"""
        modifiers, key = self.get_hotkey()
        self.hotkey_changed.emit(modifiers, key)


class APITestThread(QThread):
    """API测试线程"""

    test_completed = pyqtSignal(bool, str)  # success, message

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

    def run(self):
        """运行测试"""
        try:
            # 这里可以添加实际的API测试逻辑
            # 目前只是模拟测试
            self.msleep(2000)  # 模拟网络延迟

            if self.config.api_key and self.config.model_name:
                self.test_completed.emit(True, "API配置测试成功")
            else:
                self.test_completed.emit(False, "API密钥或模型名称为空")

        except Exception as e:
            self.test_completed.emit(False, f"API测试失败: {str(e)}")


class SettingsWindow(QDialog):
    """设置窗口"""

    settings_applied = pyqtSignal()
    settings_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 配置管理器
        self.config_manager: Optional[ConfigManager] = None

        # Prompt模板管理器
        self.prompt_manager = PromptTemplateManager()

        # API测试线程
        self.api_test_thread: Optional[APITestThread] = None

        # 修改标志
        self.has_unsaved_changes = False

        # 初始化
        self.init_config()
        self.setup_window()
        self.setup_ui()
        self.load_settings()

        self.logger.info("设置窗口初始化完成")

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
        self.setWindowTitle("ScreenTranslate-AI - 设置")
        self.setModal(True)
        self.resize(800, 600)

        # 设置窗口图标
        try:
            icon_path = Path(__file__).parent.parent.parent / "ico.png"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception as e:
            self.logger.warning(f"设置窗口图标失败: {e}")

        # 居中显示
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)

    def setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)

        # 创建标签页
        self.tab_widget = QTabWidget()

        # 通用设置标签页
        general_tab = self.create_general_tab()
        self.tab_widget.addTab(general_tab, "通用设置")

        # LLM设置标签页
        llm_tab = self.create_llm_tab()
        self.tab_widget.addTab(llm_tab, "LLM设置")

        # Prompt管理标签页
        prompt_tab = self.create_prompt_tab()
        self.tab_widget.addTab(prompt_tab, "Prompt管理")

        # OCR设置标签页
        ocr_tab = self.create_ocr_tab()
        self.tab_widget.addTab(ocr_tab, "OCR设置")

        layout.addWidget(self.tab_widget)

        # 按钮区域
        button_layout = self.create_button_area()
        layout.addLayout(button_layout)

    def create_general_tab(self):
        """创建通用设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # 界面设置组
        ui_group = QGroupBox("界面设置")
        ui_layout = QFormLayout(ui_group)

        # 目标语言
        self.target_language_combo = QComboBox()
        self.target_language_combo.addItems(SUPPORTED_LANGUAGES)
        self.target_language_combo.currentTextChanged.connect(self.mark_changed)
        ui_layout.addRow("目标语言:", self.target_language_combo)

        # 主题
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(SUPPORTED_THEMES)
        self.theme_combo.currentTextChanged.connect(self.mark_changed)
        ui_layout.addRow("界面主题:", self.theme_combo)

        # 透明度
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(90)
        self.opacity_slider.valueChanged.connect(self.mark_changed)
        self.opacity_label = QLabel("90%")
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        opacity_widget = QWidget()
        opacity_widget.setLayout(opacity_layout)
        ui_layout.addRow("窗口不透明度:", opacity_widget)

        # 字体大小
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.valueChanged.connect(self.mark_changed)
        ui_layout.addRow("字体大小:", self.font_size_spin)

        content_layout.addWidget(ui_group)

        # 热键设置组
        hotkey_group = QGroupBox("热键设置")
        hotkey_layout = QFormLayout(hotkey_group)

        # 启用热键
        self.hotkey_enabled_cb = QCheckBox("启用全局热键")
        self.hotkey_enabled_cb.toggled.connect(self.mark_changed)
        hotkey_layout.addRow("", self.hotkey_enabled_cb)

        # 热键组合
        self.hotkey_edit = HotkeyEdit()
        self.hotkey_edit.hotkey_changed.connect(self.mark_changed)
        hotkey_layout.addRow("截图热键:", self.hotkey_edit)

        content_layout.addWidget(hotkey_group)

        # 行为设置组
        behavior_group = QGroupBox("行为设置")
        behavior_layout = QFormLayout(behavior_group)

        # 自动复制
        self.auto_copy_cb = QCheckBox("自动复制翻译结果")
        self.auto_copy_cb.toggled.connect(self.mark_changed)
        behavior_layout.addRow("", self.auto_copy_cb)

        # 显示原文
        self.show_original_cb = QCheckBox("显示原文内容")
        self.show_original_cb.toggled.connect(self.mark_changed)
        behavior_layout.addRow("", self.show_original_cb)

        # 窗口置顶
        self.stay_on_top_cb = QCheckBox("结果窗口置顶")
        self.stay_on_top_cb.toggled.connect(self.mark_changed)
        behavior_layout.addRow("", self.stay_on_top_cb)

        # 最小化到托盘
        self.minimize_to_tray_cb = QCheckBox("最小化到系统托盘")
        self.minimize_to_tray_cb.toggled.connect(self.mark_changed)
        behavior_layout.addRow("", self.minimize_to_tray_cb)

        # 开机自启动
        self.auto_start_cb = QCheckBox("开机自动启动")
        self.auto_start_cb.toggled.connect(self.mark_changed)
        behavior_layout.addRow("", self.auto_start_cb)

        content_layout.addWidget(behavior_group)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # 连接透明度滑块信号
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )

        return tab

    def create_llm_tab(self):
        """创建LLM设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # API配置组
        api_group = QGroupBox("API配置")
        api_layout = QFormLayout(api_group)

        # 提供商选择
        self.provider_combo = QComboBox()
        for provider in APIProvider:
            self.provider_combo.addItem(provider.value)
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        self.provider_combo.currentTextChanged.connect(self.mark_changed)
        api_layout.addRow("API提供商:", self.provider_combo)

        # API密钥
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("请输入API密钥")
        self.api_key_edit.textChanged.connect(self.mark_changed)
        api_layout.addRow("API密钥:", self.api_key_edit)

        # 显示/隐藏密钥按钮
        self.show_key_btn = QPushButton("显示")
        self.show_key_btn.setMaximumWidth(60)
        self.show_key_btn.clicked.connect(self.toggle_password_visibility)
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.api_key_edit)
        key_layout.addWidget(self.show_key_btn)
        key_widget = QWidget()
        key_widget.setLayout(key_layout)
        api_layout.addRow("API密钥:", key_widget)

        # API端点
        self.api_endpoint_edit = QLineEdit()
        self.api_endpoint_edit.setPlaceholderText("API端点URL")
        self.api_endpoint_edit.textChanged.connect(self.mark_changed)
        api_layout.addRow("API端点:", self.api_endpoint_edit)

        # 模型名称
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText("模型名称")
        self.model_name_edit.textChanged.connect(self.mark_changed)
        api_layout.addRow("模型名称:", self.model_name_edit)

        # API测试
        self.test_api_btn = QPushButton("测试API连接")
        self.test_api_btn.clicked.connect(self.test_api_connection)
        self.api_test_progress = QProgressBar()
        self.api_test_progress.setVisible(False)
        self.api_test_result = QLabel("")

        test_layout = QVBoxLayout()
        test_layout.addWidget(self.test_api_btn)
        test_layout.addWidget(self.api_test_progress)
        test_layout.addWidget(self.api_test_result)
        test_widget = QWidget()
        test_widget.setLayout(test_layout)
        api_layout.addRow("连接测试:", test_widget)

        content_layout.addWidget(api_group)

        # 请求设置组
        request_group = QGroupBox("请求设置")
        request_layout = QFormLayout(request_group)

        # 温度
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(1)
        self.temperature_spin.valueChanged.connect(self.mark_changed)
        request_layout.addRow("温度值:", self.temperature_spin)

        # 最大令牌数
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 32768)
        self.max_tokens_spin.valueChanged.connect(self.mark_changed)
        request_layout.addRow("最大令牌数:", self.max_tokens_spin)

        # 超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.valueChanged.connect(self.mark_changed)
        request_layout.addRow("请求超时:", self.timeout_spin)

        # 流式响应
        self.stream_cb = QCheckBox("启用流式响应")
        self.stream_cb.toggled.connect(self.mark_changed)
        request_layout.addRow("", self.stream_cb)

        content_layout.addWidget(request_group)

        # 环境变量提示
        env_group = QGroupBox("环境变量")
        env_layout = QVBoxLayout(env_group)

        env_info = QLabel("""
支持的环境变量：
• SILICONFLOW_API_KEY - 硅基流动API密钥
• DOUBAO_API_KEY - 豆包API密钥
• OPENAI_API_KEY - OpenAI API密钥
• SILICONFLOW_MODEL, DOUBAO_MODEL, OPENAI_MODEL - 对应模型名称

注意：环境变量会覆盖这里的设置
        """)
        env_info.setWordWrap(True)
        env_info.setStyleSheet("color: #666; font-size: 11px;")
        env_layout.addWidget(env_info)

        content_layout.addWidget(env_group)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return tab

    def create_prompt_tab(self):
        """创建Prompt管理标签页"""
        tab = QWidget()
        layout = QHBoxLayout(tab)

        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：模板列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # 活动模板选择
        active_group = QGroupBox("活动模板")
        active_layout = QVBoxLayout(active_group)

        self.active_template_combo = QComboBox()
        self.active_template_combo.currentTextChanged.connect(self.mark_changed)
        active_layout.addWidget(self.active_template_combo)

        left_layout.addWidget(active_group)

        # 内置模板列表
        builtin_group = QGroupBox("内置模板")
        builtin_layout = QVBoxLayout(builtin_group)

        self.builtin_templates_list = QListWidget()
        self.builtin_templates_list.itemClicked.connect(self.on_template_selected)
        builtin_layout.addWidget(self.builtin_templates_list)

        left_layout.addWidget(builtin_group)

        # 自定义模板列表
        custom_group = QGroupBox("自定义模板")
        custom_layout = QVBoxLayout(custom_group)

        self.custom_templates_list = QListWidget()
        self.custom_templates_list.itemClicked.connect(self.on_template_selected)
        custom_layout.addWidget(self.custom_templates_list)

        # 自定义模板按钮
        custom_btn_layout = QHBoxLayout()

        self.add_template_btn = QPushButton("添加")
        self.add_template_btn.clicked.connect(self.add_custom_template)
        custom_btn_layout.addWidget(self.add_template_btn)

        self.delete_template_btn = QPushButton("删除")
        self.delete_template_btn.clicked.connect(self.delete_custom_template)
        custom_btn_layout.addWidget(self.delete_template_btn)

        custom_layout.addLayout(custom_btn_layout)
        left_layout.addWidget(custom_group)

        splitter.addWidget(left_panel)

        # 右侧：模板编辑
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 模板信息
        info_group = QGroupBox("模板信息")
        info_layout = QFormLayout(info_group)

        self.template_name_edit = QLineEdit()
        self.template_name_edit.textChanged.connect(self.mark_changed)
        info_layout.addRow("名称:", self.template_name_edit)

        self.template_desc_edit = QLineEdit()
        self.template_desc_edit.textChanged.connect(self.mark_changed)
        info_layout.addRow("描述:", self.template_desc_edit)

        right_layout.addWidget(info_group)

        # 模板内容
        content_group = QGroupBox("模板内容")
        content_layout = QVBoxLayout(content_group)

        self.template_content_edit = QTextEdit()
        self.template_content_edit.setPlaceholderText(
            "输入Prompt模板内容...\n\n"
            "可用变量:\n"
            "• {text} - 输入文本\n"
            "• {target_language} - 目标语言"
        )
        self.template_content_edit.textChanged.connect(self.mark_changed)
        content_layout.addWidget(self.template_content_edit)

        right_layout.addWidget(content_group)

        # 预览区域
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_btn = QPushButton("预览模板")
        self.preview_btn.clicked.connect(self.preview_template)
        preview_layout.addWidget(self.preview_btn)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(100)
        preview_layout.addWidget(self.preview_text)

        right_layout.addWidget(preview_group)

        splitter.addWidget(right_panel)

        # 设置分割器比例
        splitter.setSizes([300, 500])

        layout.addWidget(splitter)

        return tab

    def create_ocr_tab(self):
        """创建OCR设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # OCR基础设置组
        basic_group = QGroupBox("基础设置")
        basic_layout = QFormLayout(basic_group)

        # 启用OCR
        self.ocr_enabled_cb = QCheckBox("启用OCR文字识别")
        self.ocr_enabled_cb.toggled.connect(self.mark_changed)
        basic_layout.addRow("", self.ocr_enabled_cb)

        # CPU模式说明
        cpu_label = QLabel("OCR使用CPU模式运行，确保兼容性")
        cpu_label.setStyleSheet("color: #666; font-size: 11px;")
        basic_layout.addRow("", cpu_label)

        content_layout.addWidget(basic_group)

        # 识别语言设置组
        lang_group = QGroupBox("识别语言")
        lang_layout = QVBoxLayout(lang_group)

        # 语言选择说明
        lang_info = QLabel("选择OCR识别的语言（可多选）:")
        lang_layout.addWidget(lang_info)

        # 语言复选框
        self.ocr_languages = {}
        lang_options = [
            ("ch_sim", "简体中文"),
            ("ch_tra", "繁体中文"),
            ("en", "英语"),
            ("ja", "日语"),
            ("ko", "韩语"),
            ("fr", "法语"),
            ("de", "德语"),
            ("es", "西班牙语"),
            ("ru", "俄语"),
            ("ar", "阿拉伯语")
        ]

        lang_grid = QGridLayout()
        for i, (code, name) in enumerate(lang_options):
            cb = QCheckBox(name)
            cb.toggled.connect(self.mark_changed)
            self.ocr_languages[code] = cb
            lang_grid.addWidget(cb, i // 2, i % 2)

        lang_widget = QWidget()
        lang_widget.setLayout(lang_grid)
        lang_layout.addWidget(lang_widget)

        content_layout.addWidget(lang_group)

        # 高级设置组
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout(advanced_group)

        # 置信度阈值
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.1)
        self.confidence_spin.setDecimals(1)
        self.confidence_spin.valueChanged.connect(self.mark_changed)
        advanced_layout.addRow("置信度阈值:", self.confidence_spin)

        # 文本阈值
        self.text_threshold_spin = QDoubleSpinBox()
        self.text_threshold_spin.setRange(0.0, 1.0)
        self.text_threshold_spin.setSingleStep(0.1)
        self.text_threshold_spin.setDecimals(1)
        self.text_threshold_spin.valueChanged.connect(self.mark_changed)
        advanced_layout.addRow("文本阈值:", self.text_threshold_spin)

        # 链接阈值
        self.link_threshold_spin = QDoubleSpinBox()
        self.link_threshold_spin.setRange(0.0, 1.0)
        self.link_threshold_spin.setSingleStep(0.1)
        self.link_threshold_spin.setDecimals(1)
        self.link_threshold_spin.valueChanged.connect(self.mark_changed)
        advanced_layout.addRow("链接阈值:", self.link_threshold_spin)

        # 画布大小
        self.canvas_size_spin = QSpinBox()
        self.canvas_size_spin.setRange(256, 4096)
        self.canvas_size_spin.setSingleStep(256)
        self.canvas_size_spin.valueChanged.connect(self.mark_changed)
        advanced_layout.addRow("画布大小:", self.canvas_size_spin)

        # 放大比例
        self.mag_ratio_spin = QDoubleSpinBox()
        self.mag_ratio_spin.setRange(0.1, 3.0)
        self.mag_ratio_spin.setSingleStep(0.1)
        self.mag_ratio_spin.setDecimals(1)
        self.mag_ratio_spin.valueChanged.connect(self.mark_changed)
        advanced_layout.addRow("放大比例:", self.mag_ratio_spin)

        content_layout.addWidget(advanced_group)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return tab

    def create_button_area(self):
        """创建按钮区域"""
        layout = QHBoxLayout()

        # 导入/导出按钮
        self.import_btn = QPushButton("导入配置")
        self.import_btn.clicked.connect(self.import_settings)
        layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("导出配置")
        self.export_btn.clicked.connect(self.export_settings)
        layout.addWidget(self.export_btn)

        layout.addStretch()

        # 主要操作按钮
        self.reset_btn = QPushButton("重置默认")
        self.reset_btn.clicked.connect(self.reset_settings)
        layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_changes)
        layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(self.apply_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_settings)
        self.ok_btn.setDefault(True)
        layout.addWidget(self.ok_btn)

        return layout

    def load_settings(self):
        """加载设置到界面"""
        try:
            if not self.config_manager:
                return

            settings = self.config_manager.get_settings()

            # 通用设置
            self.target_language_combo.setCurrentText(settings.ui.target_language)
            self.theme_combo.setCurrentText(settings.ui.theme)
            self.opacity_slider.setValue(int(settings.ui.opacity * 100))
            self.font_size_spin.setValue(settings.ui.font_size)
            self.auto_copy_cb.setChecked(settings.ui.auto_copy)
            self.show_original_cb.setChecked(settings.ui.show_original)
            self.stay_on_top_cb.setChecked(settings.ui.window_stay_on_top)
            self.minimize_to_tray_cb.setChecked(settings.ui.minimize_to_tray)
            self.auto_start_cb.setChecked(settings.ui.auto_start)

            # 热键设置
            self.hotkey_enabled_cb.setChecked(settings.hotkey.enabled)
            self.hotkey_edit.set_hotkey(settings.hotkey.modifiers, settings.hotkey.key)

            # LLM设置
            self.provider_combo.setCurrentText(settings.llm.provider)
            self.api_key_edit.setText(settings.llm.api_key)
            self.api_endpoint_edit.setText(settings.llm.api_endpoint)
            self.model_name_edit.setText(settings.llm.model_name)
            self.temperature_spin.setValue(settings.llm.temperature)
            self.max_tokens_spin.setValue(settings.llm.max_tokens)
            self.timeout_spin.setValue(settings.llm.timeout)
            self.stream_cb.setChecked(settings.llm.stream)

            # OCR设置
            self.ocr_enabled_cb.setChecked(settings.ocr.enabled)
            self.confidence_spin.setValue(settings.ocr.confidence_threshold)
            self.text_threshold_spin.setValue(settings.ocr.text_threshold)
            self.link_threshold_spin.setValue(settings.ocr.link_threshold)
            self.canvas_size_spin.setValue(settings.ocr.canvas_size)
            self.mag_ratio_spin.setValue(settings.ocr.mag_ratio)

            # OCR语言设置
            for lang_code, cb in self.ocr_languages.items():
                cb.setChecked(lang_code in settings.ocr.languages)

            # Prompt设置
            self.load_prompt_templates()
            self.active_template_combo.setCurrentText(settings.prompt.active_template)

            # 清除修改标志
            self.has_unsaved_changes = False

            self.logger.info("设置已加载到界面")

        except Exception as e:
            self.logger.error(f"加载设置失败: {e}")
            QMessageBox.critical(self, "错误", f"加载设置失败: {e}")

    def load_prompt_templates(self):
        """加载Prompt模板"""
        try:
            # 清空列表
            self.builtin_templates_list.clear()
            self.custom_templates_list.clear()
            self.active_template_combo.clear()

            # 加载内置模板
            available_templates = sorted(get_available_templates())
            for template_name in available_templates:
                item = QListWidgetItem(template_name)
                template = self.prompt_manager.get_template(template_name)
                if template:
                    item.setToolTip(template.description)
                self.builtin_templates_list.addItem(item)

                self.active_template_combo.addItem(template_name)
                index = self.active_template_combo.findText(template_name)
                if index >= 0 and template:
                    self.active_template_combo.setItemData(
                        index,
                        template.description,
                        Qt.ItemDataRole.ToolTipRole
                    )

            # 加载自定义模板
            if self.config_manager:
                settings = self.config_manager.get_settings()
                for name, content in settings.prompt.custom_templates.items():
                    item = QListWidgetItem(name)
                    if content:
                        item.setToolTip(content[:200])
                    self.custom_templates_list.addItem(item)

                    self.active_template_combo.addItem(name)
                    index = self.active_template_combo.findText(name)
                    if index >= 0:
                        tooltip = content[:200] if content else "自定义模板"
                        self.active_template_combo.setItemData(
                            index,
                            tooltip,
                            Qt.ItemDataRole.ToolTipRole
                        )

        except Exception as e:
            self.logger.error(f"加载Prompt模板失败: {e}")

    def validate_settings(self) -> tuple:
        """验证设置"""
        errors = []

        # 验证API设置
        if not self.api_key_edit.text().strip():
            errors.append("API密钥不能为空")

        if not self.model_name_edit.text().strip():
            errors.append("模型名称不能为空")

        if not self.api_endpoint_edit.text().strip():
            errors.append("API端点不能为空")

        # 验证热键设置
        if self.hotkey_enabled_cb.isChecked():
            modifiers, key = self.hotkey_edit.get_hotkey()
            if not key:
                errors.append("热键主键不能为空")

        # 验证OCR语言设置
        if self.ocr_enabled_cb.isChecked():
            selected_langs = [code for code, cb in self.ocr_languages.items() if cb.isChecked()]
            if not selected_langs:
                errors.append("至少需要选择一种OCR识别语言")

        return len(errors) == 0, errors

    def apply_settings(self):
        """应用设置"""
        try:
            # 验证设置
            is_valid, errors = self.validate_settings()
            if not is_valid:
                QMessageBox.warning(self, "验证失败", "\n".join(errors))
                return

            if not self.config_manager:
                return

            # 更新通用设置
            self.config_manager.update_ui_settings(
                target_language=self.target_language_combo.currentText(),
                theme=self.theme_combo.currentText(),
                opacity=self.opacity_slider.value() / 100.0,
                font_size=self.font_size_spin.value(),
                auto_copy=self.auto_copy_cb.isChecked(),
                show_original=self.show_original_cb.isChecked(),
                window_stay_on_top=self.stay_on_top_cb.isChecked(),
                minimize_to_tray=self.minimize_to_tray_cb.isChecked(),
                auto_start=self.auto_start_cb.isChecked()
            )

            # 更新热键设置
            modifiers, key = self.hotkey_edit.get_hotkey()
            self.config_manager.update_hotkey_settings(
                enabled=self.hotkey_enabled_cb.isChecked(),
                modifiers=modifiers,
                key=key
            )

            # 更新LLM设置
            self.config_manager.update_llm_settings(
                provider=self.provider_combo.currentText(),
                api_key=self.api_key_edit.text(),
                api_endpoint=self.api_endpoint_edit.text(),
                model_name=self.model_name_edit.text(),
                temperature=self.temperature_spin.value(),
                max_tokens=self.max_tokens_spin.value(),
                timeout=self.timeout_spin.value(),
                stream=self.stream_cb.isChecked()
            )

            # 更新OCR设置
            selected_languages = [code for code, cb in self.ocr_languages.items() if cb.isChecked()]
            self.config_manager.update_ocr_settings(
                enabled=self.ocr_enabled_cb.isChecked(),
                languages=selected_languages,
                gpu=False,  # 强制CPU模式
                confidence_threshold=self.confidence_spin.value(),
                text_threshold=self.text_threshold_spin.value(),
                link_threshold=self.link_threshold_spin.value(),
                canvas_size=self.canvas_size_spin.value(),
                mag_ratio=self.mag_ratio_spin.value()
            )

            # 更新Prompt设置
            # 这里需要处理自定义模板的保存
            custom_templates = {}
            for i in range(self.custom_templates_list.count()):
                item = self.custom_templates_list.item(i)
                template_name = item.text()
                # 这里应该从编辑器获取模板内容，简化处理
                custom_templates[template_name] = self.template_content_edit.toPlainText()

            self.config_manager.update_prompt_settings(
                active_template=self.active_template_combo.currentText(),
                custom_templates=custom_templates
            )

            # 保存配置
            self.config_manager.save()

            # 清除修改标志
            self.has_unsaved_changes = False

            # 发射信号
            self.settings_applied.emit()

            # 显示保存成功提示
            QMessageBox.information(self, "成功", "设置已保存，正在重启应用以确保设置生效...")

            self.logger.info("设置已保存，开始自动重启应用")

            # 自动重启应用
            self.restart_application()

        except Exception as e:
            self.logger.error(f"应用设置失败: {e}")
            QMessageBox.critical(self, "错误", f"保存设置失败: {e}")

    def accept_settings(self):
        """确定并关闭"""
        self.apply_settings()
        self.accept()

    def cancel_changes(self):
        """取消更改"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "有未保存的更改，确定要取消吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.reject()

    def reset_settings(self):
        """重置设置"""
        reply = QMessageBox.question(
            self, "重置设置",
            "确定要重置所有设置为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.config_manager:
                self.config_manager.reset_to_defaults()
                self.load_settings()
                self.settings_reset.emit()
                QMessageBox.information(self, "成功", "设置已重置为默认值")

    def import_settings(self):
        """导入设置"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "导入配置", "", "JSON文件 (*.json)"
            )

            if file_path and self.config_manager:
                success = self.config_manager.import_config(file_path)
                if success:
                    self.load_settings()
                    QMessageBox.information(self, "成功", "配置导入成功")
                else:
                    QMessageBox.critical(self, "错误", "配置导入失败")

        except Exception as e:
            self.logger.error(f"导入设置失败: {e}")
            QMessageBox.critical(self, "错误", f"导入设置失败: {e}")

    def export_settings(self):
        """导出设置"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出配置", "settings_export.json", "JSON文件 (*.json)"
            )

            if file_path and self.config_manager:
                success = self.config_manager.export_config(file_path)
                if success:
                    QMessageBox.information(self, "成功", f"配置已导出到: {file_path}")
                else:
                    QMessageBox.critical(self, "错误", "配置导出失败")

        except Exception as e:
            self.logger.error(f"导出设置失败: {e}")
            QMessageBox.critical(self, "错误", f"导出设置失败: {e}")

    def test_api_connection(self):
        """测试API连接"""
        try:
            # 创建临时配置进行测试
            from ..core.llm_client import LLMConfig, APIProvider

            provider_map = {
                "siliconflow": APIProvider.SILICONFLOW,
                "doubao": APIProvider.DOUBAO,
                "openai": APIProvider.OPENAI,
                "custom": APIProvider.CUSTOM
            }

            provider = provider_map.get(self.provider_combo.currentText(), APIProvider.CUSTOM)

            config = LLMConfig(
                provider=provider,
                api_key=self.api_key_edit.text(),
                api_endpoint=self.api_endpoint_edit.text(),
                model_name=self.model_name_edit.text(),
                temperature=self.temperature_spin.value(),
                max_tokens=self.max_tokens_spin.value()
            )

            # 启动测试
            self.test_api_btn.setEnabled(False)
            self.api_test_progress.setVisible(True)
            self.api_test_progress.setRange(0, 0)
            self.api_test_result.setText("正在测试...")

            # 创建测试线程
            self.api_test_thread = APITestThread(config)
            self.api_test_thread.test_completed.connect(self.on_api_test_completed)
            self.api_test_thread.start()

        except Exception as e:
            self.logger.error(f"API测试失败: {e}")
            self.on_api_test_completed(False, f"测试失败: {e}")

    @pyqtSlot(bool, str)
    def on_api_test_completed(self, success: bool, message: str):
        """API测试完成"""
        self.test_api_btn.setEnabled(True)
        self.api_test_progress.setVisible(False)

        if success:
            self.api_test_result.setText("✓ " + message)
            self.api_test_result.setStyleSheet("color: green;")
        else:
            self.api_test_result.setText("✗ " + message)
            self.api_test_result.setStyleSheet("color: red;")

    def on_provider_changed(self, provider: str):
        """提供商变更处理"""
        # 根据提供商更新默认端点
        endpoints = {
            "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
            "doubao": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions"
        }

        default_endpoint = endpoints.get(provider, "")
        if default_endpoint:
            self.api_endpoint_edit.setText(default_endpoint)

    def toggle_password_visibility(self):
        """切换密码可见性"""
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("隐藏")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("显示")

    def on_template_selected(self, item):
        """模板选择处理"""
        if not item:
            return

        template_name = item.text()

        try:
            template = self.prompt_manager.get_template(template_name)
            description = template.description if template else ""
            content = template.template if template else ""

            if not template and self.config_manager:
                settings = self.config_manager.get_settings()
                content = settings.prompt.custom_templates.get(template_name, "")

            # 更新编辑器内容时不触发修改标志
            self.template_name_edit.blockSignals(True)
            self.template_desc_edit.blockSignals(True)
            self.template_content_edit.blockSignals(True)

            self.template_name_edit.setText(template_name)
            self.template_desc_edit.setText(description)
            self.template_content_edit.setPlainText(content)

            self.preview_text.clear()

        except Exception as e:
            self.logger.error(f"加载Prompt模板失败: {e}")
        finally:
            self.template_name_edit.blockSignals(False)
            self.template_desc_edit.blockSignals(False)
            self.template_content_edit.blockSignals(False)

    def add_custom_template(self):
        """添加自定义模板"""
        name = f"自定义模板{self.custom_templates_list.count() + 1}"
        item = QListWidgetItem(name)
        self.custom_templates_list.addItem(item)
        self.active_template_combo.addItem(name)
        self.mark_changed()

    def delete_custom_template(self):
        """删除自定义模板"""
        current_item = self.custom_templates_list.currentItem()
        if current_item:
            template_name = current_item.text()
            self.custom_templates_list.takeItem(self.custom_templates_list.row(current_item))

            # 从活动模板下拉框中移除
            index = self.active_template_combo.findText(template_name)
            if index >= 0:
                self.active_template_combo.removeItem(index)

            self.mark_changed()

    def preview_template(self):
        """预览模板"""
        template_content = self.template_content_edit.toPlainText()
        if template_content:
            # 简单的模板预览，使用示例数据
            preview = template_content.replace("{text}", "Hello World")
            preview = preview.replace("{target_language}", "简体中文")
            self.preview_text.setPlainText(preview)

    def mark_changed(self):
        """标记为已修改"""
        self.has_unsaved_changes = True

    def on_config_changed(self, section: str):
        """配置变更处理"""
        # 可以在这里处理配置的实时更新
        pass

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "有未保存的更改，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # 停止API测试线程
        if self.api_test_thread and self.api_test_thread.isRunning():
            self.api_test_thread.quit()
            self.api_test_thread.wait()

        super().closeEvent(event)

    def restart_application(self):
        """重启应用程序"""
        try:
            import sys
            import os

            if is_frozen():
                executable = str(Path(sys.executable).resolve())
                self.logger.info(f"准备重启应用: {executable} (重用当前进程)")

                from PyQt6.QtCore import QTimer

                def _restart_current_process():
                    self.logger.info("通过 os.execl 重启当前进程")
                    try:
                        os.execl(executable, executable)
                    except Exception as inner:
                        self.logger.error(f"进程内重启失败: {inner}")
                        QMessageBox.critical(self, "错误", f"重启应用失败: {inner}")

                app = QApplication.instance()
                if app is None:
                    raise RuntimeError("未找到 QApplication 实例")

                QTimer.singleShot(0, _restart_current_process)
                self.close()
                self._quit_current_app()
                return

            work_dir = str(get_runtime_working_dir())
            executable = str(Path(sys.executable).resolve())
            script_path = (get_project_root() / "main.py").resolve()
            if not script_path.exists():
                raise FileNotFoundError(f"未找到 main.py: {script_path}")

            arguments = [str(script_path)]
            display_target = f"{executable} {script_path}"

            self.logger.info(f"准备重启应用: {display_target}")

            success, pid = QProcess.startDetached(executable, arguments, work_dir)
            if not success:
                raise RuntimeError("无法启动新的应用实例")

            self.logger.info(f"新应用实例已启动，PID: {pid}")

            self.close()
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self._quit_current_app)

        except Exception as e:
            self.logger.error(f"重启应用失败: {e}")
            QMessageBox.critical(self, "错误", f"重启应用失败: {e}")

    def _quit_current_app(self):
        """退出当前应用"""
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()
        except Exception as e:
            self.logger.error(f"退出当前应用失败: {e}")


def create_settings_window(parent=None) -> SettingsWindow:
    """创建设置窗口实例"""
    return SettingsWindow(parent)












