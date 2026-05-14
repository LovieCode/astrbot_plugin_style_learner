import json
import re
import time
from collections import OrderedDict
from typing import Any, Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt
from .utils import filter_text


INFERENCE_THRESHOLDS = [2, 4, 8, 12, 24, 60, 100]


def should_infer(jargon: dict) -> bool:
    if jargon.get("is_complete", False):
        return False
    count = jargon.get("count", 0) or 0
    last = jargon.get("last_inference_count", 0) or 0
    if count <= last:
        return False
    for t in INFERENCE_THRESHOLDS:
        if count >= t > last:
            return True
    return False


class JargonMiner:
    def __init__(self, llm_caller: Callable):
        self._llm_caller = llm_caller
        self._cache_limit = 50
        self._cache: OrderedDict[str, None] = OrderedDict()

    def _add_to_cache(self, content: str) -> None:
        """将提取到的黑话加入 LRU 缓存"""
        if not content:
            return
        key = content.strip()
        if not key or len(key) <= 1:
            return
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = None
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)

    def get_cached_jargons(self) -> list[str]:
        """获取缓存中的所有黑话列表"""
        return list(self._cache.keys())

    def _check_cached_jargons_in_messages(self, messages: list[dict]) -> list[dict]:
        """检查缓存中的黑话是否出现在消息中，返回匹配的条目列表"""
        if not messages or not self._cache:
            return []
        matched: list[dict] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant":
                continue
            text = filter_text(msg.get("text", ""))
            if not text:
                continue
            for jargon_content in self._cache:
                if not jargon_content:
                    continue
                if re.search(r"[\u4e00-\u9fff]", jargon_content):
                    pattern = re.escape(jargon_content)
                else:
                    pattern = r"\b" + re.escape(jargon_content) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    matched.append(
                        {
                            "content": jargon_content,
                            "context": text,
                            "source_id": str(i + 1),
                        }
                    )
        return matched

    @staticmethod
    def _is_valid_jargon(content: str) -> bool:
        if not content or len(content) <= 1:
            return False
        if re.match(r"^\d{1,4}$", content):
            return False
        if re.match(r"^[a-zA-Z0-9]{1}$", content):
            return False
        if re.match(r"^[\d]{2}[\d\s/-]*$", content):
            return False
        return True

    async def process_entries(self, entries: list[dict], chat_id: str):
        if not entries:
            return
        db = get_db()
        for entry in entries:
            content = entry.get("content", "").strip()
            if not content or len(content) <= 1:
                continue
            if not self._is_valid_jargon(content):
                logger.info(f"Jargon [{content}]: rejected by validation rule")
                continue
            self._add_to_cache(content)
            context = entry.get("context", "")
            is_global = False
            existed = db.add_or_update_jargon(content, context, chat_id, is_global)
            meaning = entry.get("meaning", "").strip()
            if meaning:
                db.update_jargon_meaning(
                    db.get_jargon_by_content(content)["id"],
                    meaning,
                    is_jargon=True,
                )
                db.conn.execute(
                    "UPDATE jargons SET is_complete=1 WHERE content=?",
                    (content,),
                )
                db.conn.commit()
                logger.info(f"Jargon [{content}]: 从上下文直接获取释义 - {meaning}")
                continue
            if existed:
                jargon = db.get_jargon_by_content(content)
                if jargon and should_infer(jargon):
                    await self._infer(jargon)

    async def _infer(self, jargon: dict):
        db = get_db()
        content = jargon["content"]
        raw = jargon.get("raw_contexts", "[]")
        try:
            contexts = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            contexts = []
        if not contexts:
            return
        context_text = "\n".join(contexts[-5:])
        prompt = (
            f"词条内容: {content}\n\n"
            f"该词条出现的上下文:\n{context_text}\n\n"
            f'请推断"{content}"的含义。\n'
            f"- 如果是在上下文中有特定含义的网络用语/缩写/黑话，请解释其含义\n"
            f"- 如果是常规词汇，也请说明\n"
            f'- 如果信息不足无法推断，请设置 "no_info": true\n\n'
            f"以 JSON 格式输出:\n"
            f'{{"meaning": "含义说明", "no_info": false}}'
        )
        try:
            resp = await self._llm_caller(prompt)
        except Exception as e:
            logger.error(f"Jargon inference LLM call failed: {e}")
            return
        if not resp:
            return
        infer = self._parse_json(resp)
        if not infer:
            return
        if infer.get("no_info") or not infer.get("meaning", "").strip():
            db.conn.execute(
                "UPDATE jargons SET last_inference_count=? WHERE id=?",
                (jargon["count"], jargon["id"]),
            )
            db.conn.commit()
            return
        has_meaning = True
        db.update_jargon_meaning(jargon["id"], infer.get("meaning", ""), is_jargon=True)
        db.conn.execute(
            "UPDATE jargons SET last_inference_count=?, is_complete=? WHERE id=?",
            (
                jargon["count"],
                1 if (jargon.get("count", 0) or 0) >= 20 else 0,
                jargon["id"],
            ),
        )
        db.conn.commit()
        logger.info(f"Jargon [{content}]: {infer.get('meaning', '')}")

    def _parse_json(self, text: str) -> dict | None:
        text = text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
