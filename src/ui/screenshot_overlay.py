"""
截图选择覆盖层模块

提供全屏遮罩用于区域选择，支持 ESC/右键取消。
兼容高 DPI 屏幕，拖拽过程中显示尺寸提示和操作提示。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap


class ScreenshotOverlay(QWidget):
    """全屏截图选择层"""

    area_selected = pyqtSignal(int, int, int, int)
    selection_cancelled = pyqtSignal()

    def __init__(self, background: QPixmap, geometry: QRect):
        super().__init__()
        self.start_point: Optional[QPoint] = None
        self.end_point: Optional[QPoint] = None
        self.is_selecting = False
        self.background_pixmap: Optional[QPixmap] = background
        self.screen_geometry = geometry

        self._setup_window()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMouseTracking(True)

        if self.screen_geometry and not self.screen_geometry.isNull():
            self.setGeometry(self.screen_geometry)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.geometry())

        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.update()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            event.accept()
            self.cancel_selection()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_selecting and self.start_point:
            self.end_point = event.pos()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            if self.start_point and self.end_point:
                selection_rect = self._get_selection_rect()
                if selection_rect.width() > 5 and selection_rect.height() > 5:
                    self.area_selected.emit(
                        selection_rect.x(),
                        selection_rect.y(),
                        selection_rect.width(),
                        selection_rect.height(),
                    )
                else:
                    self.selection_cancelled.emit()
            self.close()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            event.accept()
            self.cancel_selection()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.cancel_selection()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.is_selecting = False
        self.releaseKeyboard()
        self.releaseMouse()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 绘制逻辑
    # ------------------------------------------------------------------
    def _get_selection_rect(self) -> QRect:
        if not self.start_point or not self.end_point:
            return QRect()

        rect = QRect(self.start_point, self.end_point)
        return rect.normalized()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.background_pixmap and not self.background_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.background_pixmap)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.is_selecting and self.start_point and self.end_point:
            selection_rect = self._get_selection_rect()

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection_rect, Qt.GlobalColor.transparent)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            if self.background_pixmap and not self.background_pixmap.isNull():
                pixel_ratio = self.background_pixmap.devicePixelRatio() or 1.0
                physical_rect = QRect(
                    int(selection_rect.x() * pixel_ratio),
                    int(selection_rect.y() * pixel_ratio),
                    int(selection_rect.width() * pixel_ratio),
                    int(selection_rect.height() * pixel_ratio),
                )
                painter.drawPixmap(selection_rect, self.background_pixmap, physical_rect)

            pen = QPen(QColor(0, 120, 215), 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(selection_rect)

            if selection_rect.width() > 30 and selection_rect.height() > 20:
                self._draw_size_info(painter, selection_rect)

        self._draw_help_text(painter)

    def _draw_size_info(self, painter: QPainter, rect: QRect):
        size_text = f"{rect.width()} × {rect.height()}"

        painter.setPen(QPen(QColor(255, 255, 255)))
        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)

        text_rect = painter.fontMetrics().boundingRect(size_text)
        xpos = rect.x() + 6
        ypos = rect.y() - 12
        if ypos < 20:
            ypos = rect.y() + 28

        bg_rect = QRect(
            xpos - 4,
            ypos - text_rect.height(),
            text_rect.width() + 8,
            text_rect.height() + 6,
        )
        painter.fillRect(bg_rect, QColor(0, 0, 0, 180))
        painter.drawText(xpos, ypos, size_text)

    def _draw_help_text(self, painter: QPainter):
        help_text = "拖拽选择区域 • 右键/ESC 取消"
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(help_text)
        margin = 18
        bg_rect = QRect(
            self.rect().left() + margin,
            self.rect().bottom() - text_rect.height() - margin,
            text_rect.width() + 12,
            text_rect.height() + 10,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(bg_rect, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            bg_rect.left() + 6,
            bg_rect.top() + text_rect.height() + 2,
            help_text,
        )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def cancel_selection(self) -> None:
        self.is_selecting = False
        self.start_point = None
        self.end_point = None
        if self.isVisible():
            self.selection_cancelled.emit()
            self.close()

    def show_overlay(self) -> None:
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()
        self.grabMouse()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
