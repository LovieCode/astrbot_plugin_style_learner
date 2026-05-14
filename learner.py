import random
import time
from difflib import SequenceMatcher
from typing import Any, Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt
from .utils import build_context_paragraph, detect_emotion, filter_text, parse_expression_response

MAX_EXPRESSION_COUNT = 20
MAX_JARGON_COUNT = 30


class ExpressionLearner:
    def __init__(self, llm_caller: Callable, check_caller: Callable | None = None):
        self._llm_caller = llm_caller
        self._check_caller = check_caller

    def set_check_caller(self, caller: Callable):
        self._check_caller = caller

    async def learn_and_store(self, messages: list[dict], chat_id: str,
                            bot_name: str = "Bot",
                            enable_jargon: bool = True) -> list[dict]:
        """从消息中学习表达方式和黑话，返回新增的条目列表"""
        user_msgs = [m for m in messages if m.get("role") != "assistant" and m.get("text", "").strip()]
        if not user_msgs:
            total = len(messages)
            assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
            empty_count = sum(1 for m in messages if not m.get("text", "").strip())
            logger.warning(
                f"ExpressionLearner: no valid user messages in {total} total "
                f"(assistant={assistant_count}, empty={empty_count}, user={total - assistant_count})"
            )
            return [{"type": "error", "content": f"没有有效的用户消息（{total}条中 assistant={assistant_count}，空文本={empty_count}）"}]
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
            logger.warning("ExpressionLearner: no valid expressions or jargons after filtering")
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
                use_llm = sim < 1.0
                new_situation = situation
                if use_llm and self._llm_caller:
                    merged = await self._compose_situation(db, existing["id"], situation, existing["situation"])
                    if merged:
                        new_situation = merged
                db.update_expression_count(existing["id"], new_situation, now)
                expr_id = existing["id"]
            else:
                expr_id = db.add_expression(emotion, situation, style, ctx, chat_id, now)
            learnt.append({
                "type": "expression",
                "id": expr_id,
                "situation": situation,
                "style": style,
                "emotion": emotion,
            })
            # 即时检查：count 增加后触发 LLM 审核
            if self._check_caller:
                await self._check_expression(expr_id, situation, style)
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
                ctx = build_context_paragraph(messages, line_idx) or filter_text(msg.get("text", ""))
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
                    learnt.append({"type": "jargon", "content": entry.get("content", "")})
        logger.info(f"Learner: stored {len(learnt)} items for {chat_id}")
        return learnt

    async def _compose_situation(self, db, expr_id: int, new_situation: str,
                                  existing_situation: str) -> str | None:
        """使用 LLM 合并相似 situation，保持简洁概括（不超过20字）"""
        prompt = (
            "请阅读以下两个聊天情境描述，并将它们概括成一句简短的话，"
            "长度不超过20个字，保留共同特点：\n"
            f"- {existing_situation}\n"
            f"- {new_situation}\n"
            "只输出概括内容。"
        )
        try:
            summary = await self._llm_caller(prompt)
            if summary and 0 < len(summary.strip()) <= 50:
                return summary.strip()
        except Exception as e:
            logger.warning(f"Situation composition failed: {e}")
        return None

    async def _check_expression(self, expr_id: int, situation: str, style: str):
        """即时 LLM 审核：count 增加后评估表达方式是否合适"""
        if not self._check_caller:
            return
        prompt = get_prompt("check") if get_prompt("check") else (
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
            prompt = prompt.format(situation=situation, style=style)
        except (KeyError, ValueError):
            pass
        try:
            resp = await self._check_caller(prompt)
        except Exception as e:
            logger.error(f"Expression check LLM call failed: {e}")
            return
        if not resp:
            return
        import re
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            resp = m.group(0)
        try:
            parsed = __import__("json").loads(resp)
        except Exception:
            return
        suitable = parsed.get("suitable", True)
        reason = parsed.get("reason", "")
        db = get_db()
        db.check_expression(expr_id, True, not suitable)
        status = "通过" if suitable else "不通过"
        logger.info(f"Expr #{expr_id} 即时审核 [{status}]: {situation[:30]} - {style[:30]}" + (f" ({reason[:50]})" if reason else ""))

    def _build_chat_str(self, messages: list[dict]) -> str:
        """构建匿名可读消息，不同发送者用 A/B/C... 标签，bot 用 SELF"""
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
            lines.append(f"[{i+1}] {label}说 {text}")
        return "\n".join(lines)

    def _resolve_source_idx(self, source_id: str, messages: list[dict]) -> int:
        if not source_id.isdigit():
            return -1
        idx = int(source_id) - 1
        if 0 <= idx < len(messages):
            return idx
        return -1