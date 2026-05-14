"""表达方式自动检查定时任务

功能：
1. 定期随机选取指定数量的未检查表达方式
2. 使用 LLM 进行评估
3. 通过评估的：rejected=0, checked=1
4. 未通过评估的：rejected=1, checked=1
"""

import random
import asyncio
from typing import Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt


class ExpressionAutoCheckTask:
    """表达方式自动检查定时任务"""

    def __init__(self, llm_caller: Callable, check_interval: int = 300,
                 check_count: int = 5, enabled: bool = True):
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
        # 启动后等待 60 秒再开始
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
            checked_only=False, exclude_rejected=True,
            page=1, page_size=200, status="pending",
        )[0]
        unchecked = [e for e in unchecked if not e.get("checked")]
        if not unchecked:
            return
        selected = random.sample(unchecked, min(self._count, len(unchecked)))
        logger.info(f"AutoCheck: checking {len(selected)} expressions")
        for expr in selected:
            await self._evaluate_one(db, expr)
            await asyncio.sleep(0.3)

    async def _evaluate_one(self, db, expr: dict):
        situation = expr["situation"]
        style = expr["style"]
        prompt = get_prompt("check")
        try:
            prompt = prompt.format(situation=situation, style=style)
        except (KeyError, ValueError):
            prompt = (
                f"请评估以下表达方式是否合适：\n"
                f"使用情景：{situation}\n"
                f"表达方式：{style}\n\n"
                "评估标准：\n"
                "1. 表达方式与使用情景是否匹配\n"
                "2. 可以容忍口语化\n"
                "3. 不能太过特指，需要具有泛用性\n"
                "4. 一般不涉及具体人名\n\n"
                '以 JSON 格式输出：{"suitable": true/false, "reason": "理由"}'
            )
        try:
            resp = await self._llm_caller(prompt)
        except Exception as e:
            logger.error(f"AutoCheck: LLM call failed for expr #{expr['id']}: {e}")
            return
        if not resp:
            return
        import re
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            resp = m.group(0)
        import json
        try:
            parsed = json.loads(resp)
        except json.JSONDecodeError:
            return
        suitable = parsed.get("suitable", True)
        reason = parsed.get("reason", "")
        db.check_expression(expr["id"], True, not suitable)
        status = "通过" if suitable else "不通过"
        logger.info(f"AutoCheck expr #{expr['id']} [{status}]: {situation[:30]} - {style[:30]}" + (f" ({reason[:50]})" if reason else ""))