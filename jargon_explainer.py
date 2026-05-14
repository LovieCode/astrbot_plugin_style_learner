from typing import Any, Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt


class JargonExplainer:
    _instance: "JargonExplainer | None" = None

    @classmethod
    def create(cls, llm_caller, global_jargon: bool = False):
        cls._instance = JargonExplainer(llm_caller, global_jargon)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "JargonExplainer | None":
        return cls._instance

    def __init__(self, llm_caller, global_jargon: bool = False):
        self._llm_caller = llm_caller
        self._global_jargon = global_jargon

    def match_from_text(self, text: str, chat_id: str | None = None) -> list[dict]:
        if not text or not text.strip():
            return []
        db = get_db()
        query_chat_id = None if self._global_jargon else chat_id
        matched = db.match_jargons_in_text(text, query_chat_id)
        if not matched and not self._global_jargon and chat_id:
            matched = db.match_jargons_in_text(text, None)
            if matched:
                logger.info(f"Jargons: fallback to global, got {len(matched)} for {chat_id}")
        return matched

    async def explain(self, text: str, chat_id: str | None = None) -> str | None:
        matched = self.match_from_text(text, chat_id)
        if not matched:
            return None
        lines = []
        for m in matched:
            lines.append(f"- {m['content']}: {m.get('meaning', '含义待确认')}")
        explanation = "\n".join(lines)
        prompt = get_prompt("summarize").format(
            chat_text=text[:200],
            explanations=explanation,
        )
        try:
            summary = await self._llm_caller(prompt)
            if summary and summary.strip():
                return summary.strip()
        except Exception as e:
            logger.error(f"Jargon summarization failed: {e}")
        return f"当前对话中的黑话解释：\n{explanation}"
