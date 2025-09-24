# -*- coding: utf-8 -*-
"""
历史记录窗口界面模块

实现历史记录的可视化管理界面，支持查看、搜索、复制和删除操作。
集成历史管理器，提供用户友好的交互体验。
"""

import sys
import logging
from datetime import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                           QTableWidgetItem, QLineEdit, QPushButton, QLabel,
                           QTextEdit, QGroupBox, QMessageBox, QHeaderView,
                           QSplitter, QWidget, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QTextOption

from ..utils.history_manager import HistoryManager, HistoryRecord, get_history_manager


class HistoryWindow(QDialog):
    """历史记录窗口"""

    # 信号
    record_selected = pyqtSignal(str)  # 记录ID
    copy_requested = pyqtSignal(str, str)  # 文本内容, 类型

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 管理器
        self.history_manager: Optional[HistoryManager] = None

        # 当前选中记录
        self.current_record: Optional[HistoryRecord] = None

        # 初始化
        self.init_managers()
        self.setup_window()
        self.setup_ui()
        self.load_data()

        self.logger.info("历史窗口初始化完成")

    def init_managers(self):
        """初始化管理器"""
        try:
            self.history_manager = get_history_manager()

            if self.history_manager:
                self.history_manager.history_updated.connect(self.on_history_updated)

        except Exception as e:
            self.logger.error(f"初始化管理器失败: {e}")

    def setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle("翻译历史记录")
        self.setModal(False)
        self.resize(800, 600)

        # 设置窗口图标
        try:
            from pathlib import Path
            from PyQt6.QtGui import QIcon
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

        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索原文或译文...")
        self.search_edit.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.search_edit)

        self.clear_search_btn = QPushButton("清除")
        self.clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(self.clear_search_btn)

        layout.addLayout(search_layout)

        # 记录表格
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["时间", "原文", "译文", "语言对"])
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)

        # 设置表头
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.table_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.table_widget.doubleClicked.connect(self.copy_selected_translation)

        # 详情区域
        detail_group = QGroupBox("记录详情")
        detail_layout = QHBoxLayout(detail_group)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(12)

        wrap_mode = getattr(
            QTextOption.WrapMode,
            "WrapAtWordBoundaryOrAnywhere",
            QTextOption.WrapMode.WordWrap
        )

        def create_detail_panel(title: str) -> tuple[QWidget, QTextEdit]:
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(6)

            label = QLabel(title)
            panel_layout.addWidget(label)

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setWordWrapMode(wrap_mode)
            text_edit.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Expanding)
            panel_layout.addWidget(text_edit)

            return panel, text_edit

        original_panel, self.original_text_edit = create_detail_panel("原文:")
        translated_panel, self.translated_text_edit = create_detail_panel("译文:")

        detail_layout.addWidget(original_panel)
        detail_layout.addWidget(translated_panel)
        detail_layout.setStretch(0, 1)
        detail_layout.setStretch(1, 1)

        # 分隔表格和详情，便于调整比例
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table_widget)
        splitter.addWidget(detail_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.copy_original_btn = QPushButton("复制原文")
        self.copy_original_btn.clicked.connect(self.copy_original)
        self.copy_original_btn.setEnabled(False)
        button_layout.addWidget(self.copy_original_btn)

        self.copy_translated_btn = QPushButton("复制译文")
        self.copy_translated_btn.clicked.connect(self.copy_translated)
        self.copy_translated_btn.setEnabled(False)
        button_layout.addWidget(self.copy_translated_btn)

        self.delete_btn = QPushButton("删除记录")
        self.delete_btn.clicked.connect(self.delete_current_record)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_data)
        button_layout.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # 状态信息
        self.status_label = QLabel("就绪")
        layout.addWidget(self.status_label)

    def load_data(self):
        """加载数据"""
        try:
            if not self.history_manager:
                return

            records = self.history_manager.get_records()
            self.populate_table(records)

            self.status_label.setText(f"共 {len(records)} 条记录")
            self.logger.debug(f"加载了 {len(records)} 条历史记录")

        except Exception as e:
            self.logger.error(f"加载数据失败: {e}")

    def populate_table(self, records: List[HistoryRecord]):
        """填充表格数据"""
        try:
            self.table_widget.setRowCount(len(records))

            for row, record in enumerate(records):
                # 时间
                try:
                    dt = datetime.fromisoformat(record.timestamp)
                    time_str = dt.strftime("%m-%d %H:%M")
                except:
                    time_str = record.timestamp[:16]

                time_item = QTableWidgetItem(time_str)
                time_item.setData(Qt.ItemDataRole.UserRole, record)
                self.table_widget.setItem(row, 0, time_item)

                # 原文
                original_text = record.original_text
                if len(original_text) > 50:
                    original_text = original_text[:50] + "..."
                original_item = QTableWidgetItem(original_text)
                original_item.setToolTip(record.original_text)
                self.table_widget.setItem(row, 1, original_item)

                # 译文
                translated_text = record.translated_text
                if len(translated_text) > 50:
                    translated_text = translated_text[:50] + "..."
                translated_item = QTableWidgetItem(translated_text)
                translated_item.setToolTip(record.translated_text)
                self.table_widget.setItem(row, 2, translated_item)

                # 语言对
                language_pair = f"{record.source_language} → {record.target_language}"
                lang_item = QTableWidgetItem(language_pair)
                self.table_widget.setItem(row, 3, lang_item)

        except Exception as e:
            self.logger.error(f"填充表格失败: {e}")

    def on_search_changed(self, text: str):
        """搜索文本变更"""
        try:
            if not self.history_manager:
                return

            records = self.history_manager.get_records(search_query=text)
            self.populate_table(records)
            self.status_label.setText(f"搜索结果: {len(records)} 条记录")

        except Exception as e:
            self.logger.error(f"搜索失败: {e}")

    def clear_search(self):
        """清除搜索"""
        self.search_edit.clear()

    def on_selection_changed(self):
        """选择变更"""
        try:
            current_row = self.table_widget.currentRow()
            if current_row >= 0:
                time_item = self.table_widget.item(current_row, 0)
                if time_item:
                    record = time_item.data(Qt.ItemDataRole.UserRole)
                    if record:
                        self.current_record = record
                        self.update_detail_panel(record)
                        self.set_buttons_enabled(True)
                        self.record_selected.emit(record.id)
                        return

            # 没有选择
            self.current_record = None
            self.clear_detail_panel()
            self.set_buttons_enabled(False)

        except Exception as e:
            self.logger.error(f"处理选择变更失败: {e}")

    def update_detail_panel(self, record: HistoryRecord):
        """更新详情面板"""
        try:
            self.original_text_edit.setPlainText(record.original_text)
            self.translated_text_edit.setPlainText(record.translated_text)

        except Exception as e:
            self.logger.error(f"更新详情面板失败: {e}")

    def clear_detail_panel(self):
        """清空详情面板"""
        self.original_text_edit.clear()
        self.translated_text_edit.clear()

    def set_buttons_enabled(self, enabled: bool):
        """设置按钮可用性"""
        self.copy_original_btn.setEnabled(enabled)
        self.copy_translated_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def copy_original(self):
        """复制原文"""
        try:
            if self.current_record:
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(self.current_record.original_text)
                self.copy_requested.emit(self.current_record.original_text, "original")
                self.status_label.setText("原文已复制到剪贴板")

        except Exception as e:
            self.logger.error(f"复制原文失败: {e}")

    def copy_translated(self):
        """复制译文"""
        try:
            if self.current_record:
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(self.current_record.translated_text)
                self.copy_requested.emit(self.current_record.translated_text, "translated")
                self.status_label.setText("译文已复制到剪贴板")

        except Exception as e:
            self.logger.error(f"复制译文失败: {e}")

    def copy_selected_translation(self):
        """双击复制译文"""
        self.copy_translated()

    def delete_current_record(self):
        """删除当前记录"""
        try:
            if not self.current_record:
                return

            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除这条翻译记录吗？\n\n原文: {self.current_record.original_text[:50]}...",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                if self.history_manager:
                    success = self.history_manager.remove_record(self.current_record.id)
                    if success:
                        self.status_label.setText("记录已删除")
                        self.logger.info(f"删除记录: {self.current_record.id}")
                    else:
                        QMessageBox.warning(self, "删除失败", "无法删除记录，请重试。")

        except Exception as e:
            self.logger.error(f"删除记录失败: {e}")
            QMessageBox.critical(self, "错误", f"删除记录失败: {e}")

    @pyqtSlot()
    def on_history_updated(self):
        """历史记录更新"""
        self.load_data()


def create_history_window(parent=None) -> HistoryWindow:
    """创建历史窗口实例"""
    return HistoryWindow(parent)
