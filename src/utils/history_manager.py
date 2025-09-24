# -*- coding: utf-8 -*-
"""
历史记录管理模块

实现翻译历史的存储、检索和管理功能。
使用JSON文件持久化存储，支持最大记录数限制。
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from contextlib import contextmanager

from PyQt6.QtCore import QObject, pyqtSignal

from .path_utils import get_data_dir


@dataclass
class HistoryRecord:
    """历史记录数据类"""
    id: str
    original_text: str
    translated_text: str
    source_language: str = "auto"
    target_language: str = "zh"
    timestamp: str = ""
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}
        if not self.id:
            # 生成基于时间戳的ID
            self.id = str(int(datetime.now().timestamp() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryRecord':
        """从字典创建实例"""
        return cls(**data)

    def matches_search(self, query: str) -> bool:
        """检查是否匹配搜索条件"""
        if not query:
            return True

        query = query.lower()
        return (query in self.original_text.lower() or
                query in self.translated_text.lower() or
                query in self.source_language.lower() or
                query in self.target_language.lower())


class HistoryManager(QObject):
    """历史记录管理器"""

    # 信号
    history_updated = pyqtSignal()  # 历史记录更新
    record_added = pyqtSignal(str)  # 记录添加，传递记录ID
    record_removed = pyqtSignal(str)  # 记录删除，传递记录ID

    def __init__(self,
                 data_dir: Optional[str] = None,
                 filename: str = "history.json",
                 max_records: int = 20):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # 配置
        base_dir = Path(data_dir) if data_dir else get_data_dir()
        self.data_dir = base_dir
        self.filename = filename
        self.max_records = max_records

        # 文件路径
        self.file_path = self.data_dir / self.filename

        # 内存缓存
        self._records: List[HistoryRecord] = []
        self._lock = threading.RLock()

        # 初始化
        self._ensure_data_directory()
        self.load_history()

        self.logger.info(f"历史管理器初始化完成，文件路径: {self.file_path}")

    def _ensure_data_directory(self):
        """确保数据目录存在"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"数据目录已确保存在: {self.data_dir}")
        except Exception as e:
            self.logger.error(f"创建数据目录失败: {e}")
            raise

    @contextmanager
    def _file_lock(self):
        """文件锁上下文管理器"""
        with self._lock:
            yield

    def load_history(self) -> bool:
        """加载历史记录"""
        try:
            with self._file_lock():
                if not self.file_path.exists():
                    self.logger.info("历史文件不存在，创建空历史")
                    self._records = []
                    return True

                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 验证数据格式
                if not isinstance(data, dict) or 'records' not in data:
                    self.logger.warning("历史文件格式无效，重置为空")
                    self._records = []
                    return True

                # 加载记录
                records = []
                for record_data in data.get('records', []):
                    try:
                        record = HistoryRecord.from_dict(record_data)
                        records.append(record)
                    except Exception as e:
                        self.logger.warning(f"跳过无效记录: {e}")

                self._records = records
                self.logger.info(f"成功加载 {len(self._records)} 条历史记录")
                return True

        except Exception as e:
            self.logger.error(f"加载历史记录失败: {e}")
            self._records = []
            return False

    def save_history(self) -> bool:
        """保存历史记录"""
        try:
            with self._file_lock():
                # 准备数据
                data = {
                    "version": "1.0",
                    "created_at": datetime.now().isoformat(),
                    "total_records": len(self._records),
                    "max_records": self.max_records,
                    "records": [record.to_dict() for record in self._records]
                }

                # 写入临时文件，然后重命名（原子操作）
                temp_path = self.file_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 原子替换
                temp_path.replace(self.file_path)

                self.logger.debug(f"历史记录已保存: {len(self._records)} 条")
                return True

        except Exception as e:
            self.logger.error(f"保存历史记录失败: {e}")
            return False

    def add_record(self,
                   original_text: str,
                   translated_text: str,
                   source_language: str = "auto",
                   target_language: str = "zh",
                   metadata: Dict[str, Any] = None) -> Optional[str]:
        """添加历史记录"""
        try:
            if not original_text.strip() or not translated_text.strip():
                self.logger.warning("尝试添加空记录，已跳过")
                return None

            with self._file_lock():
                # 创建新记录
                record = HistoryRecord(
                    id="",  # 自动生成
                    original_text=original_text.strip(),
                    translated_text=translated_text.strip(),
                    source_language=source_language,
                    target_language=target_language,
                    metadata=metadata or {}
                )

                # 检查是否已存在相同记录
                for existing in self._records:
                    if (existing.original_text == record.original_text and
                        existing.translated_text == record.translated_text):
                        self.logger.debug("记录已存在，更新时间戳")
                        existing.timestamp = record.timestamp
                        self.save_history()
                        self.history_updated.emit()
                        return existing.id

                # 添加到列表开头（最新的在前）
                self._records.insert(0, record)

                # 限制记录数量
                if len(self._records) > self.max_records:
                    removed_records = self._records[self.max_records:]
                    self._records = self._records[:self.max_records]

                    for removed in removed_records:
                        self.record_removed.emit(removed.id)
                        self.logger.debug(f"删除旧记录: {removed.id}")

                # 保存到文件
                success = self.save_history()
                if success:
                    self.record_added.emit(record.id)
                    self.history_updated.emit()
                    self.logger.info(f"添加历史记录: {record.id}")
                    return record.id
                else:
                    # 保存失败，回滚
                    self._records.remove(record)
                    return None

        except Exception as e:
            self.logger.error(f"添加历史记录失败: {e}")
            return None

    def get_records(self,
                   limit: Optional[int] = None,
                   search_query: str = "") -> List[HistoryRecord]:
        """获取历史记录"""
        try:
            with self._file_lock():
                records = self._records.copy()

                # 搜索过滤
                if search_query:
                    records = [r for r in records if r.matches_search(search_query)]

                # 限制数量
                if limit and limit > 0:
                    records = records[:limit]

                return records

        except Exception as e:
            self.logger.error(f"获取历史记录失败: {e}")
            return []

    def get_record_by_id(self, record_id: str) -> Optional[HistoryRecord]:
        """根据ID获取记录"""
        try:
            with self._file_lock():
                for record in self._records:
                    if record.id == record_id:
                        return record
                return None

        except Exception as e:
            self.logger.error(f"获取记录失败: {e}")
            return None

    def remove_record(self, record_id: str) -> bool:
        """删除记录"""
        try:
            with self._file_lock():
                for i, record in enumerate(self._records):
                    if record.id == record_id:
                        removed_record = self._records.pop(i)
                        success = self.save_history()
                        if success:
                            self.record_removed.emit(record_id)
                            self.history_updated.emit()
                            self.logger.info(f"删除历史记录: {record_id}")
                            return True
                        else:
                            # 保存失败，回滚
                            self._records.insert(i, removed_record)
                            return False

                self.logger.warning(f"未找到要删除的记录: {record_id}")
                return False

        except Exception as e:
            self.logger.error(f"删除历史记录失败: {e}")
            return False

    def clear_history(self) -> bool:
        """清空历史记录"""
        try:
            with self._file_lock():
                old_records = self._records.copy()
                self._records.clear()

                success = self.save_history()
                if success:
                    for record in old_records:
                        self.record_removed.emit(record.id)
                    self.history_updated.emit()
                    self.logger.info("历史记录已清空")
                    return True
                else:
                    # 保存失败，回滚
                    self._records = old_records
                    return False

        except Exception as e:
            self.logger.error(f"清空历史记录失败: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            with self._file_lock():
                total_records = len(self._records)

                if total_records == 0:
                    return {
                        "total_records": 0,
                        "oldest_record": None,
                        "newest_record": None,
                        "language_pairs": {},
                        "avg_original_length": 0,
                        "avg_translated_length": 0
                    }

                # 计算统计数据
                language_pairs = {}
                total_original_length = 0
                total_translated_length = 0

                oldest_time = self._records[0].timestamp
                newest_time = self._records[0].timestamp

                for record in self._records:
                    # 语言对统计
                    pair = f"{record.source_language} → {record.target_language}"
                    language_pairs[pair] = language_pairs.get(pair, 0) + 1

                    # 长度统计
                    total_original_length += len(record.original_text)
                    total_translated_length += len(record.translated_text)

                    # 时间统计
                    if record.timestamp < oldest_time:
                        oldest_time = record.timestamp
                    if record.timestamp > newest_time:
                        newest_time = record.timestamp

                return {
                    "total_records": total_records,
                    "oldest_record": oldest_time,
                    "newest_record": newest_time,
                    "language_pairs": language_pairs,
                    "avg_original_length": total_original_length / total_records,
                    "avg_translated_length": total_translated_length / total_records,
                    "max_records": self.max_records,
                    "file_path": str(self.file_path)
                }

        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {}

    def export_history(self, export_path: str, format_type: str = "json") -> bool:
        """导出历史记录"""
        try:
            with self._file_lock():
                export_file = Path(export_path)

                if format_type.lower() == "json":
                    data = {
                        "export_time": datetime.now().isoformat(),
                        "total_records": len(self._records),
                        "records": [record.to_dict() for record in self._records]
                    }

                    with open(export_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)

                elif format_type.lower() == "txt":
                    with open(export_file, 'w', encoding='utf-8') as f:
                        f.write(f"翻译历史记录导出\n")
                        f.write(f"导出时间: {datetime.now().isoformat()}\n")
                        f.write(f"总记录数: {len(self._records)}\n")
                        f.write("=" * 50 + "\n\n")

                        for i, record in enumerate(self._records, 1):
                            f.write(f"记录 {i}:\n")
                            f.write(f"时间: {record.timestamp}\n")
                            f.write(f"原文 ({record.source_language}): {record.original_text}\n")
                            f.write(f"译文 ({record.target_language}): {record.translated_text}\n")
                            f.write("-" * 30 + "\n\n")

                else:
                    raise ValueError(f"不支持的导出格式: {format_type}")

                self.logger.info(f"历史记录已导出到: {export_file}")
                return True

        except Exception as e:
            self.logger.error(f"导出历史记录失败: {e}")
            return False


# 全局历史管理器实例
_history_manager_instance = None
_history_manager_lock = threading.Lock()


def get_history_manager(data_dir: Optional[str] = None,
                       filename: str = "history.json",
                       max_records: int = 20) -> HistoryManager:
    """获取全局历史管理器实例"""
    global _history_manager_instance

    with _history_manager_lock:
        if _history_manager_instance is None:
            _history_manager_instance = HistoryManager(data_dir=data_dir, filename=filename, max_records=max_records)
        return _history_manager_instance


def cleanup_history_manager():
    """清理全局历史管理器"""
    global _history_manager_instance

    with _history_manager_lock:
        if _history_manager_instance is not None:
            try:
                _history_manager_instance.save_history()
            except Exception as e:
                logging.getLogger(__name__).error(f"清理历史管理器时保存失败: {e}")
            finally:
                _history_manager_instance = None