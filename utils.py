import difflib
import json
import random
import re
from typing import Any

EMOTION_KEYWORDS: dict[str, list[str]] = {
    "开心": [
        "哈哈",
        "好耶",
        "太棒",
        "开心",
        "喜欢",
        "nice",
        "棒",
        "笑死",
        "乐",
        "耶",
        "妙啊",
        "嘿嘿",
        "嘻嘻",
        "✌",
        "🤣",
        "好开心",
        "太好了",
    ],
    "惊讶": [
        "真的吗",
        "不会吧",
        "哇塞",
        "惊了",
        "真的假的",
        "离谱",
        "居然",
        "我去",
        "卧槽",
        "天哪",
        "厉害了",
        "震撼",
        "好家伙",
        "什么情况",
    ],
    "无奈": [
        "唉",
        "行吧",
        "那算了",
        "没办法",
        "随便吧",
        "无语",
        "麻了",
        "摆了",
        "算了",
        "行行行",
        "🤷",
        "好气哦还是要微笑",
    ],
    "嘲讽": [
        "对对对",
        "你说得对",
        "就这",
        "典",
        "急了",
        "不会真有人",
        "乐子",
        "6",
        "不愧是你",
        "好厉害的",
        "这波",
        "太强了",
    ],
    "鼓励": [
        "加油",
        "你可以的",
        "没事",
        "冲冲冲",
        "奥利给",
        "顶",
        "好起来了",
        "冲",
        "相信你",
        "一定能",
        "支持",
        "投你一票",
    ],
    "生气": [
        "有病",
        "滚",
        "烦",
        "气死",
        "受不了",
        "什么鬼",
        "有毒",
        "别烦",
        "cnm",
        "sb",
        "tmd",
        "尼玛",
        "滚蛋",
        "爬",
    ],
    "悲伤": [
        "难受",
        "想哭",
        "呜呜",
        "哭了",
        "破防",
        "emo",
        "玉玉",
        "难过",
        "伤心",
        "😭",
        "好难",
        "想死",
        "心碎",
        "失落",
    ],
    "撒娇": [
        "不要嘛",
        "哼",
        "讨厌",
        "人家",
        "～",
        "嘛",
        "呜呜呜",
        "好不好嘛",
        "求求",
        "拜托拜托",
    ],
    "认真": [
        "说真的",
        "认真说",
        "从技术",
        "严格来说",
        "其实",
        "客观来说",
        "理性分析",
        "有一说一",
        "的来说",
        "理论上",
    ],
    "好奇": [
        "是什么",
        "怎么做到",
        "为什么",
        "啥意思",
        "什么意思",
        "如何",
        "谁知道",
        "有人知道",
        "求教",
        "请教",
        "有没有人",
        "怎么弄",
    ],
    "困惑": [
        "不明白",
        "不懂",
        "啥呀",
        "？？？",
        "？？",
        "迷了",
        "迷糊",
        "怎么回事",
        "看不懂",
        "想不通",
        "🤔",
        "这啥",
    ],
    "恐惧": [
        "好可怕",
        "吓死",
        "害怕",
        "不敢",
        "恐怖",
        "吓人",
        "吓",
        "慎入",
        "胆小",
        "😱",
        "慎点",
    ],
    "嫌弃": [
        "好恶心",
        "别烦我",
        "想吐",
        "🤮",
        "恶心",
        "别来沾边",
        "走开",
        "脏了",
        "晦气",
        "退退退",
        "别靠近",
    ],
    "得意": [
        "看我多强",
        "这就是实力",
        "大佬",
        "膜拜",
        "🫡",
        "不愧是我",
        "拿捏",
        "轻轻松松",
        "基操",
        "有手就行",
    ],
    "尴尬": [
        "好尴尬",
        "社死",
        "😅",
        "尴尬",
        "脚趾抠地",
        "不好意思",
        "打扰了",
        "当我没说",
        "当我放屁",
        "地缝",
    ],
    "期待": [
        "好期待",
        "等不及",
        "快点",
        "快出",
        "愿望",
        "许愿",
        "盼望",
        "gkd",
        "搞快点",
        "期待住了",
        "想看到",
    ],
}

_ALL_EMOTIONS = list(EMOTION_KEYWORDS.keys())


