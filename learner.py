import time
from collections.abc import Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt
from .utils import (
    build_context_paragraph,
    detect_emotion,
    filter_text,
    parse_expression_response,
)

MAX_EXPRESSION_COUNT = 20
MAX_JARGON_COUNT = 30


class ExpressionLearner:
    def __init__(self, llm_caller: Callable):
        self._llm_caller = llm_caller

    async def learn_and_store(
        self,
        messages: list[dict],
        chat_id: str,
        bot_name: str = "Bot",
        enable_jargon: bool = True,
    ) -> list[dict]:
        """从消息中学习表达方式和黑话，返回新增的条目列表"""
        user_msgs = [
            m
            for m in messages
            if m.get("role") != "assistant" and m.get("text", "").strip()
        ]
        if not user_msgs:
            total = len(messages)
            assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
            empty_count = sum(1 for m in messages if not m.get("text", "").strip())
            logger.warning(
                f"ExpressionLearner: no valid user messages in {total} total "
                f"(assistant={assistant_count}, empty={empty_count}, user={total - assistant_count})"
            )
            return [
                {
                    "type": "error",
                    "content": f"没有有效的用户消息（{total}条中 assistant={assistant_count}，空文本={empty_count}）",
                }
            ]
        chat_str = self._build_chat_str(messages)
        prompt = get_prompt("learn").format(bot_name=bot_name, chat_str=chat_str)
        try:
            result = await self._llm_caller(prompt)
        except Exception as e:
            logger.error(f"ExpressionLearner: LLM call failed: {e}")
            return [{"type": "error", "content": f"LLM 调用异常: {e}"}]
        if not result:
            logger.warning("ExpressionLearner: LLM returned empty result")
            return [{"type": "error", "content": "LLM 返回了空结果"}]
        if isinstance(result, str) and result.startswith("ERROR:"):
            logger.error(f"ExpressionLearner: LLM error - {result}")
            return [{"type": "error", "content": result.replace("ERROR: ", "")}]
        expressions, jargons = parse_expression_response(result)
        # 数量上限过滤：超过上限则整批丢弃
        if len(expressions) > MAX_EXPRESSION_COUNT:
            logger.info(
                f"ExpressionLearner: 表达方式提取数量超过{MAX_EXPRESSION_COUNT}个（实际{len(expressions)}个），放弃本次学习"
            )
            expressions = []
        if len(jargons) > MAX_JARGON_COUNT:
            logger.info(
                f"ExpressionLearner: 黑话提取数量超过{MAX_JARGON_COUNT}个（实际{len(jargons)}个），放弃本次学习"
            )
            jargons = []
        if not expressions and not jargons:
            logger.warning(
                "ExpressionLearner: no valid expressions or jargons after filtering"
            )
            return []
        learnt: list[dict] = []
        db = get_db()
        now = time.time()
        # 获取机器人名称列表用于过滤
        banned_names = set()
        if bot_name and bot_name != "Bot":
            banned_names.add(bot_name.strip().casefold())
        for expr in expressions:
            sid = expr.get("source_id", "")
            line_idx = self._resolve_source_idx(sid, messages)
            if line_idx < 0:
                continue
            msg = messages[line_idx]
            if msg.get("role") == "assistant":
                continue
            ctx = filter_text(msg.get("text", ""))
            if not ctx:
                continue
            situation = expr.get("situation", "")
            style = expr.get("style", "")
            # 过滤掉包含 SELF 的表达
            if "SELF" in (situation or "") or "SELF" in (style or ""):
                continue
            # 过滤 style 与机器人名称重复的表达
            if style.strip().casefold() in banned_names:
                continue
            # 过滤包含表情/图片标记的表达
            if any(tag in (situation + style) for tag in ["表情：", "表情:", "[图片"]):
                continue
            emotion = expr.get("emotion", "").strip()
            if not emotion or emotion == "neutral":
                emotion = detect_emotion(style)
            existing, sim = db.find_similar_expression(situation, chat_id)
            if existing and sim >= 0.75:
                db.update_expression_count(existing["id"], situation, now)
                expr_id = existing["id"]
            else:
                expr_id = db.add_expression(
                    emotion, situation, style, ctx, chat_id, now
                )
            learnt.append(
                {
                    "type": "expression",
                    "id": expr_id,
                    "situation": situation,
                    "style": style,
                    "emotion": emotion,
                }
            )
        if enable_jargon and jargons:
            entries = []
            from .jargon_miner import JargonMiner

            miner = JargonMiner(self._llm_caller)
            cached = miner._check_cached_jargons_in_messages(messages)
            existing_contents = {e.get("content") for e in entries}
            for c in cached:
                if c["content"] not in existing_contents:
                    entries.append(c)
                    existing_contents.add(c["content"])
            for j in jargons:
                cname = j.get("content", "").strip()
                if not cname or len(cname) <= 1:
                    continue
                if cname in existing_contents:
                    continue
                sid = j.get("source_id", "")
                line_idx = self._resolve_source_idx(sid, messages)
                if line_idx < 0:
                    continue
                msg = messages[line_idx]
                if msg.get("role") == "assistant":
                    continue
                ctx = build_context_paragraph(messages, line_idx) or filter_text(
                    msg.get("text", "")
                )
                if ctx:
                    entry = {"content": cname, "context": ctx}
                    meaning = j.get("meaning", "").strip()
                    if meaning:
                        entry["meaning"] = meaning
                    entries.append(entry)
                    existing_contents.add(cname)
            if entries:
                await miner.process_entries(entries, chat_id)
                for entry in entries:
                    learnt.append(
                        {"type": "jargon", "content": entry.get("content", "")}
                    )
        logger.info(f"Learner: stored {len(learnt)} items for {chat_id}")
        return learnt

    def _build_chat_str(self, messages: list[dict]) -> str:
        sender_map: dict[str, str] = {}
        next_label = ord("A")
        lines = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            sender_name = msg.get("sender_name", "")
            if role == "assistant" or not sender_name:
                label = "SELF"
            else:
                if sender_name not in sender_map:
                    sender_map[sender_name] = chr(next_label)
                    next_label += 1
                label = sender_map[sender_name]
            text = msg.get("text", "")
            images = msg.get("images", [])
            if images:
                captions = [
                    img.get("caption") if isinstance(img, dict) else None
                    for img in images
                ]
                captions = [c for c in captions if c]
                if captions:
                    text += " [图片描述: " + "; ".join(captions) + "]"
                else:
                    text += text and " [图片]" or "[图片]"
            lines.append(f"[{i + 1}] {label}说 {text}")
        return "\n".join(lines)

    def _resolve_source_idx(self, source_id: str, messages: list[dict]) -> int:
        if not source_id.isdigit():
            return -1
        idx = int(source_id) - 1
        if 0 <= idx < len(messages):
            return idx
        return -1
