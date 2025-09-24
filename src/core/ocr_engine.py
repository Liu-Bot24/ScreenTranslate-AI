# -*- coding: utf-8 -*-
"""
OCR引擎模块

使用EasyOCR实现文字识别功能。
支持多语言识别、置信度过滤、GPU加速等功能。
集成配置管理系统和截图模块。
"""

import os
import sys
import logging
import platform
import tempfile
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import easyocr

from ..config.config_manager import ConfigManager, get_config_manager


@dataclass
class OCRResult:
    """OCR识别结果数据类"""
    text: str
    confidence: float
    bounding_box: Tuple[Tuple[int, int], ...]
    language: str = ""

    def __post_init__(self):
        """后处理初始化"""
        if self.confidence < 0:
            self.confidence = 0.0
        elif self.confidence > 1:
            self.confidence = 1.0


@dataclass
class OCRRegion:
    """OCR识别区域"""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    text: str
    confidence: float

    @property
    def area(self) -> int:
        """计算区域面积"""
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)


class OCREngine:
    """OCR文字识别引擎"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 配置管理器
        self.config_manager: Optional[ConfigManager] = None

        # EasyOCR读取器
        self.reader: Optional[easyocr.Reader] = None

        # 当前配置
        self.current_languages: List[str] = []
        self.gpu_enabled: bool = False

        # 平台信息
        self.platform = platform.system().lower()

        # 初始化
        self.init_config()

        self.logger.info("OCR引擎初始化完成")

    def init_config(self):
        """初始化配置"""
        try:
            self.config_manager = get_config_manager()
            if self.config_manager:
                self.config_manager.config_changed.connect(self.on_config_changed)

        except Exception as e:
            self.logger.error(f"初始化配置失败: {e}")

    def _check_gpu_support(self) -> bool:
        """检查GPU支持"""
        try:
            # 检查CUDA可用性
            import torch
            if torch.cuda.is_available():
                self.logger.info(f"检测到CUDA GPU: {torch.cuda.get_device_name(0)}")
                return True
            else:
                self.logger.info("未检测到可用的CUDA GPU")
                return False

        except ImportError:
            self.logger.warning("PyTorch未安装，无法检查GPU支持")
            return False
        except Exception as e:
            self.logger.error(f"GPU检查失败: {e}")
            return False

    def _get_ocr_config(self) -> Dict[str, Any]:
        """获取OCR配置"""
        default_config = {
            'enabled': True,
            'languages': ['ch_sim', 'en'],
            'gpu': False,
            'confidence_threshold': 0.6,
            'text_threshold': 0.7,
            'link_threshold': 0.4,
            'canvas_size': 2560,
            'mag_ratio': 1.0
        }

        if not self.config_manager:
            return default_config

        try:
            settings = self.config_manager.get_settings()
            return {
                'enabled': settings.ocr.enabled,
                'languages': settings.ocr.languages,
                'gpu': settings.ocr.gpu,
                'confidence_threshold': settings.ocr.confidence_threshold,
                'text_threshold': settings.ocr.text_threshold,
                'link_threshold': settings.ocr.link_threshold,
                'canvas_size': settings.ocr.canvas_size,
                'mag_ratio': settings.ocr.mag_ratio
            }
        except Exception as e:
            self.logger.error(f"获取OCR配置失败: {e}")
            return default_config

    def _init_reader(self, languages: List[str], gpu: bool = False) -> bool:
        """初始化EasyOCR读取器"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if (self.reader is not None and
                    self.current_languages == languages and
                    self.gpu_enabled == gpu):
                    return True

                self.logger.info(f"初始化OCR读取器，语言: {languages}, GPU: {gpu}")

                valid_languages = self._validate_languages(languages)
                if not valid_languages:
                    self.logger.error("没有有效的语言代码")
                    return False

                use_gpu = gpu and self._check_gpu_support()
                if gpu and not use_gpu:
                    self.logger.warning("GPU不可用，使用CPU模式")

                # 强制使用CPU模式，避免GPU依赖问题
                use_gpu = False
                self.logger.info("强制使用CPU模式进行OCR识别")

                self.reader = easyocr.Reader(
                    lang_list=valid_languages,
                    gpu=use_gpu,
                    verbose=False
                )

                self.current_languages = valid_languages
                self.gpu_enabled = use_gpu

                self.logger.info(f"OCR读取器初始化成功，支持语言: {valid_languages}")
                return True

            except Exception as e:
                if self._should_retry_reader_init(e, attempt, max_attempts):
                    wait_seconds = min(5, 2 ** attempt)
                    self.logger.warning("初始化OCR读取器失败({}/{})，{}秒后重试: {}".format(attempt + 1, max_attempts, wait_seconds, e))
                    time.sleep(wait_seconds)
                    continue

                self.logger.error(f"初始化OCR读取器失败: {e}")
                self.reader = None
                return False

        self.reader = None
        return False

    def _should_retry_reader_init(self, error: Exception, attempt: int, max_attempts: int) -> bool:
        """判断是否需要在模型下载过程中重试"""
        if attempt >= max_attempts - 1:
            return False

        message = str(error).lower()
        if isinstance(error, PermissionError):
            return True
        if 'temp.zip' in message or 'another program is using this file' in message or 'being used by another process' in message:
            return True
        if 'download' in message and 'model' in message:
            return True
        return False

    def _validate_languages(self, languages: List[str]) -> List[str]:
        """验证并转换语言代码"""
        # EasyOCR支持的语言代码映射
        language_map = {
            'ch_sim': 'ch_sim',      # 简体中文
            'ch_tra': 'ch_tra',      # 繁体中文
            'en': 'en',              # 英语
            'ja': 'ja',              # 日语
            'ko': 'ko',              # 韩语
            'fr': 'fr',              # 法语
            'de': 'de',              # 德语
            'es': 'es',              # 西班牙语
            'ru': 'ru',              # 俄语
            'ar': 'ar',              # 阿拉伯语
            'hi': 'hi',              # 印地语
            'th': 'th',              # 泰语
            'vi': 'vi',              # 越南语
            'it': 'it',              # 意大利语
            'pt': 'pt',              # 葡萄牙语
            'nl': 'nl',              # 荷兰语
            'pl': 'pl',              # 波兰语
            'sv': 'sv',              # 瑞典语
            'da': 'da',              # 丹麦语
            'no': 'no',              # 挪威语
            'fi': 'fi',              # 芬兰语
        }

        valid_languages = []
        for lang in languages:
            if lang in language_map:
                valid_languages.append(language_map[lang])
            else:
                self.logger.warning(f"不支持的语言代码: {lang}")

        # 确保至少有一种语言
        if not valid_languages:
            self.logger.warning("没有有效语言，使用默认语言：简体中文和英语")
            valid_languages = ['ch_sim', 'en']

        return valid_languages

    def _preprocess_image(self, image: Image.Image, config: Dict[str, Any]) -> np.ndarray:
        """预处理图像"""
        try:
            # 转换为RGB模式
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # 应用放大比例
            mag_ratio = config.get('mag_ratio', 1.0)
            if mag_ratio != 1.0:
                new_width = int(image.width * mag_ratio)
                new_height = int(image.height * mag_ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 限制画布大小
            canvas_size = config.get('canvas_size', 2560)
            if max(image.width, image.height) > canvas_size:
                # 按比例缩放
                ratio = canvas_size / max(image.width, image.height)
                new_width = int(image.width * ratio)
                new_height = int(image.height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 转换为numpy数组
            image_array = np.array(image)

            self.logger.debug(f"图像预处理完成，大小: {image_array.shape}")
            return image_array

        except Exception as e:
            self.logger.error(f"图像预处理失败: {e}")
            raise

    def _postprocess_results(self, results: List, config: Dict[str, Any]) -> List[OCRResult]:
        """后处理OCR结果"""
        try:
            confidence_threshold = config.get('confidence_threshold', 0.6)
            fallback_threshold = max(0.2, confidence_threshold * 0.5)

            ocr_results = []
            low_confidence_results: List[OCRResult] = []

            for result in results:
                if len(result) >= 2:
                    bbox = result[0]  # 边界框坐标
                    text = result[1]  # 识别的文本
                    confidence = result[2] if len(result) > 2 else 1.0  # 置信度

                    # 过滤低置信度结果
                    if confidence >= confidence_threshold:
                        # 转换边界框格式
                        bbox_tuple = tuple(tuple(point) for point in bbox)

                        ocr_result = OCRResult(
                            text=text.strip(),
                            confidence=confidence,
                            bounding_box=bbox_tuple
                        )

                        if ocr_result.text:  # 只保留非空文本
                            ocr_results.append(ocr_result)
                    elif confidence >= fallback_threshold:
                        bbox_tuple = tuple(tuple(point) for point in bbox)
                        fallback_result = OCRResult(
                            text=text.strip(),
                            confidence=confidence,
                            bounding_box=bbox_tuple
                        )
                        if fallback_result.text:
                            low_confidence_results.append(fallback_result)

            if not ocr_results and low_confidence_results:
                self.logger.debug("OCR高置信度结果为空，回退到低置信度文本")
                ocr_results = low_confidence_results
            elif low_confidence_results and len(ocr_results) <= 3:
                self.logger.debug("OCR结果过少，补充低置信度文本")
                ocr_results.extend(low_confidence_results)

            self.logger.debug(f"OCR后处理完成，有效结果: {len(ocr_results)}")
            return ocr_results

        except Exception as e:
            self.logger.error(f"OCR结果后处理失败: {e}")
            return []

    def _extract_text_with_layout(self, results: List[OCRResult]) -> str:
        """从OCR结果提取带布局的文本"""
        try:
            if not results:
                return ""

            # 按垂直位置排序文本块
            regions = []
            for result in results:
                # 计算边界框的中心点和边界
                bbox_points = result.bounding_box
                if len(bbox_points) >= 2:
                    xs = [point[0] for point in bbox_points]
                    ys = [point[1] for point in bbox_points]

                    x1, x2 = min(xs), max(xs)
                    y1, y2 = min(ys), max(ys)

                    region = OCRRegion(
                        bbox=(x1, y1, x2, y2),
                        text=result.text,
                        confidence=result.confidence
                    )
                    regions.append(region)

            if not regions:
                return ""

            # 按行分组
            lines = self._group_into_lines(regions)

            # 构建最终文本
            final_text = []
            for line in lines:
                # 按水平位置排序行内元素
                line.sort(key=lambda r: r.bbox[0])
                line_text = " ".join(region.text for region in line)
                final_text.append(line_text)

            result_text = "\n".join(final_text)

            self.logger.debug(f"文本布局提取完成，行数: {len(final_text)}")
            return result_text

        except Exception as e:
            self.logger.error(f"文本布局提取失败: {e}")
            # 降级处理：简单连接所有文本
            return " ".join(result.text for result in results)

    def _group_into_lines(self, regions: List[OCRRegion]) -> List[List[OCRRegion]]:
        """将文本区域按行分组"""
        try:
            if not regions:
                return []

            # 按垂直位置排序
            sorted_regions = sorted(regions, key=lambda r: r.bbox[1])

            lines = []
            current_line = [sorted_regions[0]]

            for region in sorted_regions[1:]:
                # 检查是否在同一行
                last_region = current_line[-1]

                # 计算垂直重叠
                y1_last, y2_last = last_region.bbox[1], last_region.bbox[3]
                y1_curr, y2_curr = region.bbox[1], region.bbox[3]

                overlap = min(y2_last, y2_curr) - max(y1_last, y1_curr)
                min_height = min(y2_last - y1_last, y2_curr - y1_curr)

                # 如果有足够的垂直重叠，认为在同一行
                if overlap > 0.3 * min_height:
                    current_line.append(region)
                else:
                    # 开始新行
                    lines.append(current_line)
                    current_line = [region]

            # 添加最后一行
            if current_line:
                lines.append(current_line)

            return lines

        except Exception as e:
            self.logger.error(f"行分组失败: {e}")
            return [[region] for region in regions]

    def recognize_image(self, image: Image.Image) -> str:
        """识别图像中的文字"""
        try:
            if not isinstance(image, Image.Image):
                raise ValueError("输入必须是PIL Image对象")

            if image.size[0] == 0 or image.size[1] == 0:
                raise ValueError("图像尺寸无效")

            # 获取配置
            config = self._get_ocr_config()

            if not config.get('enabled', True):
                self.logger.info("OCR功能已禁用")
                return ""

            # 初始化读取器
            if not self._init_reader(config['languages'], config['gpu']):
                raise RuntimeError("OCR读取器初始化失败")

            # 预处理图像
            image_array = self._preprocess_image(image, config)

            # 执行OCR识别
            self.logger.debug("开始OCR识别...")
            raw_results = self.reader.readtext(
                image_array,
                detail=1,  # 返回详细信息
                paragraph=False,  # 不按段落分组
                width_ths=config.get('text_threshold', 0.7),
                height_ths=config.get('link_threshold', 0.4)
            )

            # 后处理结果
            ocr_results = self._postprocess_results(raw_results, config)

            if not ocr_results:
                self.logger.info("未识别到任何文字")
                return ""

            # 提取文本并保持布局
            final_text = self._extract_text_with_layout(ocr_results)

            self.logger.info(f"OCR识别完成，识别到 {len(ocr_results)} 个文本块")
            return final_text

        except Exception as e:
            message = str(e)
            if 'numpy is not available' in message:
                self.logger.error("EasyOCR 报告缺少 NumPy，请确认环境已安装 numpy 包。")
                raise RuntimeError("EasyOCR 报告缺少 NumPy，请运行 `pip install --upgrade numpy` 后重试。") from e
            self.logger.error(f"OCR识别失败: {e}")
            raise

    def recognize_screenshot(self, screenshot_data: Any) -> str:
        """识别截图中的文字"""
        try:
            # 处理不同类型的截图数据
            if isinstance(screenshot_data, Image.Image):
                image = screenshot_data
            elif isinstance(screenshot_data, np.ndarray):
                # numpy数组转PIL Image
                if screenshot_data.dtype != np.uint8:
                    screenshot_data = screenshot_data.astype(np.uint8)
                image = Image.fromarray(screenshot_data)
            elif isinstance(screenshot_data, (str, Path)):
                # 文件路径
                image = Image.open(screenshot_data)
            else:
                raise ValueError(f"不支持的截图数据类型: {type(screenshot_data)}")

            return self.recognize_image(image)

        except Exception as e:
            self.logger.error(f"截图OCR识别失败: {e}")
            raise

    def get_detailed_results(self, image: Image.Image) -> List[OCRResult]:
        """获取详细的OCR识别结果"""
        try:
            if not isinstance(image, Image.Image):
                raise ValueError("输入必须是PIL Image对象")

            # 获取配置
            config = self._get_ocr_config()

            if not config.get('enabled', True):
                return []

            # 初始化读取器
            if not self._init_reader(config['languages'], config['gpu']):
                raise RuntimeError("OCR读取器初始化失败")

            # 预处理图像
            image_array = self._preprocess_image(image, config)

            # 执行OCR识别
            raw_results = self.reader.readtext(
                image_array,
                detail=1,
                paragraph=False,
                width_ths=config.get('text_threshold', 0.7),
                height_ths=config.get('link_threshold', 0.4)
            )

            # 后处理结果
            return self._postprocess_results(raw_results, config)

        except Exception as e:
            self.logger.error(f"获取详细OCR结果失败: {e}")
            return []

    def create_annotated_image(self, image: Image.Image, show_confidence: bool = True) -> Image.Image:
        """创建带注释的图像，显示识别结果"""
        try:
            # 获取详细结果
            results = self.get_detailed_results(image)

            if not results:
                return image.copy()

            # 创建副本用于绘制
            annotated = image.copy()
            draw = ImageDraw.Draw(annotated)

            # 尝试使用默认字体
            try:
                font = ImageFont.load_default()
            except:
                font = None

            # 绘制识别结果
            for i, result in enumerate(results):
                # 绘制边界框
                bbox_points = result.bounding_box
                if len(bbox_points) >= 4:
                    # 绘制多边形边界框
                    draw.polygon(bbox_points, outline='red', width=2)

                    # 绘制文本和置信度
                    if show_confidence:
                        label = f"{result.text} ({result.confidence:.2f})"
                    else:
                        label = result.text

                    # 在边界框上方绘制标签
                    text_pos = (bbox_points[0][0], bbox_points[0][1] - 20)
                    draw.text(text_pos, label, fill='red', font=font)

            return annotated

        except Exception as e:
            self.logger.error(f"创建注释图像失败: {e}")
            return image.copy()

    def is_ready(self) -> bool:
        """检查OCR引擎是否就绪"""
        try:
            config = self._get_ocr_config()
            return (config.get('enabled', True) and
                    self._init_reader(config['languages'], config['gpu']))
        except:
            return False

    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        return [
            'ch_sim',  # 简体中文
            'ch_tra',  # 繁体中文
            'en',      # 英语
            'ja',      # 日语
            'ko',      # 韩语
            'fr',      # 法语
            'de',      # 德语
            'es',      # 西班牙语
            'ru',      # 俄语
            'ar',      # 阿拉伯语
            'hi',      # 印地语
            'th',      # 泰语
            'vi',      # 越南语
            'it',      # 意大利语
            'pt',      # 葡萄牙语
            'nl',      # 荷兰语
            'pl',      # 波兰语
            'sv',      # 瑞典语
            'da',      # 丹麦语
            'no',      # 挪威语
            'fi',      # 芬兰语
        ]

    def get_status(self) -> Dict[str, Any]:
        """获取OCR引擎状态"""
        try:
            config = self._get_ocr_config()
            return {
                'enabled': config.get('enabled', True),
                'ready': self.is_ready(),
                'languages': self.current_languages,
                'gpu_enabled': self.gpu_enabled,
                'gpu_available': self._check_gpu_support(),
                'confidence_threshold': config.get('confidence_threshold', 0.6),
                'reader_initialized': self.reader is not None
            }
        except Exception as e:
            self.logger.error(f"获取OCR状态失败: {e}")
            return {'enabled': False, 'ready': False}

    def on_config_changed(self, section: str):
        """配置变更处理"""
        try:
            if section == "ocr":
                self.logger.info("OCR配置已更新，重新初始化读取器")
                # 清除当前读取器，下次使用时重新初始化
                self.reader = None
                self.current_languages = []

        except Exception as e:
            self.logger.error(f"处理配置变更失败: {e}")

    def cleanup(self):
        """清理资源"""
        try:
            if self.reader:
                # EasyOCR没有显式清理方法，设置为None让GC回收
                self.reader = None
                self.current_languages = []
                self.gpu_enabled = False

            self.logger.info("OCR引擎资源已清理")

        except Exception as e:
            self.logger.error(f"清理OCR引擎资源失败: {e}")


# 全局OCR引擎实例
_ocr_engine_instance = None


def get_ocr_engine() -> OCREngine:
    """获取全局OCR引擎实例"""
    global _ocr_engine_instance

    if _ocr_engine_instance is None:
        _ocr_engine_instance = OCREngine()

    return _ocr_engine_instance


def cleanup_ocr_engine():
    """清理全局OCR引擎"""
    global _ocr_engine_instance

    if _ocr_engine_instance is not None:
        _ocr_engine_instance.cleanup()
        _ocr_engine_instance = None
