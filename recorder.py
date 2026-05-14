import time
from collections import defaultdict
from typing import Any, Callable

from astrbot.api import logger


class MessageRecorder:
    def __init__(self, min_messages: int = 30, min_interval: float = 3600,
                 db=None):
        self.min_messages = min_messages
        self.min_interval = min_interval
        self._db = db
        self._buffers: dict[str, list[dict]] = defaultdict(list)
        self._last_learn_time: dict[str, float] = defaultdict(float)
        self._learning_callbacks: list[callable] = []
        self._load_from_db()

    def _load_from_db(self):
        if not self._db:
            return
        for chat_id in self._db.get_all_buffered_chat_ids():
            msgs = self._db.load_buffered_messages(chat_id)
            if msgs:
                self._buffers[chat_id] = msgs

    def _save_to_db(self, chat_id: str):
        if not self._db:
            return
        self._db.save_buffered_messages(chat_id, self._buffers.get(chat_id, []))

    def _clear_from_db(self, chat_id: str):
        if not self._db:
            return
        self._db.clear_buffered_messages(chat_id)

    def on_learning_ready(self, callback: Callable):
        self._learning_callbacks.append(callback)

    def record(self, chat_id: str, role: str, text: str,
               sender_name: str = "", timestamp: float | None = None):
        if not text or not text.strip():
            return
        self._buffers[chat_id].append({
            "role": role,
            "sender_name": sender_name,
            "text": text.strip(),
            "time": timestamp or time.time(),
        })
        self._save_to_db(chat_id)
        self._maybe_trigger(chat_id)

    def _user_message_count(self, chat_id: str) -> int:
        return sum(1 for m in self._buffers.get(chat_id, []) if m.get("role") == "user")

    def _maybe_trigger(self, chat_id: str):
        if self._user_message_count(chat_id) < self.min_messages:
            return
        elapsed = time.time() - self._last_learn_time.get(chat_id, 0)
        if elapsed < self.min_interval:
            return
        messages = list(self._buffers[chat_id])
        self._buffers[chat_id] = []
        self._clear_from_db(chat_id)
        self._last_learn_time[chat_id] = time.time()
        logger.info(f"MessageRecorder: triggering learning for {chat_id}, {len(messages)} messages")
        for cb in self._learning_callbacks:
            try:
                cb(chat_id, messages)
            except Exception as e:
                logger.error(f"MessageRecorder: callback error: {e}")

    def get_buffered_count(self, chat_id: str) -> int:
        return len(self._buffers.get(chat_id, []))

    def get_user_message_count(self, chat_id: str) -> int:
        return self._user_message_count(chat_id)

    def get_all_chat_ids(self) -> list[str]:
        return list(self._buffers.keys())

    def force_trigger(self, chat_id: str) -> list[dict] | None:
        """手动强制触发学习，不管消息数量是否达标"""
        buf = self._buffers.pop(chat_id, None)
        if buf and len(buf) > 0:
            self._clear_from_db(chat_id)
            self._last_learn_time[chat_id] = time.time()
            logger.info(f"MessageRecorder: force-trigger learning for {chat_id}, {len(buf)} messages")
            return buf
        return None

    def get_pending_chat_ids(self) -> list[str]:
        now = time.time()
        result = []
        for cid, buf in self._buffers.items():
            if self._user_message_count(cid) >= self.min_messages and \
               (now - self._last_learn_time.get(cid, 0)) >= self.min_interval:
                result.append(cid)
        return result

    def get_all_buffered_summary(self) -> list[dict]:
        now = time.time()
        result = []
        for chat_id, buf in sorted(self._buffers.items()):
            if not buf:
                continue
            user_cnt = self._user_message_count(chat_id)
            ready = user_cnt >= self.min_messages and \
                    (now - self._last_learn_time.get(chat_id, 0)) >= self.min_interval
            result.append({
                "chat_id": chat_id,
                "count": user_cnt,
                "total": len(buf),
                "min_messages": self.min_messages,
                "ready": ready,
                "last_message_preview": buf[-1].get("text", "")[:80] if buf else "",
            })
        return result

    def get_buffered_messages(self, chat_id: str) -> list[dict]:
        return list(self._buffers.get(chat_id, []))

    def clear_buffer(self, chat_id: str):
        """清除某个 chat 的消息缓冲"""
        self._buffers.pop(chat_id, None)
        self._clear_from_db(chat_id)
