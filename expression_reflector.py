"""表达反思器：定期向管理员提问，收集对表达方式的审核反馈"""

import random
import time
from collections import defaultdict
from typing import Callable

from astrbot.api import logger

from .models import get_db


ASK_INTERVAL_MIN = 600   # 最小间隔 10 分钟
ASK_INTERVAL_MAX = 900   # 最大间隔 15 分钟


class ExpressionReflector:
    def __init__(self, llm_caller: Callable):
        self._llm_caller = llm_caller
        self._last_ask_times: dict[str, float] = defaultdict(float)
        self._operator_chat_id = ""
        self._current_expression_id: int | None = None

    def set_operator(self, chat_id: str):
        """设置接收审核提问的管理员 chat_id"""
        self._operator_chat_id = chat_id

    def has_active_question(self) -> bool:
        """是否有等待回复的审核提问"""
        return self._current_expression_id is not None

    def should_ask(self, chat_id: str) -> bool:
        """检查是否应该向该群的管理员提问"""
        if not self._operator_chat_id:
            return False
        if self._current_expression_id is not None:
            return False
        now = time.time()
        last = self._last_ask_times.get("__global__", 0)
        interval = random.uniform(ASK_INTERVAL_MIN, ASK_INTERVAL_MAX)
        return (now - last) >= interval

    async def ask_if_needed(self) -> str | None:
        """检查是否需要提问，返回发给管理员的提问文本，否则返回 None"""
        if not self.should_ask(""):
            return None
        db = get_db()
        unchecked = db.get_expressions(
            checked_only=False, exclude_rejected=True,
            page=1, page_size=50, status="pending",
        )[0]
        unchecked = [e for e in unchecked if not e.get("checked")]
        if not unchecked:
            return None
        expr = random.choice(unchecked)
        self._current_expression_id = expr["id"]
        ask_text = (
            f"我正在学习新的表达方式，请帮我看看这个是否合适？\n\n"
            f"**学习到的表达信息**\n"
            f"- 情景 (Situation): {expr['situation']}\n"
            f"- 风格 (Style): {expr['style']}\n\n"
            '回复「通过」以采纳，回复「拒绝」或提供修改建议来改进。\n'
            f"(表达ID: {expr['id']})"
        )
        self._last_ask_times["__global__"] = time.time()
        logger.info(f"Reflector: asking operator about expression #{expr['id']}")
        return ask_text

    def on_admin_response(self, text: str) -> tuple[int, bool, str] | None:
        """处理管理员的回复，返回 (expr_id, approved, correction_text) 或 None"""
        if not text:
            return None
        text = text.strip()
        import re
        m = re.search(r"表达ID[：:]\s*(\d+)", text)
        if m:
            expr_id = int(m.group(1))
        else:
            return None
        db = get_db()
        if "通过" in text and "不通过" not in text:
            db.check_expression(expr_id, checked=True, rejected=False)
            logger.info(f"Reflector: expression #{expr_id} approved by operator")
            self._current_expression_id = None
            return (expr_id, True, "")
        elif "拒绝" in text or "不通过" in text:
            db.check_expression(expr_id, checked=True, rejected=True)
            logger.info(f"Reflector: expression #{expr_id} rejected by operator")
            self._current_expression_id = None
            return (expr_id, False, text)
        return None