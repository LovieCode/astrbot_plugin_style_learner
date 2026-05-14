import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.star.filter.event_message_type import EventMessageType

from .expression_reflector import ExpressionReflector
from .jargon_explainer import JargonExplainer
from .jargon_miner import JargonMiner
from .learner import ExpressionLearner
from .models import get_db
from .recorder import MessageRecorder
from .selector import ExpressionSelector
from .utils import filter_text
from .auto_check import ExpressionAutoCheckTask


@register(
    "astrbot_plugin_style_learner",
    "AstrBot Community",
    "从群聊中学习表达方式与黑话，按情绪分类注入回复风格。",
    "v1.0.0",
    "",
)
class StyleLearnerPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.context = context
        self.config = config or {}
        self.recorder: MessageRecorder | None = None
        self.selector: ExpressionSelector | None = None
        self.learner: ExpressionLearner | None = None
        self.miner: JargonMiner | None = None
        self.explainer: JargonExplainer | None = None
        self.reflector: ExpressionReflector | None = None
        self.auto_check: ExpressionAutoCheckTask | None = None
        self._bot_name = "Bot"
        self._cron_registered = False
        self._reflector_cron_registered = False
        self._cron_jobs: list[str] = []

    async def initialize(self):
        logger.info("StyleLearner: initializing...")
        cfg = await self._get_config()
        self._bot_name = cfg.get("bot_name", "").strip() or self._bot_name
        # 如果未手动配置，尝试从平台获取 display_name 作为回退
        if self._bot_name == "Bot":
            try:
                platform = self.context.get_using_platform()
                if platform:
                    meta = platform.meta()
                    if meta and meta.adapter_display_name:
                        self._bot_name = meta.adapter_display_name
            except Exception:
                pass
        learner_llm = self._make_llm_caller("learn", cfg)
        selection_llm = self._make_llm_caller("selection", cfg)
        check_llm = self._make_llm_caller("check", cfg)
        infer_llm = self._make_llm_caller("infer", cfg)
        self.selector = ExpressionSelector(selection_llm)
        self.learner = ExpressionLearner(learner_llm)
        self.miner = JargonMiner(learner_llm)
        self.explainer = JargonExplainer(
            infer_llm or learner_llm, global_jargon=cfg.get("all_global_jargon", False)
        )
        self.reflector = ExpressionReflector(check_llm or learner_llm)
        # 自动检查任务
        auto_check_enabled = cfg.get("expression_auto_check_enabled", True)
        auto_check_interval = cfg.get("expression_auto_check_interval", 300)
        auto_check_count = cfg.get("expression_auto_check_count", 5)
        self.auto_check = ExpressionAutoCheckTask(
            check_llm or learner_llm,
            check_interval=auto_check_interval,
            check_count=auto_check_count,
            enabled=auto_check_enabled,
        )
        self.auto_check.start()
        # 设置跨群共享
        groups = cfg.get("expression_groups", [])
        if groups and isinstance(groups, list):
            self.selector.set_expression_groups(groups)
        global_exprs = cfg.get("all_global_expressions", False)
        self.selector.set_global_expressions(global_exprs)
        operator_chat = cfg.get("operator_chat_id", "")
        if operator_chat:
            self.reflector.set_operator(operator_chat)
        min_msgs = cfg.get("min_messages_for_learning", 30)
        min_int = cfg.get("learning_interval_minutes", 60) * 60
        self.recorder = MessageRecorder(
            min_messages=min_msgs, min_interval=min_int, db=get_db()
        )
        self.recorder.on_learning_ready(self._on_learning_ready)
        # 根据注入模式开关 LLM 工具
        injection_mode = cfg.get("injection_mode", "append")
        if injection_mode == "append":
            try:
                self.context.deactivate_llm_tool("get_conversation_style")
                self.context.deactivate_llm_tool("get_jargon_meaning")
                logger.info(
                    "StyleLearner: injection_mode=append, deactivated LLM tools"
                )
            except Exception as e:
                logger.warning(f"StyleLearner: failed to deactivate tools: {e}")

        await self._register_cron()
        await self._register_reflector_cron()
        await self._register_web_apis()
        # 修复已存在的配置中 expression_groups 类型错误（string → list）
        if isinstance(self.config, dict) and isinstance(
            self.config.get("expression_groups"), str
        ):
            try:
                self.config["expression_groups"] = json.loads(
                    self.config["expression_groups"]
                )
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
                logger.info("StyleLearner: fixed expression_groups type in config")
            except Exception:
                self.config["expression_groups"] = []
        logger.info("StyleLearner: initialized successfully")

    async def _get_config(self) -> dict:
        defaults = {
            "enable_expression_learning": True,
            "enable_jargon_mining": True,
            "injection_mode": "append",
            "selection_mode": "classic",
            "min_messages_for_learning": 30,
            "learning_interval_minutes": 60,
            "expression_checked_only": False,
            "all_global_jargon": False,
            "all_global_expressions": False,
            "expression_groups": [],
            "expression_auto_check_enabled": True,
            "expression_auto_check_interval": 300,
            "expression_auto_check_count": 5,
            "llm_model_override": "",
            "learner_model_override": "",
            "selection_model_override": "",
            "check_model_override": "",
            "infer_model_override": "",
            "operator_chat_id": "",
            "bot_name": "",
        }
        if isinstance(self.config, dict) and self.config:
            result = {**defaults, **self.config}
        else:
            result = defaults
        if isinstance(result.get("expression_groups"), str):
            try:
                result["expression_groups"] = json.loads(result["expression_groups"])
            except (json.JSONDecodeError, TypeError):
                result["expression_groups"] = []
        if not isinstance(result.get("expression_groups"), list):
            result["expression_groups"] = []
        return result

    def _make_llm_caller(self, task: str = "", cfg: dict | None = None):
        """创建 LLM caller，返回的 call_llm(prompt) 可能返回以 'ERROR:' 开头的错误信息"""
        cfg = cfg or {}
        model_override = ""
        if task == "learn":
            model_override = cfg.get("learner_model_override", "") or cfg.get(
                "llm_model_override", ""
            )
        elif task == "selection":
            model_override = cfg.get("selection_model_override", "") or cfg.get(
                "llm_model_override", ""
            )
        elif task == "check":
            model_override = cfg.get("check_model_override", "") or cfg.get(
                "llm_model_override", ""
            )
        elif task == "infer":
            model_override = cfg.get("infer_model_override", "") or cfg.get(
                "llm_model_override", ""
            )
        else:
            model_override = cfg.get("llm_model_override", "")

        async def call_llm(prompt: str, system_prompt: str = "") -> str | None:
            logger.info(
                f"StyleLearner LLM caller ({task}): attempting to get provider..."
            )
            provider = self.context.get_using_provider()
            if model_override:
                try:
                    override = self.context.get_provider_by_id(model_override)
                    if override:
                        provider = override
                        logger.info(
                            f"StyleLearner LLM caller ({task}): using overridden provider {model_override}"
                        )
                except Exception as e:
                    logger.error(
                        f"StyleLearner LLM caller ({task}): get_provider_by_id failed: {e}"
                    )
            if not provider:
                providers = self.context.get_all_providers()
                if not providers:
                    msg = "ERROR: 没有找到任何 LLM Provider，请在 AstrBot 中至少配置一个模型"
                    logger.error(f"StyleLearner LLM caller ({task}): {msg}")
                    return msg
                provider = providers[0]
                logger.info(
                    f"StyleLearner LLM caller ({task}): fallback to first provider"
                )
            try:
                logger.info(f"StyleLearner LLM caller ({task}): calling LLM...")
                messages = [{"role": "user", "content": prompt}]
                resp = await provider.text_chat(
                    system_prompt=system_prompt
                    or "你是一个有用的助手。请严格按要求的格式输出。",
                    contexts=messages,
                )
                logger.info(f"StyleLearner LLM caller ({task}): LLM response received")
                if isinstance(resp, tuple) and len(resp) > 0:
                    resp = resp[0]
                if hasattr(resp, "completion_text"):
                    return resp.completion_text
                if isinstance(resp, str):
                    return resp
                return str(resp)
            except Exception as e:
                msg = f"ERROR: LLM 调用异常 - {e}"
                logger.error(f"StyleLearner LLM caller ({task}): {e}")
                return msg

        return call_llm

    async def _register_cron(self):
        if self._cron_registered:
            return
        try:
            cron = self.context.cron_manager
            if cron is None:
                logger.warning("Cron manager unavailable, will try again later")
                return
            job = await cron.add_basic_job(
                name="style_learner_tick",
                cron_expression="*/30 * * * *",
                handler=self._on_tick,
                description="定期检查并触发表达风格学习",
                persistent=False,
                enabled=True,
            )
            self._cron_jobs.append(job.job_id)
            self._cron_registered = True
            logger.info("StyleLearner: cron job registered")
        except Exception as e:
            logger.warning(
                f"StyleLearner: cron registration failed (non-critical): {e}"
            )

    async def _register_reflector_cron(self):
        if self._reflector_cron_registered or not self.reflector:
            return
        try:
            cron = self.context.cron_manager
            if cron is None:
                return
            job = await cron.add_basic_job(
                name="style_learner_reflector",
                cron_expression="*/5 * * * *",
                handler=self._on_reflector_tick,
                description="定期向管理员提问审核表达方式",
                persistent=False,
                enabled=True,
            )
            self._cron_jobs.append(job.job_id)
            self._reflector_cron_registered = True
            logger.info("StyleLearner: reflector cron registered")
        except Exception as e:
            logger.warning(f"StyleLearner: reflector cron registration failed: {e}")

    async def _on_tick(self):
        if not self.recorder:
            return
        for chat_id in self.recorder.get_pending_chat_ids():
            messages = self.recorder.force_trigger(chat_id)
            if messages:
                await self._run_learning(chat_id, messages)

    async def _on_reflector_tick(self):
        if not self.reflector:
            return
        try:
            ask_text = await self.reflector.ask_if_needed()
            if ask_text and self.reflector._operator_chat_id:
                await self._send_admin_message(ask_text)
        except Exception as e:
            logger.error(f"Reflector tick error: {e}")

    async def _send_admin_message(self, text: str):
        """向管理员发送私聊消息"""
        try:
            platform = self.context.get_using_platform()
            if not platform:
                return
            from astrbot.core.platform.message_session import MessageSession

            target = MessageSession.from_umo(self.reflector._operator_chat_id)
            if target:
                platform.send_message(target, text)
        except Exception as e:
            logger.warning(f"Failed to send admin message: {e}")

    def _on_learning_ready(self, chat_id: str, messages: list[dict]):
        import asyncio

        asyncio.create_task(self._run_learning(chat_id, messages))

    async def _run_learning(self, chat_id: str, messages: list[dict]) -> list[dict]:
        """执行学习，返回本次学到的新条目列表"""
        cfg = await self._get_config()
        enabled = cfg.get("enable_expression_learning", True)
        if not enabled or not self.learner:
            logger.warning(
                f"StyleLearner: learning skipped, enabled={enabled}, learner={self.learner is not None}"
            )
            return []
        enable_jargon = cfg.get("enable_jargon_mining", True)
        items = await self.learner.learn_and_store(
            messages, chat_id, self._bot_name, enable_jargon
        )
        logger.info(
            f"StyleLearner: learning done for {chat_id}, got {len(items)} items"
        )
        return items

    # ── Main hooks ──

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin or ""
        user_text = event.message_str or ""
        if not user_text.strip():
            return
        if not self.recorder:
            return
        sender_name = event.get_sender_name() or ""
        # 缓存 chat 名称映射，优先群名，次取发送者名，最后用 ID 本身
        chat_name = ""
        try:
            group = await event.get_group()
            chat_name = (
                group.group_name if group and getattr(group, "group_name", "") else ""
            )
        except Exception:
            pass
        if not chat_name:
            chat_name = sender_name or umo.split(":")[-1] if umo else ""
        if chat_name and chat_name != umo:
            get_db().cache_chat_name(umo, chat_name)
        self.recorder.record(umo, "user", user_text, sender_name=sender_name)
        # 处理管理员审核回复
        if self.reflector and self.reflector._operator_chat_id:
            if umo == self.reflector._operator_chat_id:
                result = self.reflector.on_admin_response(user_text)
                if result:
                    expr_id, approved, _ = result
                    status = "通过" if approved else "拒绝"
                    yield event.plain_result(f"已{status}表达 #{expr_id}，谢谢反馈！")
                    return

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        umo = event.unified_msg_origin or ""
        user_text = event.message_str or ""
        if not user_text.strip():
            return
        chat_id = umo
        cfg = await self._get_config()
        injection_mode = cfg.get("injection_mode", "append")
        checked_only = cfg.get("expression_checked_only", False)
        selection_mode = cfg.get("selection_mode", "classic")
        if not self.selector or not self.explainer:
            logger.warning(
                "StyleLearner on_llm_request: selector or explainer not initialized"
            )
            return
        if injection_mode not in ("append", "both"):
            logger.info(
                f"StyleLearner on_llm_request: injection_mode={injection_mode}, skipping"
            )
            return
        # 匹配黑话
        jargon_list = self.explainer.match_from_text(user_text, chat_id)[:5]
        # 获取聊天上下文（最近消息）供 classic 模式分析
        chat_observe_info = ""
        style_instruction = (
            "- 请不要输出多余内容(包括不必要的前后缀，冒号，括号，表情包，at或 @等)，只输出发言内容就好\n"
            "- 给出日常且口语化的回复，尽量简短一些\n"
            "- 不要回复的太有条理\n"
            "- 最好一次对一个话题进行回复"
        )
        req.extra_user_content_parts.append(TextPart(text=style_instruction))
        hint = await self.selector.build_hint(
            chat_id=chat_id,
            user_text=user_text,
            jargons=jargon_list,
            mode=selection_mode,
            checked_only=checked_only,
            bot_name=self._bot_name,
            chat_observe_info=chat_observe_info,
        )
        if hint:
            req.extra_user_content_parts.append(TextPart(text=hint))
            logger.info(
                f"StyleLearner on_llm_request: injected hint ({len(hint)} chars) for {chat_id}"
            )
        else:
            # 检查 DB 中是否有数据可供诊断
            db = get_db()
            expr_count = db.conn.execute(
                "SELECT COUNT(*) as cnt FROM expressions WHERE (rejected=0 OR rejected IS NULL)"
            ).fetchone()["cnt"]
            jargon_count = db.conn.execute(
                "SELECT COUNT(*) as cnt FROM jargons"
            ).fetchone()["cnt"]
            logger.info(
                f"StyleLearner on_llm_request: no hint for {chat_id} "
                f"(DB: {expr_count} expressions, {jargon_count} jargons, "
                f"injection_mode={injection_mode}, selection_mode={selection_mode})"
            )

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, response):
        umo = event.unified_msg_origin or ""
        if not self.recorder:
            return
        text = ""
        if hasattr(response, "completion_text"):
            text = response.completion_text or ""
        elif isinstance(response, str):
            text = response
        if text.strip():
            self.recorder.record(
                umo, "assistant", text.strip(), sender_name=self._bot_name
            )

    # ── Commands ──

    @filter.command("style")
    async def style_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(
            "🎭 表达风格学习插件\n"
            "用法：\n"
            "/style list [情绪] - 查看表达列表\n"
            "/style stats - 查看学习统计"
        )

    @filter.command("style", sub_command="list")
    async def style_list(self, event: AstrMessageEvent, emotion: str = "all"):
        chat_id = event.unified_msg_origin or ""
        db = get_db()
        exprs, total = db.get_expressions(
            chat_id=chat_id,
            emotion=emotion if emotion != "all" else None,
            page=1,
            page_size=10,
        )
        if not exprs:
            yield event.plain_result("暂无表达数据。")
            return
        lines = [f"📝 表达列表（共{total}条，情绪:{emotion}）", ""]
        for e in exprs[:10]:
            lines.append(
                f"[{e.get('emotion', '?')}] {e['situation']} → {e['style']} (次数:{e['count']})"
            )
        yield event.plain_result("\n".join(lines))

    @filter.command("style", sub_command="stats")
    async def style_stats(self, event: AstrMessageEvent):
        db = get_db()
        stats = db.get_statistics()
        lines = [
            "📊 学习统计",
            f"表达方式: {stats['total_expressions']} 条",
            f"  已审核: {stats['checked_expressions']} 条",
            f"  已拒绝: {stats['rejected_expressions']} 条",
            f"黑话: {stats['total_jargons']} 条 (有含义: {stats['jargons_with_meaning']})",
            f"群组数: {stats['chat_group_count']}",
            "",
            "📈 情绪分布:",
        ]
        for em, cnt in stats.get("emotion_distribution", {}).items():
            bar = "█" * min(cnt, 20)
            lines.append(f"  {em}: {bar} {cnt}")
        yield event.plain_result("\n".join(lines))

    # ── LLM Tools ──

    @filter.llm_tool(name="get_conversation_style")
    async def tool_get_style(self, event: AstrMessageEvent, emotion: str = ""):
        """获取当前群聊适合的表达风格参考。

        Args:
            emotion(string): 情绪分类（开心/惊讶/无奈/嘲讽/鼓励/生气/悲伤/撒娇/认真/neutral），为空时自动检测
        """
        chat_id = event.unified_msg_origin or ""
        if not emotion:
            emotion = "neutral"
        db = get_db()
        exprs = db.get_expressions_by_emotion(chat_id, emotion, 5)
        if not exprs:
            return "暂无表达风格数据。"
        lines = [f"当前对话适合的风格（情绪: {emotion}）："]
        for e in exprs:
            lines.append(f"- {e['situation']} → {e['style']}")
        return "\n".join(lines)

    @filter.llm_tool(name="get_jargon_meaning")
    async def tool_get_jargon(self, event: AstrMessageEvent, text: str = ""):
        """获取文本中黑话的含义解释。

        Args:
            text(string): 要分析的文本
        """
        if not text:
            return "请提供要分析的文本。"
        chat_id = event.unified_msg_origin or ""
        if not self.explainer:
            return ""
        matched = self.explainer.match_from_text(text, chat_id)
        if not matched:
            return "未在文本中发现已知黑话。"
        lines = ["识别到以下黑话："]
        for m in matched:
            lines.append(f"- {m['content']}: {m.get('meaning', '含义待确认')}")
        return "\n".join(lines)

    # ── WebUI API ──

    async def _register_web_apis(self):
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/expressions",
            self._api_get_expressions,
            ["GET"],
            "获取表达列表",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>",
            self._api_get_expression,
            ["GET"],
            "获取单个表达",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>/check",
            self._api_check_expression,
            ["POST"],
            "审核表达",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>",
            self._api_delete_expression,
            ["POST"],
            "删除表达",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>/edit",
            self._api_edit_expression,
            ["POST"],
            "编辑表达",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/jargons",
            self._api_get_jargons,
            ["GET"],
            "获取黑话列表",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>/meaning",
            self._api_update_jargon_meaning,
            ["POST"],
            "编辑黑话含义",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>",
            self._api_delete_jargon,
            ["POST"],
            "删除黑话",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>/check",
            self._api_check_jargon,
            ["POST"],
            "审核黑话",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/statistics",
            self._api_statistics,
            ["GET"],
            "获取学习统计",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/trigger-learn",
            self._api_trigger_learn,
            ["POST"],
            "手动触发学习",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/chat-groups",
            self._api_chat_groups,
            ["GET"],
            "获取群列表",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/known-chats",
            self._api_known_chats,
            ["GET"],
            "获取已知会话列表（含名称），用于配置下拉选择",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/settings",
            self._api_get_settings,
            ["GET"],
            "获取配置",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/settings",
            self._api_update_settings,
            ["POST"],
            "更新配置",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/pending-messages",
            self._api_pending_messages,
            ["GET"],
            "获取待学习消息",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/prompts",
            self._api_get_prompts,
            ["GET"],
            "获取所有 Prompt 模板",
        )
        self.context.register_web_api(
            "/astrbot_plugin_style_learner/prompts",
            self._api_save_prompts,
            ["POST"],
            "保存 Prompt 模板",
        )

    async def _api_get_expressions(self, *args, **kwargs):
        from quart import request as quart_request

        chat_id = quart_request.args.get("chat_id", "")
        emotion = quart_request.args.get("emotion", "")
        status = quart_request.args.get("status", "")
        page = int(quart_request.args.get("page", 1))
        page_size = int(quart_request.args.get("page_size", 20))
        db = get_db()
        exprs, total = db.get_expressions(
            chat_id=chat_id if chat_id else None,
            emotion=emotion if emotion and emotion != "all" else None,
            status=status,
            page=page,
            page_size=page_size,
        )
        chat_ids = list({e.get("chat_id", "") for e in exprs})
        name_map = db.get_chat_name_map(chat_ids)
        for e in exprs:
            e["_chat_name"] = name_map.get(e.get("chat_id", ""), "")
        return {"success": True, "data": exprs, "total": total}

    async def _api_get_expression(self, expr_id: int, *args, **kwargs):
        """获取单条表达方式的详细信息"""
        db = get_db()
        expr = db.get_expression_by_id(expr_id)
        if expr is None:
            return {"success": False, "message": "表达方式不存在"}
        return {"success": True, "data": expr}

    async def _api_check_expression(self, expr_id: int, *args, **kwargs):
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        checked = body.get("checked", True)
        rejected = body.get("rejected", False)
        db = get_db()
        db.check_expression(expr_id, checked, rejected)
        return {"success": True}

    async def _api_delete_expression(self, expr_id: int, *args, **kwargs):
        db = get_db()
        db.delete_expression(expr_id)
        return {"success": True}

    async def _api_edit_expression(self, expr_id: int, *args, **kwargs):
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        db = get_db()
        db.update_expression(
            expr_id,
            **{k: v for k, v in body.items() if k in ("emotion", "situation", "style")},
        )
        return {"success": True}

    async def _api_get_jargons(self, *args, **kwargs):
        from quart import request as quart_request

        chat_id = quart_request.args.get("chat_id", "")
        page = int(quart_request.args.get("page", 1))
        page_size = int(quart_request.args.get("page_size", 20))
        db = get_db()
        jargons, total = db.get_jargons(
            chat_id=chat_id if chat_id else None,
            page=page,
            page_size=page_size,
        )
        chat_ids = list({j.get("chat_id", "") for j in jargons})
        name_map = db.get_chat_name_map(chat_ids)
        for j in jargons:
            j["_chat_name"] = name_map.get(j.get("chat_id", ""), "")
        return {"success": True, "data": jargons, "total": total}

    async def _api_update_jargon_meaning(self, jargon_id: int, *args, **kwargs):
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        meaning = body.get("meaning", "")
        db = get_db()
        db.update_jargon_meaning(jargon_id, meaning, is_jargon=True)
        return {"success": True}

    async def _api_check_jargon(self, jargon_id: int, *args, **kwargs):
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        rejected = body.get("rejected", False)
        db = get_db()
        db.conn.execute(
            "UPDATE jargons SET rejected=? WHERE id=?",
            (1 if rejected else 0, jargon_id),
        )
        db.conn.commit()
        return {"success": True}

    async def _api_delete_jargon(self, jargon_id: int, *args, **kwargs):
        db = get_db()
        db.delete_jargon(jargon_id)
        return {"success": True}

    async def _api_statistics(self, *args, **kwargs):
        db = get_db()
        return {"success": True, "data": db.get_statistics()}

    async def _api_trigger_learn(self, *args, **kwargs):
        if not self.recorder:
            return {"success": False, "message": "插件未初始化"}
        db = get_db()
        results = []
        for chat_id in self.recorder.get_all_chat_ids():
            messages = self.recorder.get_buffered_messages(chat_id)
            if not messages:
                continue
            chat_name = db.get_chat_name(chat_id) or chat_id
            logger.info(
                f"StyleLearner: manually triggering learning for {chat_id} ({chat_name}), {len(messages)} messages"
            )
            try:
                items = await self._run_learning(chat_id, list(messages))
            except Exception as e:
                logger.error(f"StyleLearner: learning failed for {chat_id}: {e}")
                results.append(
                    {
                        "chat_id": chat_id,
                        "_chat_name": chat_name,
                        "message_count": len(messages),
                        "items": [],
                        "error": str(e),
                    }
                )
                continue
            if items:
                self.recorder.clear_buffer(chat_id)
            results.append(
                {
                    "chat_id": chat_id,
                    "_chat_name": chat_name,
                    "message_count": len(messages),
                    "items": items,
                }
            )
        if not results:
            return {"success": True, "message": "没有待学习的消息"}
        total_items = sum(len(r["items"]) for r in results)
        return {
            "success": True,
            "data": results,
            "message": f"完成 {len(results)} 个群的学习，共学到 {total_items} 条",
        }

    async def _api_pending_messages(self, *args, **kwargs):
        from quart import request as quart_request

        chat_id = quart_request.args.get("chat_id", "")
        if not self.recorder:
            return {"success": True, "data": []}
        if chat_id:
            msgs = self.recorder.get_buffered_messages(chat_id)
            return {"success": True, "data": msgs, "total": len(msgs)}
        summary = self.recorder.get_all_buffered_summary()
        return {"success": True, "data": summary}

    async def _api_chat_groups(self, *args, **kwargs):
        db = get_db()
        chat_ids = db.get_chat_groups()
        name_map = db.get_chat_name_map(chat_ids)
        data = []
        for cid in chat_ids:
            name = name_map.get(cid, "")
            data.append({"chat_id": cid, "_chat_name": name})
        return {"success": True, "data": data}

    async def _api_known_chats(self, *args, **kwargs):
        db = get_db()
        chats = db.get_known_chats()
        return {"success": True, "data": chats}

    async def _api_get_settings(self, *args, **kwargs):
        cfg = await self._get_config()
        return {"success": True, "data": cfg}

    async def _api_update_settings(self, *args, **kwargs):
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
        if "expression_groups" in body:
            val = body["expression_groups"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    val = []
            if not isinstance(val, list):
                val = []
            body["expression_groups"] = val
        try:
            self.config.update(body)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
        return {"success": False, "message": "保存配置失败"}

    async def _api_get_prompts(self, *args, **kwargs):
        from .prompt_manager import get_all_prompts

        return {"success": True, "data": get_all_prompts()}

    async def _api_save_prompts(self, *args, **kwargs):
        from quart import request as quart_request
        from .prompt_manager import set_prompt, reset_prompt

        body = await quart_request.get_json(silent=True) or {}
        key = body.get("key", "")
        value = body.get("value")
        if not key:
            return {"success": False, "message": "缺少 key 参数"}
        if value is None or (isinstance(value, str) and not value.strip()):
            reset_prompt(key)
            return {"success": True, "message": f"Prompt '{key}' 已重置为默认值"}
        set_prompt(key, value)
        return {"success": True, "message": f"Prompt '{key}' 已保存"}

    async def terminate(self):
        logger.info("StyleLearner: terminating...")
        if self.auto_check:
            self.auto_check.stop()
        cron = getattr(self.context, "cron_manager", None)
        if cron:
            for job_id in self._cron_jobs:
                try:
                    await cron.delete_job(job_id)
                except Exception as e:
                    logger.warning(
                        f"StyleLearner: failed to delete cron job {job_id}: {e}"
                    )
        self._cron_jobs.clear()