def normalize_emotion(emotion: str) -> str:
    """将 LLM 自由生成的情绪归一化到 16 个基础类别。
    优先精确匹配，否则子串匹配，最后回退 neutral。"""
    if not emotion:
        return "neutral"
    emotion = emotion.strip()
    # 精确匹配
    if emotion in _ALL_EMOTIONS:
        return emotion
    # 取"惊讶中带着兴奋"的主情绪
    lower = emotion.lower()
    for base in _ALL_EMOTIONS:
        if base in emotion or base.lower() in lower:
            return base
    return "neutral"


def detect_emotion(text: str) -> str:
    if not text:
        return "neutral"
    text_lower = text.lower()
    best_emotion = "neutral"
    best_score = 0
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                score += 1
            if kw in text:
                score += 1
        if score > best_score:
            best_score = score
            best_emotion = emotion
    return best_emotion


def calculate_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def weighted_sample(items: list[dict], k: int, weight_key: str = "count") -> list[dict]:
    if not items or k <= 0:
        return []
    if len(items) <= k:
        return list(items)
    cp = list(items)
    weights = [_calc_weights(cp, weight_key)]
    selected = []
    for _ in range(min(k, len(cp))):
        w = _calc_weights(cp, weight_key)
        total = sum(w)
        if total <= 0:
            idx = random.randrange(len(cp))
            selected.append(cp.pop(idx))
            continue
        threshold = random.uniform(0, total)
        cum = 0.0
        for idx, weight in enumerate(w):
            cum += weight
            if threshold <= cum:
                selected.append(cp.pop(idx))
                break
    return selected


def _calc_weights(items: list[dict], weight_key: str) -> list[float]:
    counts = []
    for item in items:
        c = item.get(weight_key, 1)
        try:
            counts.append(max(float(c), 0.0))
        except (TypeError, ValueError):
            counts.append(1.0)
    if not counts:
        return []
    mn, mx = min(counts), max(counts)
    if mx == mn:
        return [1.0] * len(counts)
    return [1.0 + (v - mn) / (mx - mn) * 4.0 for v in counts]


def filter_text(raw: str) -> str:
    if not raw:
        return ""
    raw = re.sub(r"\[回复.*?\]，说：\s*", "", raw)
    raw = re.sub(r"@<[^>]*>", "", raw)
    raw = re.sub(r"\[picid:[^\]]*\]", "", raw)
    raw = re.sub(r"\[表情包：[^\]]*\]", "", raw)
    return raw.strip()


def parse_expression_response(text: str) -> tuple[list[dict], list[dict]]:
    raw = text.strip()
    json_block = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if json_block:
        raw = json_block.group(1).strip()
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return [], []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [], []
    if isinstance(parsed, dict):
        parsed = [parsed]
    expressions = []
    jargons = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if item.get("situation") and item.get("style"):
            expressions.append(
                {
                    "situation": str(item["situation"]).strip(),
                    "style": str(item["style"]).strip(),
                    "emotion": normalize_emotion(str(item.get("emotion", "neutral"))),
                    "source_id": str(item.get("source_id", "")).strip(),
                }
            )
        elif item.get("content"):
            jargons.append(
                {
                    "content": str(item["content"]).strip(),
                    "source_id": str(item.get("source_id", "")).strip(),
                }
            )
    return expressions, jargons


def build_style_hint(expressions: list[dict], jargons: list[dict], emotion: str) -> str:
    parts = []
    if expressions:
        parts.append("==== 表达风格参考 ====")
        parts.append(f"情绪: {emotion}")
        for expr in expressions:
            parts.append(f"- {expr['situation']} → {expr['style']}")
        parts.append("")
    if jargons:
        parts.append("==== 黑话解释 ====")
        for j in jargons:
            parts.append(f"- {j['content']}: {j.get('meaning', '含义未知')}")
        parts.append("")
    return "\n".join(parts).strip()


def build_context_paragraph(messages: list[dict], center_index: int) -> str | None:
    """构建包含中心消息上下文的段落（前3条+后3条），返回格式化文本"""
    if not messages or center_index < 0 or center_index >= len(messages):
        return None
    context_start = max(0, center_index - 3)
    context_end = min(len(messages), center_index + 1 + 3)
    context_msgs = messages[context_start:context_end]
    if not context_msgs:
        return None
    lines = []
    for i, msg in enumerate(context_msgs):
        actual_idx = context_start + i
        sender = msg.get("sender_name", "") or msg.get("role", "")
        text = filter_text(msg.get("text", ""))
        if not text:
            continue
        marker = " *" if actual_idx == center_index else ""
        lines.append(f"[{actual_idx + 1}]{marker} {sender}: {text}")
    return "\n".join(lines) if lines else None
