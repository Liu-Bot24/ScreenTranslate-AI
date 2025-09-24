"""
配置数据结构定义模块

定义应用程序的所有配置数据结构和默认值。
包括LLM配置、热键设置、语言选择、Prompt模板等。
支持从JSON序列化/反序列化和验证。
"""

import os
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class APIProvider(Enum):
    """API提供商枚举"""
    SILICONFLOW = "siliconflow"
    DOUBAO = "doubao"
    OPENAI = "openai"
    CUSTOM = "custom"


class ModifierKey(Enum):
    """修饰键枚举"""
    CTRL = "ctrl"
    SHIFT = "shift"
    ALT = "alt"
    CMD = "cmd"
    WIN = "win"


@dataclass
class LLMSettings:
    """LLM配置设置"""
    provider: str = APIProvider.SILICONFLOW.value
    api_key: str = ""
    api_endpoint: str = ""
    model_name: str = "deepseek-ai/deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30
    stream: bool = True

    def __post_init__(self):
        """初始化后处理"""
        # 如果没有设置API端点，根据提供商设置默认值
        if not self.api_endpoint:
            self.api_endpoint = self._get_default_endpoint()

    def _get_default_endpoint(self) -> str:
        """获取默认API端点"""
        endpoints = {
            APIProvider.SILICONFLOW.value: "https://api.siliconflow.cn/v1/chat/completions",
            APIProvider.DOUBAO.value: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            APIProvider.OPENAI.value: "https://api.openai.com/v1/chat/completions"
        }
        return endpoints.get(self.provider, "")

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not self.api_key.strip():
            errors.append("API密钥不能为空")

        if not self.model_name.strip():
            errors.append("模型名称不能为空")

        if not self.api_endpoint.strip():
            errors.append("API端点不能为空")

        if not (0.0 <= self.temperature <= 2.0):
            errors.append("温度值必须在0.0-2.0之间")

        if not (1 <= self.max_tokens <= 32768):
            errors.append("最大令牌数必须在1-32768之间")

        if not (1 <= self.timeout <= 300):
            errors.append("超时时间必须在1-300秒之间")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0


@dataclass
class HotkeySettings:
    """热键配置设置"""
    modifiers: List[str] = field(default_factory=lambda: ["alt"])
    key: str = "3"
    enabled: bool = True

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not self.key.strip():
            errors.append("主键不能为空")

        valid_modifiers = {e.value for e in ModifierKey}
        for modifier in self.modifiers:
            if modifier not in valid_modifiers:
                errors.append(f"无效的修饰键: {modifier}")

        if len(self.modifiers) > 4:
            errors.append("修饰键数量不能超过4个")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0

    def get_display_text(self) -> str:
        """获取显示文本"""
        if not self.modifiers or not self.key:
            return "未设置"

        parts = []
        for modifier in self.modifiers:
            if modifier == "ctrl":
                parts.append("Ctrl")
            elif modifier == "shift":
                parts.append("Shift")
            elif modifier == "alt":
                parts.append("Alt")
            elif modifier == "cmd":
                parts.append("Cmd")
            elif modifier == "win":
                parts.append("Win")

        parts.append(self.key.upper())
        return "+".join(parts)


@dataclass
class OCRSettings:
    """OCR配置设置"""
    enabled: bool = True
    languages: List[str] = field(default_factory=lambda: ["ch_sim", "en"])
    gpu: bool = False
    confidence_threshold: float = 0.4
    text_threshold: float = 0.6
    link_threshold: float = 0.4
    canvas_size: int = 2560
    mag_ratio: float = 1.0

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not self.languages:
            errors.append("至少需要选择一种OCR语言")

        if not (0.0 <= self.confidence_threshold <= 1.0):
            errors.append("置信度阈值必须在0.0-1.0之间")

        if not (0.0 <= self.text_threshold <= 1.0):
            errors.append("文本阈值必须在0.0-1.0之间")

        if not (0.0 <= self.link_threshold <= 1.0):
            errors.append("链接阈值必须在0.0-1.0之间")

        if not (256 <= self.canvas_size <= 4096):
            errors.append("画布大小必须在256-4096之间")

        if not (0.1 <= self.mag_ratio <= 3.0):
            errors.append("放大比例必须在0.1-3.0之间")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0


@dataclass
class PromptSettings:
    """Prompt模板配置设置"""
    active_template: str = "translate"
    custom_templates: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not self.active_template.strip():
            errors.append("活动模板名称不能为空")

        # 验证自定义模板
        for name, template in self.custom_templates.items():
            if not name.strip():
                errors.append("模板名称不能为空")
            if not template.strip():
                errors.append(f"模板'{name}'内容不能为空")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0


@dataclass
class TranslationSettings:
    """翻译相关配置"""
    source_language: str = 'auto'
    target_language: str = '简体中文'
    preserve_format: bool = True
    glossary_enabled: bool = False
    tone: str = 'default'

    def validate(self) -> list[str]:
        errors = []
        if not self.target_language.strip():
            errors.append('目标语言不能为空')
        return errors


