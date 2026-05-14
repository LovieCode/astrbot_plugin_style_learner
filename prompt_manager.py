"""Prompt 管理器：统一管理所有 LLM Prompt 模板，支持用户自定义覆盖"""

from .models import get_db

_DEFAULT_PROMPTS = {
    "learn": """{chat_str}
你的名字是{bot_name},现在请你完成两个提取任务
任务1：请从上面这段群聊中用户的语言风格和说话方式
1. 只考虑文字，不要考虑表情包和图片
2. 不要总结SELF的发言，因为这是你自己的发言，不要重复学习你自己的发言
3. 不要涉及具体的人名，也不要涉及具体名词
4. 思考有没有特殊的梗，一并总结成语言风格
5. 例子仅供参考，请严格根据群聊内容总结!!!
注意：总结成如下格式的规律，总结的内容要详细，但具有概括性：
例如：当"AAAAA"时，可以"BBBBB", AAAAA代表某个场景，不超过20个字。BBBBB代表对应的语言风格，特定句式或表达方式，不超过20个字。
表达方式在3-5个左右，不要超过10个。

每条表达方式必须标注一个 emotion 情绪标签，只能从以下 16 个词中选择一个：
开心、惊讶、无奈、嘲讽、鼓励、生气、悲伤、撒娇、认真、好奇、困惑、恐惧、嫌弃、得意、尴尬、期待

任务2：请从上面这段聊天内容中提取"可能是黑话"的候选项（黑话/俚语/网络缩写/口头禅）。
- 必须为对话中真实出现过的短词或短语
- 必须是你无法理解含义的词语，没有明确含义的词语，请不要选择有明确含义，或者含义清晰的词语
- 排除：人名、@、表情包/图片中的内容、纯标点、常规功能词（如的、了、呢、啊等）
- 每个词条长度建议 2-8 个字符（不强制），尽量短小

黑话必须为以下几种类型：
- 由字母构成的，汉语拼音首字母的简写词，例如：nb、yyds、xswl
- 英文词语的缩写，用英文字母概括一个词汇或含义，例如：CPU、GPU、API
- 中文词语的缩写，用几个汉字概括一个词汇或含义，例如：社死、内卷

排除以下内容：
- 纯数字或数字组合（如 00、21、123）
- 单字母或字母+数字混合无意义

输出要求：
将表达方式，语言风格和黑话以 JSON 数组输出，每个元素为一个对象，结构如下（注意字段名）：
注意请不要输出重复内容，请对表达方式和黑话进行去重。

[
  {{"situation": "AAAAA", "style": "BBBBB", "emotion": "开心", "source_id": "3"}},
  {{"situation": "CCCC", "style": "DDDD", "emotion": "嘲讽", "source_id": "7"}},
  {{"situation": "对某件事表示十分惊叹", "style": "使用 我嘞个xxxx", "emotion": "惊讶", "source_id": "[消息编号]"}},
  {{"situation": "表示讽刺的赞同，不讲道理", "style": "对对对", "emotion": "嘲讽", "source_id": "[消息编号]"}},
  {{"situation": "当涉及游戏相关时，夸赞，略带戏谑意味", "style": "使用 这么强！", "emotion": "鼓励", "source_id": "[消息编号]"}},
  {{"content": "词条", "source_id": "12", "meaning": ""}},
  {{"content": "词条2", "source_id": "5", "meaning": "永远的神"}}
]

其中：
表达方式条目：
- situation：表示"在什么情境下"的简短概括（不超过20个字）
- style：表示对应的语言风格或常用表达（不超过20个字）
- emotion：该表达方式所传达的情绪，请用简短的自然语言自由描述，不要局限于固定分类。例如：开心、讽刺中带着无奈、假装生气、热情洋溢、冷淡敷衍、阴阳怪气等
- source_id：该表达方式对应的"来源行编号"，即上方聊天记录中方括号里的数字（例如 [3]），请只输出数字本身，不要包含方括号
黑话jargon条目：
- content:表示黑话的内容
- source_id：该黑话对应的"来源行编号"，即上方聊天记录中方括号里的数字（例如 [3]），请只输出数字本身，不要包含方括号
- meaning（可选）：该黑话在对话中明确出现过的释义或解释。仅当上下文中明确有人解释了这个词时填写（例如有人说"YYDS就是永远的神"，则 meaning 填"永远的神"），否则留空字符串""

现在请你输出 JSON：
""",

    "selection": """{chat_observe_info}

你的名字是{bot_name}{target_message}
{reply_reason_block}

以下是可选的表达情境：
{all_situations}

请你分析聊天内容的语境、情绪、话题类型，从上述情境中选择最适合当前聊天情境的，最多{max_num}个情境。
考虑因素包括：
1.聊天的情绪氛围（轻松、严肃、幽默等）
2.话题类型（日常、技术、游戏、情感等）
3.情境与当前语境的匹配度
{target_message_extra_block}

请以JSON格式输出，只需要输出选中的情境编号：
例如：
{{
    "selected_situations": [2, 3, 5, 7, 19]
}}

请严格按照JSON格式输出，不要包含其他内容：
""",

    "inference": """词条内容: {content}

该词条出现的上下文:
{contexts}

请推断"{content}"的含义。
- 如果是黑话/俚语/网络缩写，请解释其含义
- 如果是常规词汇，也请说明
- 如果信息不足无法推断，请设置 "no_info": true

以 JSON 格式输出:
{{
  "meaning": "含义说明",
  "no_info": false
}}
""",

    "compare": """推断结果1（基于上下文）:
{inference1}

推断结果2（仅基于词条本身）:
{inference2}

请比较两个推断结果是否相同或类似。
- 如果含义相同或类似，说明这不是黑话（含义明确）
- 如果含义有差异，说明可能是黑话（需要上下文才能理解）

以 JSON 格式输出:
{{
  "is_similar": true,
  "reason": "判断理由"
}}
""",

    "check": """请评估以下表达方式或语言风格以及使用条件或使用情景是否合适：
使用条件或使用情景：{situation}
表达方式或言语风格：{style}

请从以下方面进行评估：
1. 表达方式或言语风格是否与使用条件或使用情景匹配
2. 允许部分语法错误或口头化或缺省出现
3. 表达方式不能太过特指，需要具有泛用性
4. 一般不涉及具体的人名或名称

请以JSON格式输出评估结果：
{{
    "suitable": true/false,
    "reason": "评估理由（如果不合适，请说明原因）"
}}
如果合适，suitable设为true；如果不合适，suitable设为false，并在reason中说明原因。
请严格按照JSON格式输出，不要包含其他内容。""",

    "summarize": """聊天内容:
{chat_text}

当前对话中识别到以下黑话:
{explanations}

请将这些黑话解释整理成简洁的一段话，适合作为回复参考。直接输出平文本，不要格式：
""",
}

