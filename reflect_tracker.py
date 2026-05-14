"""表达反思追踪器：追踪管理员对表达审核提问的回复状态

类似 MaiBot 的 ReflectTracker，用于追踪管理员是否对表达审核提问做出了回复。
"""

import time
from typing import Callable

from astrbot.api import logger

from .models import get_db


class ReflectTracker:
    """追踪单个审核提问的状态"""

    def __init__(self, expression_id: int, created_time: float | None = None):
        self.expression_id = expression_id
        self.created_time = created_time or time.time()
        self._max_duration = 15 * 60  # 15 分钟超时
        self._max_messages = 30  # 最多等待 30 条消息
        self._message_count = 0

    def feed_message(self) -> bool:
        """收到一条消息，返回 True 表示应销毁此 tracker（超时或消息过多）"""
        self._message_count += 1
        if self._message_count > self._max_messages:
            logger.info(f"ReflectTracker for expr #{self.expression_id}: message count exceeded")
            return True
        if time.time() - self.created_time > self._max_duration:
            logger.info(f"ReflectTracker for expr #{self.expression_id}: timed out")
            return True
        return False


class ReflectTrackerManager:
    """管理所有活跃的 ReflectTracker"""

    def __init__(self):
        self._trackers: dict[str, ReflectTracker] = {}

    def add_tracker(self, chat_id: str, tracker: ReflectTracker):
        self._trackers[chat_id] = tracker

    def get_tracker(self, chat_id: str) -> ReflectTracker | None:
        return self._trackers.get(chat_id)

    def remove_tracker(self, chat_id: str):
        self._trackers.pop(chat_id, None)

    def check_all(self) -> list[str]:
        """检查所有 tracker 是否超时，返回需要移除的 chat_id 列表"""
        to_remove = []
        for cid, tracker in self._trackers.items():
            if time.time() - tracker.created_time > tracker._max_duration:
                to_remove.append(cid)
        for cid in to_remove:
            self.remove_tracker(cid)
        return to_remove


reflect_tracker_manager = ReflectTrackerManager()