@dataclass
class UISettings:
    """界面配置设置"""
    target_language: str = "简体中文"
    theme: str = "light"
    opacity: float = 0.9
    auto_copy: bool = True
    show_original: bool = True
    font_size: int = 12
    window_stay_on_top: bool = True
    minimize_to_tray: bool = True
    auto_start: bool = False
    result_window_width: int = 720
    result_window_height: int = 540

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not self.target_language.strip():
            errors.append("目标语言不能为空")

        if self.theme not in ["light", "dark", "auto"]:
            errors.append("主题必须是 light、dark 或 auto")

        if not (0.1 <= self.opacity <= 1.0):
            errors.append("透明度必须在0.1-1.0之间")

        if not (8 <= self.font_size <= 72):
            errors.append("字体大小必须在8-72之间")

        if not (360 <= self.result_window_width <= 3840):
            errors.append("结果窗口宽度必须在360-3840之间")

        if not (240 <= self.result_window_height <= 2160):
            errors.append("结果窗口高度必须在240-2160之间")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0


@dataclass
class HistorySettings:
    """历史记录配置设置"""
    enabled: bool = True
    max_records: int = 100
    auto_save: bool = True
    data_retention_days: int = 30

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if not (1 <= self.max_records <= 1000):
            errors.append("最大记录数必须在1-1000之间")

        if not (1 <= self.data_retention_days <= 365):
            errors.append("数据保留天数必须在1-365之间")

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate()) == 0


@dataclass
class AppSettings:
    """应用程序总配置"""
    version: str = "1.0.0"
    llm: LLMSettings = field(default_factory=LLMSettings)
    hotkey: HotkeySettings = field(default_factory=HotkeySettings)
    ocr: OCRSettings = field(default_factory=OCRSettings)
    prompt: PromptSettings = field(default_factory=PromptSettings)
    translation: TranslationSettings = field(default_factory=TranslationSettings)
    ui: UISettings = field(default_factory=UISettings)
    history: HistorySettings = field(default_factory=HistorySettings)

    def validate(self) -> Dict[str, List[str]]:
        """验证所有配置"""
        errors = {}

        llm_errors = self.llm.validate()
        if llm_errors:
            errors["llm"] = llm_errors

        hotkey_errors = self.hotkey.validate()
        if hotkey_errors:
            errors["hotkey"] = hotkey_errors

        ocr_errors = self.ocr.validate()
        if ocr_errors:
            errors["ocr"] = ocr_errors

        prompt_errors = self.prompt.validate()
        if prompt_errors:
            errors["prompt"] = prompt_errors

        ui_errors = self.ui.validate()
        if ui_errors:
            errors["ui"] = ui_errors

        history_errors = self.history.validate()
        if history_errors:
            errors["history"] = history_errors

        translation_errors = self.translation.validate()
        if translation_errors:
            errors["translation"] = translation_errors

        return errors

    def is_valid(self) -> bool:
        """检查所有配置是否有效"""
        errors = self.validate()
        return len(errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppSettings':
        """从字典创建配置对象"""
        # 处理嵌套对象
        settings = cls()

        if "version" in data:
            settings.version = data["version"]

        if "llm" in data:
            llm_data = data["llm"]
            settings.llm = LLMSettings(**llm_data)

        if "hotkey" in data:
            hotkey_data = data["hotkey"]
            settings.hotkey = HotkeySettings(**hotkey_data)

        if "ocr" in data:
            ocr_data = data["ocr"]
            settings.ocr = OCRSettings(**ocr_data)

        if "prompt" in data:
            prompt_data = data["prompt"]
            settings.prompt = PromptSettings(**prompt_data)

        if "translation" in data:
            translation_data = data["translation"]
            settings.translation = TranslationSettings(**translation_data)

        if "ui" in data:
            ui_data = data["ui"]
            settings.ui = UISettings(**ui_data)

        if "history" in data:
            history_data = data["history"]
            settings.history = HistorySettings(**history_data)

        return settings

    def get_env_overrides(self) -> 'AppSettings':
        """
        从环境变量获取配置覆盖

        Returns:
            AppSettings: 应用环境变量覆盖后的配置
        """
        # 创建配置副本
        settings = AppSettings.from_dict(self.to_dict())

        # LLM环境变量覆盖
        if os.getenv("SILICONFLOW_API_KEY"):
            settings.llm.provider = APIProvider.SILICONFLOW.value
            settings.llm.api_key = os.getenv("SILICONFLOW_API_KEY")
            settings.llm.model_name = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/deepseek-chat")

        elif os.getenv("DOUBAO_API_KEY"):
            settings.llm.provider = APIProvider.DOUBAO.value
            settings.llm.api_key = os.getenv("DOUBAO_API_KEY")
            settings.llm.model_name = os.getenv("DOUBAO_MODEL", "ep-20241010211228-dpc2p")

        elif os.getenv("OPENAI_API_KEY"):
            settings.llm.provider = APIProvider.OPENAI.value
            settings.llm.api_key = os.getenv("OPENAI_API_KEY")
            settings.llm.model_name = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

        # 重新设置API端点
        settings.llm.api_endpoint = settings.llm._get_default_endpoint()

        return settings


# 默认配置实例
DEFAULT_SETTINGS = AppSettings()


# 支持的语言列表
SUPPORTED_LANGUAGES = [
    "简体中文", "繁体中文", "English", "日本語", "한국어",
    "Français", "Deutsch", "Español", "Русский", "العربية"
]


# 支持的OCR语言
SUPPORTED_OCR_LANGUAGES = [
    "ch_sim", "ch_tra", "en", "ja", "ko", "fr", "de", "es", "ru", "ar"
]


# 主题列表
SUPPORTED_THEMES = ["light", "dark", "auto"]
