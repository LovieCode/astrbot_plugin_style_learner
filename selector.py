import json
import random
import re
from difflib import SequenceMatcher
from typing import Any, Callable

from astrbot.api import logger

from .models import get_db
from .prompt_manager import get_prompt
from .utils import detect_emotion, weighted_sample, build_style_hint

_STOP_WORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "当",
    "时",
    "使用",
    "表示",
    "可以",
    "吗",
    "吧",
    "呢",
    "啊",
    "哦",
    "嗯",
    "呀",
    "嘛",
    "哈",
    "对",
    "不",
    "都",
    "就",
    "才",
    "也",
    "还",
    "又",
    "再",
    "把",
    "被",
    "让",
    "给",
    "跟",
    "比",
    "从",
    "到",
    "向",
    "往",
    "用",
    "以",
    "要",
    "会",
    "能",
    "可",
    "该",
    "应",
    "想",
    "看",
    "说",
    "做",
    "去",
    "来",
    "上",
    "下",
    "有",
    "没",
    "这个",
    "那个",
    "一个",
    "什么",
    "怎么",
    "为什么",
    "一下",
    "一点",
    "很",
    "非常",
    "比较",
    "太",
    "真",
    "大",
    "小",
    "多",
    "少",
    "这",
    "那",
    "个",
    "中",
    "了",
    "我",
    "你",
    "他",
    "她",
    "它",
    "们",
    "着",
    "过",
    "得",
    "地",
    "只",
    "些",
    "每",
    "各",
    "哪",
    "谁",
    "怎",
    "么",
    "样",
    "能",
    "会",
    "可",
    "该",
    "应",
    "想",
    "要",
}


def _extract_keywords(text: str) -> list[str]:
    """从中文文本中提取有意义的 2-3 字关键词，过滤停用词"""
    text = text.strip().lower()
    parts = re.split(r"[，。,\.\s!！?？：:；;、（）()\[\]【】\"'「」『』\n\t]+", text)
    keywords = []
    for part in parts:
        part = part.strip()
        if len(part) < 2:
            continue
        for size in range(2, min(4, len(part) + 1)):
            for i in range(len(part) - size + 1):
                w = part[i : i + size]
                if w not in _STOP_WORDS and not w.isdigit():
                    keywords.append(w)
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def _match_score(user_text: str, situation: str, style: str) -> float:
    """计算用户文本与一条表达方式的匹配分数。

    方向修正：从用户文本提取关键词，检查是否在表达描述中出现。
    使用命中数而非命中率，避免噪声关键词稀释分数。
    1 个命中 = 0.3 基础分，2 个 = 0.5，3+ 个 = 0.7。
    叠加 SequenceMatcher 相似度作为微调。
    """
    if not user_text:
        return 0.0

    combined = f"{situation} {style}".lower()
    user_kws = _extract_keywords(user_text)

    match_count = 0
    matched_kws: list[str] = []
    for kw in user_kws:
        if kw in combined:
            match_count += 1
            matched_kws.append(kw)

    if match_count == 0:
        base = 0.0
    elif match_count == 1:
        base = 0.35
    elif match_count == 2:
        base = 0.55
    else:
        base = 0.75

    seq = SequenceMatcher(None, user_text.lower(), combined).ratio()

    score = base + seq * 0.25

    if matched_kws:
        logger.debug(
            f"StyleSelector match: user_kws={matched_kws} -> situation='{situation[:30]}' "
            f"score={score:.3f} (base={base:.2f}, seq={seq:.2f})"
        )

    return score


