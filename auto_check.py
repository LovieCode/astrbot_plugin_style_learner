"""表达方式自动检查定时任务

功能：
1. 定期随机选取指定数量的未检查表达方式
2. 批量提交给 LLM 一次性评估
3. 通过评估的：rejected=0, checked=1
4. 未通过评估的：rejected=1, checked=1
"""

import json
import random
import re
import asyncio
from typing import Callable

from astrbot.api import logger

from .models import get_db


CHECK_PROMPT = """请评估以下表达方式是否合适。每条表达包含"使用情景"和"表达方式"。

评估标准：
1. 表达方式与使用情景是否匹配
2. 可以容忍口语化
3. 不能太过特指，需要具有泛用性
4. 一般不涉及具体人名

逐条评估，以 JSON 数组格式输出：
[
  {{"id": 1, "suitable": true, "reason": "合理，日常表达"}},
  {{"id": 2, "suitable": false, "reason": "太特指了"}}
]

待评估的表达式列表：
{items}"""


class ExpressionAutoCheckTask:
    """表达方式自动检查定时任务"""

    def __init__(
        self,
        llm_caller: Callable,
        check_interval: int = 300,
        check_count: int = 5,
        enabled: bool = True,
    ):
        self._llm_caller = llm_caller
        self._interval = check_interval
        self._count = check_count
        self._enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    def set_config(self, interval: int = 300, count: int = 5, enabled: bool = True):
        self._interval = interval
        self._count = count
        self._enabled = enabled

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        await asyncio.sleep(60)
        while self._running:
            try:
                if self._enabled and self._count > 0:
                    await self._run_check()
            except Exception as e:
                logger.error(f"AutoCheckTask error: {e}")
            await asyncio.sleep(self._interval)

    async def _run_check(self):
        db = get_db()
        unchecked = db.get_expressions(
            checked_only=False,
            exclude_rejected=True,
            page=1,
            page_size=200,
            status="pending",
        )[0]
        unchecked = [e for e in unchecked if not e.get("checked")]
        if not unchecked:
            return
        selected = random.sample(unchecked, min(self._count, len(unchecked)))
        logger.info(f"AutoCheck: batch checking {len(selected)} expressions")

        items_lines = []
        for i, expr in enumerate(selected, 1):
            items_lines.append(
                f"{i}. 使用情景：{expr['situation']}   表达方式：{expr['style']}"
            )
        prompt = CHECK_PROMPT.format(items="\n".join(items_lines))

        try:
            resp = await self._llm_caller(prompt)
        except Exception as e:
            logger.error(f"AutoCheck: LLM call failed: {e}")
            return
        if not resp:
            return

        m = re.search(r"\[.*\]", resp, re.DOTALL)
        if m:
            resp = m.group(0)
        try:
            results = json.loads(resp)
        except json.JSONDecodeError:
            logger.warning(f"AutoCheck: failed to parse response: {resp[:200]}")
            return

        if not isinstance(results, list):
            return

        for result in results:
            idx = result.get("id", 0) - 1
            if idx < 0 or idx >= len(selected):
                continue
            expr = selected[idx]
            suitable = result.get("suitable", True)
            reason = result.get("reason", "")
            db.check_expression(expr["id"], True, not suitable)
            status = "通过" if suitable else "不通过"
            logger.info(
                f"AutoCheck expr #{expr['id']} [{status}]: "
                f"{expr['situation'][:30]} - {expr['style'][:30]}"
                + (f" ({reason[:50]})" if reason else "")
            )
