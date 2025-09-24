"""
核心截图功能模块

使用mss库进行屏幕截图。
返回Pillow Image对象供后续OCR和处理使用。
"""

from typing import Optional

from PIL import Image
import mss
from PyQt6.QtCore import QObject, pyqtSignal


class ScreenshotManager(QObject):
    """截图管理器，提供截图功能"""

    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.sct = mss.mss()

    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
        """捕获指定区域的截图"""
        try:
            if width <= 0 or height <= 0:
                return None

            monitor = {
                "top": y,
                "left": x,
                "width": width,
                "height": height,
            }
            sct_img = self.sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        except Exception as e:
            self.error_occurred.emit(f"区域截图失败: {str(e)}")
            return None

    def cleanup(self):
        """清理资源"""
        if hasattr(self, "sct") and self.sct:
            self.sct.close()