def _seq_sim(a: str, b: str) -> float:
    """SequenceMatcher 快捷封装"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class ExpressionSelector:
    def __init__(self, llm_caller: Callable | None = None):
        self._llm_caller = llm_caller
        self._expression_groups: list[list[str]] = []
        self._global_expressions: bool = False

    def set_expression_groups(self, groups: list[list[str]]):
        """设置跨群共享配置"""
        self._expression_groups = groups

    def set_global_expressions(self, global_exprs: bool):
        """设置是否全局共享表达方式"""
        self._global_expressions = global_exprs

    def get_related_chat_ids(self, chat_id: str) -> list[str]:
        """根据 expression_groups 配置获取关联 chat_id 列表"""
        if not self._expression_groups:
            return [chat_id]
        global_group_exists = any("*" in group for group in self._expression_groups)
        if global_group_exists:
            all_chat_ids = set()
            for group in self._expression_groups:
                for cid in group:
                    if cid and cid != "*":
                        all_chat_ids.add(cid)
            return list(all_chat_ids) if all_chat_ids else [chat_id]
        for group in self._expression_groups:
            if chat_id in group:
                return [cid for cid in group if cid]
        return [chat_id]

    def select(
        self,
        chat_id: str,
        user_text: str,
        emotion: str | None = None,
        max_count: int = 5,
        mode: str = "simple",
        checked_only: bool = False,
    ) -> list[dict]:
        if emotion is None:
            emotion = detect_emotion(user_text)
        db = get_db()
        related_ids = self.get_related_chat_ids(chat_id)
        return self._select_simple(
            db, related_ids, user_text, emotion, max_count, checked_only
        )

    def _select_simple(
        self,
        db,
        chat_ids: list[str],
        user_text: str,
        emotion: str,
        max_count: int,
        checked_only: bool,
    ) -> list[dict]:
        """关键词匹配 + 序列相似度混合选择。

        核心改进：从用户文本提取关键词 → 检查是否在表达的 situation/style 中出现。
        命中 1 个关键词即获基础分，多个命中叠加。
        当日志量 <= 数据库总量 5 条时全量返回。
        无任何命中时按 count 降序兜底返回，确保命中率不为 0。
        当指定 chat_id 查不到时，回退到查询所有表达。
        """
        all_exprs: list[dict] = []
        if self._global_expressions:
            exprs, _ = db.get_expressions(
                chat_id=None,
                checked_only=checked_only,
                exclude_rejected=True,
                page=1,
                page_size=100,
            )
            all_exprs.extend(exprs)
        else:
            for cid in chat_ids:
                exprs, _ = db.get_expressions(
                    chat_id=cid,
                    checked_only=checked_only,
                    exclude_rejected=True,
                    page=1,
                    page_size=100,
                )
                all_exprs.extend(exprs)
            if not all_exprs:
                exprs, _ = db.get_expressions(
                    chat_id=None,
                    checked_only=checked_only,
                    exclude_rejected=True,
                    page=1,
                    page_size=100,
                )
                all_exprs.extend(exprs)
                if all_exprs:
                    logger.info(
                        f"StyleSelector: _select_simple fallback to global, "
                        f"got {len(all_exprs)} expressions for {chat_ids[0] if chat_ids else '?'}"
                    )

        if not all_exprs:
            logger.info(
                f"StyleSelector: _select_simple no expressions in DB for "
                f"{chat_ids[0] if chat_ids else '?'}"
            )
            return []

        if len(all_exprs) <= 5:
            logger.info(
                f"StyleSelector: _select_simple only {len(all_exprs)} expressions, "
                f"returning all"
            )
            return all_exprs[:max_count]

        scored: list[tuple[float, dict]] = []
        for expr in all_exprs:
            situation = str(expr.get("situation", ""))
            style = str(expr.get("style", ""))

            ms = _match_score(user_text, situation, style)

            count = expr.get("count", 1)
            count_boost = min(count / 20.0, 0.15)

            score = ms + count_boost

            if emotion and emotion != "neutral" and expr.get("emotion", "") == emotion:
                score += 0.1

            scored.append((score, expr))

        scored.sort(key=lambda x: x[0], reverse=True)

        has_any_match = scored[0][0] > 0.05

        seen_ids: set[int] = set()
        result: list[dict] = []
        for s, expr in scored:
            eid = expr.get("id")
            if eid not in seen_ids:
                seen_ids.add(eid)
                result.append(expr)
            if len(result) >= max_count:
                break

        if result and has_any_match:
            top3 = [
                (f"{e.get('situation', '')[:20]}", round(sc, 3)) for sc, e in scored[:3]
            ]
            logger.info(
                f"StyleSelector: _select_simple matched {len(result)} exprs "
                f"for '{user_text[:30]}' → top3={top3}"
            )
        elif result:
            logger.info(
                f"StyleSelector: _select_simple fallback (no keyword match), "
                f"returning {len(result)} by count for '{user_text[:30]}'"
            )
        else:
            logger.info(
                f"StyleSelector: _select_simple no match for "
                f"'{user_text[:30]}' (total {len(all_exprs)} expressions)"
            )

        return result

    async def select_classic(
        self,
        chat_id: str,
        user_text: str,
        max_num: int = 5,
        checked_only: bool = False,
        chat_observe_info: str = "",
        bot_name: str = "Bot",
        target_message: str = "",
        reply_reason: str = "",
    ) -> list[dict]:
        """classic 模式：随机候选池 + LLM 双层选择（对齐 MaiBot 逻辑）"""
        db = get_db()
        related_ids = self.get_related_chat_ids(chat_id)
        all_exprs: list[dict] = []
        if self._global_expressions:
            exprs, _ = db.get_expressions(
                chat_id=None,
                checked_only=checked_only,
                exclude_rejected=True,
                page=1,
                page_size=200,
            )
            all_exprs.extend(exprs)
        else:
            for cid in related_ids:
                exprs, _ = db.get_expressions(
                    chat_id=cid,
                    checked_only=checked_only,
                    exclude_rejected=True,
                    page=1,
                    page_size=200,
                )
                all_exprs.extend(exprs)
            if not all_exprs:
                exprs, _ = db.get_expressions(
                    chat_id=None,
                    checked_only=checked_only,
                    exclude_rejected=True,
                    page=1,
                    page_size=200,
                )
                all_exprs.extend(exprs)
                if all_exprs:
                    logger.info(
                        f"StyleSelector: select_classic fallback to global, "
                        f"got {len(all_exprs)} expressions for {chat_id}"
                    )
        seen = set()
        deduped = []
        for e in all_exprs:
            if e["id"] not in seen:
                seen.add(e["id"])
                deduped.append(e)
        all_exprs = deduped
        if len(all_exprs) < 3:
            logger.info(
                f"StyleSelector: only {len(all_exprs)} expressions for {chat_id}, "
                f"falling back to _select_simple"
            )
            return self._select_simple(
                db,
                related_ids,
                user_text,
                detect_emotion(user_text),
                max_num,
                checked_only,
            )
        high_count = [e for e in all_exprs if e.get("count", 1) > 1]
        select_high = min(len(high_count), max_num) if len(high_count) >= 3 else 0
        selected_high = (
            weighted_sample(high_count, select_high) if select_high > 0 else []
        )
        remaining = max_num + 5 - len(selected_high)
        selected_random = weighted_sample(all_exprs, min(len(all_exprs), remaining))
        candidates: dict[int, dict] = {}
        for e in selected_high:
            candidates[e["id"]] = e
        for e in selected_random:
            if e["id"] not in candidates:
                candidates[e["id"]] = e
        candidate_list = list(candidates.values())
        random.shuffle(candidate_list)
        if not self._llm_caller:
            logger.info(
                "StyleSelector classic: no LLM caller, returning random candidates"
            )
            return candidate_list[:max_num]
        all_situations: list[str] = []
        for i, expr in enumerate(candidate_list):
            all_situations.append(
                f"{i + 1}.{expr['situation']} 时，使用 {expr['style']}"
            )
        all_situations_str = "\n".join(all_situations)
        target_str = ""
        target_extra = ""
        if target_message:
            target_str = f'，现在你想要对这条消息进行回复："{target_message}"'
            target_extra = "4.考虑你要回复的目标消息"
        chat_ctx = ""
        reply_reason_block = ""
        if reply_reason:
            reply_reason_block = f"你的回复理由是：{reply_reason}"
        else:
            chat_ctx = (
                chat_observe_info or f"以下是正在进行的聊天内容：{user_text[:500]}"
            )
        prompt = get_prompt("selection").format(
            chat_observe_info=chat_ctx,
            bot_name=bot_name,
            all_situations=all_situations_str,
            max_num=max_num,
            target_message=target_str,
            target_message_extra_block=target_extra,
            reply_reason_block=reply_reason_block,
        )
        try:
            raw = await self._llm_caller(prompt)
        except Exception as e:
            logger.error(f"Expression selection LLM call failed: {e}")
            return candidate_list[:max_num]
        if not raw:
            logger.warning(
                "StyleSelector: selection LLM returned empty, using candidates"
            )
            return candidate_list[:max_num]
        if isinstance(raw, str) and raw.startswith("ERROR:"):
            logger.warning(
                f"StyleSelector: selection LLM error: {raw}, falling back to candidates"
            )
            return candidate_list[:max_num]
        try:
            parsed = self._parse_selection_response(raw)
        except Exception as e:
            logger.error(f"Failed to parse selection response: {e}")
            return candidate_list[:max_num]
        if not parsed or "selected_situations" not in parsed:
            logger.warning(
                f"StyleSelector: failed to parse selection response: {str(raw)[:200]}"
            )
            return candidate_list[:max_num]
        indices = parsed["selected_situations"]
        result = []
        for idx in indices:
            if isinstance(idx, int) and 1 <= idx <= len(candidate_list):
                result.append(candidate_list[idx - 1])
        if result:
            self._update_last_active_time(db, result)
        logger.info(
            f"StyleSelector classic: selected {len(result)} from {len(candidate_list)} candidates"
        )
        return result[:max_num] if result else candidate_list[:max_num]

    def _parse_selection_response(self, raw: str) -> dict | None:
        raw = raw.strip()
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _update_last_active_time(self, db, expressions: list[dict]):
        import time

        now = time.time()
        for expr in expressions:
            try:
                db.conn.execute(
                    "UPDATE expressions SET last_active_time=? WHERE id=?",
                    (now, expr["id"]),
                )
            except Exception:
                pass
        db.conn.commit()

    async def build_hint(
        self,
        chat_id: str,
        user_text: str | None,
        jargons: list[dict] | None = None,
        mode: str = "simple",
        checked_only: bool = False,
        chat_observe_info: str | None = None,
        bot_name: str = "Bot",
        target_message: str = "",
        reply_reason: str = "",
    ) -> str | None:
        emotion = detect_emotion(user_text or "")
        expressions = []
        if mode == "classic" and self._llm_caller:
            expressions = await self.select_classic(
                chat_id=chat_id,
                user_text=user_text or "",
                max_num=5,
                checked_only=checked_only,
                chat_observe_info=chat_observe_info or "",
                bot_name=bot_name,
                target_message=target_message,
                reply_reason=reply_reason,
            )
        else:
            db = get_db()
            related_ids = self.get_related_chat_ids(chat_id)
            expressions = self._select_simple(
                db, related_ids, user_text or "", emotion, 5, checked_only
            )
        if not expressions and not jargons:
            logger.info(
                f"StyleSelector: no expressions ({len(expressions)}) and no jargons "
                f"({len(jargons or [])}) matched for {chat_id}"
            )
            return None
        logger.info(
            f"StyleSelector: injecting {len(expressions)} expressions + {len(jargons or [])} jargons "
            f"for {chat_id} (emotion={emotion}, mode={mode})"
        )
        return build_style_hint(expressions, jargons or [], emotion)