_PROMPT_META = {
    "learn": {
        "name": "学习 Prompt",
        "description": "从群聊中学习表达方式和黑话",
        "variables": [
            {"name": "{chat_str}", "desc": "匿名化后的群聊记录（格式：A说/B说/SELF说）"},
            {"name": "{bot_name}", "desc": "机器人当前显示名称"},
        ],
    },
    "selection": {
        "name": "选择 Prompt",
        "description": "Classic 模式下 LLM 选择表达情境",
        "variables": [
            {"name": "{chat_observe_info}", "desc": "最近聊天上下文，供 LLM 分析语境"},
            {"name": "{bot_name}", "desc": "机器人当前显示名称"},
            {"name": "{target_message}", "desc": "需要回复的目标消息（初始文案为',现在你想要对这条消息进行回复:'+消息内容）"},
            {"name": "{reply_reason_block}", "desc": "回复理由块（来自 Planner），为空时退用 chat_observe_info"},
            {"name": "{all_situations}", "desc": "候选表达情境列表（编号+当…时使用…）"},
            {"name": "{max_num}", "desc": "最多选择的情境数量"},
            {"name": "{target_message_extra_block}", "desc": "额外考虑项（有目标消息时为'4.考虑你要回复的目标消息'）"},
        ],
    },
    "inference": {
        "name": "黑话推断 Prompt",
        "description": "根据上下文推断黑话含义",
        "variables": [
            {"name": "{content}", "desc": "待推断的黑话词条内容"},
            {"name": "{contexts}", "desc": "该词条出现的上下文（多行原文拼接）"},
        ],
    },
    "compare": {
        "name": "黑话对比 Prompt",
        "description": "比较两个推断结果判断是否为黑话",
        "variables": [
            {"name": "{inference1}", "desc": "基于上下文的推断结果（JSON）"},
            {"name": "{inference2}", "desc": "仅基于词条本身的推断结果（JSON）"},
        ],
    },
    "check": {
        "name": "表达检查 Prompt",
        "description": "评估表达方式是否合适（自动审核）",
        "variables": [
            {"name": "{situation}", "desc": "待评估的表达情境描述"},
            {"name": "{style}", "desc": "待评估的表达风格/句式"},
        ],
    },
    "summarize": {
        "name": "黑话摘要 Prompt",
        "description": "整理黑话解释为简洁的回复参考",
        "variables": [
            {"name": "{chat_text}", "desc": "当前聊天内容（截取前200字）"},
            {"name": "{explanations}", "desc": "已匹配到的黑话解释列表（每行一条）"},
        ],
    },
}


def get_prompt(key: str) -> str:
    """获取指定 Prompt 模板（自定义优先，默认兜底）"""
    db = get_db()
    custom = db.get_setting(f"prompt_{key}")
    if custom and isinstance(custom, str) and custom.strip():
        return custom
    return _DEFAULT_PROMPTS.get(key, "")


def set_prompt(key: str, value: str):
    """保存自定义 Prompt 模板到 settings 表"""
    db = get_db()
    db.set_setting(f"prompt_{key}", value)


def reset_prompt(key: str):
    """重置为默认 Prompt"""
    db = get_db()
    db.set_setting(f"prompt_{key}", "")


def get_all_prompts() -> list[dict]:
    """获取所有 Prompt 列表（含默认值和自定义值、元信息）"""
    db = get_db()
    result = []
    for key in ["learn", "selection", "inference", "compare", "check", "summarize"]:
        meta = _PROMPT_META.get(key, {})
        default = _DEFAULT_PROMPTS.get(key, "")
        custom = db.get_setting(f"prompt_{key}")
        result.append({
            "key": key,
            "name": meta.get("name", key),
            "description": meta.get("description", ""),
            "variables": meta.get("variables", []),
            "default": default,
            "custom": custom if isinstance(custom, str) and custom.strip() else "",
        })
    return result


def get_default_prompt(key: str) -> str:
    """获取默认 Prompt（不读取用户自定义）"""
    return _DEFAULT_PROMPTS.get(key, "")