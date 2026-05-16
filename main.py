import asyncio
import json
import time
from collections import deque

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.star.filter.event_message_type import EventMessageType

from .api import ApiRouter
from .auto_check import ExpressionAutoCheckTask
from .expression_reflector import ExpressionReflector
from .jargon_explainer import JargonExplainer
from .jargon_miner import JargonMiner
from .learner import ExpressionLearner
from .models import get_db
from .prompt_manager import get_prompt
from .recorder import MessageRecorder
from .selector import ExpressionSelector


@register(
    "astrbot_plugin_style_learner",
    "AstrBot Community",
    "从群聊中学习表达方式与黑话，按情绪分类注入回复风格。",
    "v1.1.1",
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
        self._recent_messages: dict[str, deque] = {}
        self._image_captions: dict[str, str] = {}
        self._last_llm_time: dict[str, float] = {}
        self._last_message_ts: dict[str, float] = {}
        self._cron_registered = False
        self._reflector_cron_registered = False
        self._cron_jobs: list[str] = []

    async def initialize(self):
        logger.info("[SL] initializing...")
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
        # 从 recorder DB 中加载已有的缓冲消息到 ring buffer
        bot_label = f"{self._bot_name}（你）"
        for cid, msgs in self.recorder._buffers.items():
            buf = deque(maxlen=200)
            for m in msgs:
                sender = m.get("sender_name", m.get("role", "?"))
                if m.get("role") == "assistant":
                    sender = bot_label
                raw_images = m.get("images", [])
                images = []
                for img in raw_images:
                    if isinstance(img, str):
                        images.append({
                            "url": img,
                            "caption": self._image_captions.get(img, None),
                        })
                    elif isinstance(img, dict):
                        img_url = img.get("url", "")
                        if img_url and img_url in self._image_captions:
                            img["caption"] = self._image_captions[img_url]
                        images.append(img)
                buf.append({
                    "role": m.get("role", "user"),
                    "sender": sender,
                    "text": m.get("text", ""),
                    "images": images,
                })
            self._recent_messages[cid] = buf
        if self._recent_messages:
            total = sum(len(v) for v in self._recent_messages.values())
            logger.info(f"[SL] seeded recent messages | chats={len(self._recent_messages)} msgs={total}")
        self.recorder.on_learning_ready(self._on_learning_ready)
        injection_mode = cfg.get("injection_mode", "append")
        if injection_mode == "append":
            try:
                self.context.deactivate_llm_tool("get_conversation_style")
                self.context.deactivate_llm_tool("get_jargon_meaning")
                logger.info("[SL] injection_mode=append, deactivated LLM tools")
            except Exception as e:
                logger.warning(f"[SL] failed to deactivate tools: {e}")

        await self._register_cron()
        await self._register_reflector_cron()
        try:
            ApiRouter(self).register()
        except Exception as e:
            logger.info(f"[SL] built-in WebUI unavailable, starting self-hosted API: {e}")
            ApiRouter(self).start_self_hosted()
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
                logger.info("[SL] fixed expression_groups type in config")
            except Exception:
                self.config["expression_groups"] = []
        # 从 DB 恢复图片描述缓存（重启不丢）
        db = get_db()
        self._image_captions = db.get_all_image_captions()
        if self._image_captions:
            logger.info(f"[SL] restored {len(self._image_captions)} image captions from DB")
        logger.info("[SL] initialized successfully")

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
            "max_context_turns": 1,
            "context_recent_messages_count": 0,
            "context_include_images": True,
            "guard_enabled": True,
            "debounce_seconds": 1,
            "smooth_seconds": 2,
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
            logger.info(f"[SL] LLM({task}) | attempting to get provider...")
            provider = self.context.get_using_provider()
            if model_override:
                try:
                    override = self.context.get_provider_by_id(model_override)
                    if override:
                        provider = override
                        logger.info(f"[SL] LLM({task}) | using overridden provider {model_override}")
                except Exception as e:
                    logger.error(f"[SL] LLM({task}) | get_provider_by_id failed: {e}")
            if not provider:
                providers = self.context.get_all_providers()
                if not providers:
                    msg = "ERROR: 没有找到任何 LLM Provider，请在 AstrBot 中至少配置一个模型"
                    logger.error(f"[SL] LLM({task}) | {msg}")
                    return msg
                provider = providers[0]
                logger.info(f"[SL] LLM({task}) | fallback to first provider")
            try:
                logger.info(f"[SL] LLM({task}) | calling LLM...")
                messages = [{"role": "user", "content": prompt}]
                resp = await provider.text_chat(
                    system_prompt=system_prompt
                    or "你是一个有用的助手。请严格按要求的格式输出。",
                    contexts=messages,
                )
                logger.info(f"[SL] LLM({task}) | response received")
                if isinstance(resp, tuple) and len(resp) > 0:
                    resp = resp[0]
                if hasattr(resp, "completion_text"):
                    return resp.completion_text
                if isinstance(resp, str):
                    return resp
                return str(resp)
            except Exception as e:
                msg = f"ERROR: LLM 调用异常 - {e}"
                logger.error(f"[SL] LLM({task}) | {e}")
                return msg

        return call_llm

    async def _register_cron(self):
        if self._cron_registered:
            return
        try:
            cron = self.context.cron_manager
            if cron is None:
                logger.warning("[SL] cron manager unavailable")
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
            logger.info("[SL] cron job registered")
        except Exception as e:
            logger.warning(f"[SL] cron registration failed: {e}")

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
            logger.info("[SL] reflector cron registered")
        except Exception as e:
            logger.warning(f"[SL] reflector cron registration failed: {e}")

    async def _on_tick(self):
        if not self.recorder:
            return
        for chat_id in self.recorder.get_pending_chat_ids():
            messages = self.recorder.force_trigger(chat_id)
            if messages:
                logger.debug(f"[SL] ⏰ cron tick triggered learning | chat={chat_id} msgs={len(messages)}")
                await self._run_learning(chat_id, messages)

    async def _on_reflector_tick(self):
        if not self.reflector:
            return
        try:
            ask_text = await self.reflector.ask_if_needed()
            if ask_text and self.reflector._operator_chat_id:
                await self._send_admin_message(ask_text)
        except Exception as e:
            logger.error(f"[SL] reflector tick error: {e}")

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
            logger.warning(f"[SL] failed to send admin message: {e}")

    def _on_learning_ready(self, chat_id: str, messages: list[dict]):
        import asyncio
        logger.debug(f"[SL] 📚 learning triggered (threshold met) | chat={chat_id} msgs={len(messages)}")
        asyncio.create_task(self._run_learning(chat_id, messages))

    def _build_chat_observe_info(self, chat_id: str) -> str:
        """构建聊天观察信息：将最近的消息格式化为供 classic 模式选择器使用的上下文文本"""
        if chat_id not in self._recent_messages:
            return ""
        recent = list(self._recent_messages[chat_id])
        if not recent:
            return ""
        ctx_recent_count = 15
        recent = recent[-ctx_recent_count:]
        lines = []
        for m in recent:
            sender = m.get("sender", m.get("role", "?"))
            text = m.get("text", "")
            line = f"{sender}: {text}"
            images = m.get("images", [])
            if images:
                captions = [img.get("caption") for img in images if img.get("caption")]
                if captions:
                    line += " [图片: " + "; ".join(captions) + "]"
                else:
                    line += " [图片]"
            lines.append(line)
        return "\n".join(lines)

    def _extract_images(self, event: AstrMessageEvent) -> list[dict]:
        images = []
        for comp in event.get_messages():
            if hasattr(comp, "type") and str(comp.type) == "Image":
                url = getattr(comp, "url", "") or ""
                file = getattr(comp, "file", "") or ""
                img_url = url or file or ""
                if img_url:
                    caption = self._image_captions.get(img_url, None)
                    images.append({"url": img_url, "caption": caption})
                else:
                    images.append({"url": "[图片]", "caption": None})
        return images

    async def _generate_image_captions(self, images: list[dict]):
        try:
            bot_cfg = self.context.get_config()
            prov_id = bot_cfg.get("provider_settings", {}).get(
                "default_image_caption_provider_id", ""
            )
            provider = None
            if prov_id:
                provider = self.context.get_provider_by_id(prov_id)
            # 回退：未配置专用图片描述 provider 时，使用当前主 provider
            if not provider:
                provider = self.context.get_using_provider()
            if not provider:
                logger.debug("[SL] image caption: no provider available")
                return
            prompt = bot_cfg.get("provider_settings", {}).get(
                "image_caption_prompt", "Please describe the image using Chinese."
            )
            for img_info in images:
                img_url = img_info["url"]
                if img_url == "[图片]" or img_url in self._image_captions:
                    continue
                try:
                    resp = await provider.text_chat(
                        prompt=prompt, image_urls=[img_url]
                    )
                    caption = (resp.completion_text or "").strip()
                    if caption:
                        self._image_captions[img_url] = caption
                        img_info["caption"] = caption
                        get_db().save_image_caption(img_url, caption)
                        logger.info(f"[SL] image caption generated | url={img_url[:60]}...")
                except Exception as e:
                    logger.warning(f"[SL] image caption failed: {e}")
        except Exception as e:
            logger.warning(f"[SL] image caption setup failed: {e}")

    async def _run_learning(self, chat_id: str, messages: list[dict]) -> list[dict]:
        """执行学习，返回本次学到的新条目列表"""
        cfg = await self._get_config()
        enabled = cfg.get("enable_expression_learning", True)
        if not enabled or not self.learner:
            logger.warning(f"[SL] learning skipped | enabled={enabled} learner_ready={self.learner is not None}")
            return []
        # 学习前补全图片描述：收集所有无描述的图片，批量生成
        pending = []
        for m in messages:
            for img in (m.get("images") or []):
                if not isinstance(img, dict):
                    continue
                url = img.get("url", "")
                if url and url != "[图片]" and url not in self._image_captions:
                    pending.append(img)
        if pending:
            logger.debug(
                f"[SL] pre-learning caption gen | chat={chat_id} pending={len(pending)}"
            )
            await self._generate_image_captions(pending)
        enable_jargon = cfg.get("enable_jargon_mining", True)
        items = await self.learner.learn_and_store(
            messages, chat_id, self._bot_name, enable_jargon
        )
        logger.info(f"[SL] learning done | chat={chat_id} items={len(items)}")
        return items

    # ── Main hooks ──

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin or ""
        user_text = event.message_str or ""
        images = self._extract_images(event)
        if not user_text.strip() and not images:
            return
        # 记录消息到达时间，用于 debounce"最后一条不跳过"的判断
        now = time.time()
        event.set_extra("_msg_arrival_ts", now)
        self._last_message_ts[umo] = now
        logger.debug(
            f"[SL] 📩 on_message | umo={umo} text={len(user_text)}ch "
            f"imgs={len(images)} ts={now:.3f}"
        )
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
        self.recorder.record(umo, "user", user_text, sender_name=sender_name, images=images)
        logger.debug(
            f"[SL] 📝 recorded msg | umo={umo} sender={sender_name} "
            f"text_len={len(user_text)} imgs={len(images)}"
        )
        if umo not in self._recent_messages:
            self._recent_messages[umo] = deque(maxlen=200)
        msg_entry = {
            "role": "user", "sender": sender_name, "text": user_text,
        }
        if images:
            msg_entry["images"] = images
        self._recent_messages[umo].append(msg_entry)
        if images:
            asyncio.create_task(self._generate_image_captions(msg_entry["images"]))
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
        chat_id = umo
        # 图片由 AstrBot 核心在 build_main_agent 中自动处理（提取→压缩→req.image_urls 或描述）
        # 纯图片消息也需走 hook，确保风格/工具/guard 注入生效
        if not user_text.strip():
            msg_images = self._extract_images(event)
            if msg_images:
                placeholder = f"[用户发送了 {len(msg_images)} 张图片]"
                req.extra_user_content_parts.append(
                    TextPart(text=placeholder).mark_as_temp()
                )
                logger.debug(
                    f"[SL] 🖼️ image placeholder injected | umo={chat_id} "
                    f"count={len(msg_images)}"
                )
        cfg = await self._get_config()
        injection_mode = cfg.get("injection_mode", "append")
        checked_only = cfg.get("expression_checked_only", False)
        selection_mode = cfg.get("selection_mode", "classic")

        # 确保时间戳字段已设置（on_message 不一定每次都会跑）
        arrival_ts = event.get_extra("_msg_arrival_ts", None)
        if arrival_ts is None:
            arrival_ts = time.time()
            event.set_extra("_msg_arrival_ts", arrival_ts)

        # 防抖 + 半句话保护
        #  有更新消息到达 → 跳过本次注入
        debounce = cfg.get("debounce_seconds", 0)
        try:
            debounce = float(debounce)
        except (TypeError, ValueError):
            debounce = 0.0
        if debounce > 0:
            last_msg = self._last_message_ts.get(chat_id, 0.0)
            if last_msg > arrival_ts:
                logger.debug(
                    f"[SL] ⏭️ debounce skip (newer msg) | umo={chat_id}"
                )
                return
            age = time.time() - last_msg
            if age < debounce:
                logger.debug(
                    f"[SL] ⏭️ debounce skip (too new) | umo={chat_id} "
                    f"age={age:.1f}s < {debounce}s"
                )
                return

        # 平滑：连续两次 LLM 调用之间至少间隔 smooth_seconds
        smooth = cfg.get("smooth_seconds", 0)
        try:
            smooth = float(smooth)
        except (TypeError, ValueError):
            smooth = 0.0
        if smooth > 0:
            last_llm = self._last_llm_time.get(chat_id, 0.0)
            if last_llm > 0:
                elapsed = time.time() - last_llm
                if elapsed < smooth:
                    logger.debug(
                        f"[SL] ⏭️ smooth skip | umo={chat_id} "
                        f"elapsed={elapsed:.1f}s < {smooth}s"
                    )
                    return
        self._last_llm_time[chat_id] = time.time()

        logger.debug(
            f"[SL] 🔧 on_llm_request | umo={chat_id} "
            f"mode={injection_mode} sel={selection_mode} "
            f"max_turns={cfg.get('max_context_turns', 0)} "
            f"ctx_msgs={cfg.get('context_recent_messages_count', 0)}"
        )

        if not self.selector or not self.explainer:
            logger.warning("[SL] selector or explainer not initialized")
            return
        if injection_mode not in ("append", "both"):
            logger.info(f"[SL] skip | injection_mode={injection_mode}")
            return
            return
        # 裁剪对话历史：保留最近 N 轮 user+assistant 对话
        # style injection 已注入到 extra_user_content_parts，过期的历史对话冗余
        max_turns = cfg.get("max_context_turns", 0)
        if max_turns == 0:
            req.contexts.clear()
            logger.debug(f"[SL] 🗑️ cleared all history | umo={chat_id}")
        elif max_turns > 0 and len(req.contexts) > 0:
            user_count = 0
            cutoff = 0
            for i in range(len(req.contexts) - 1, -1, -1):
                if req.contexts[i].get("role") == "user":
                    user_count += 1
                    if user_count > max_turns:
                        cutoff = i + 1
                        break
            if cutoff > 0:
                req.contexts = req.contexts[cutoff:]
                logger.debug(
                    f"[SL] 📐 trimmed history | umo={chat_id} "
                    f"keep={len(req.contexts)}msgs max_turns={max_turns}"
                )

        # 匹配黑话
        jargon_list = self.explainer.match_from_text(user_text, chat_id)[:5]
        # 获取聊天上下文（最近消息）供 classic 模式分析
        chat_observe_info = self._build_chat_observe_info(chat_id)
        req.extra_user_content_parts.append(TextPart(text=get_prompt("style")).mark_as_temp())
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
            req.extra_user_content_parts.append(TextPart(text=hint).mark_as_temp())
            logger.info(
                f"[SL] 💉 hint injected | umo={chat_id} hint_len={len(hint)} "
                f"jargons={len(jargon_list)}"
            )
        else:
            db = get_db()
            expr_count = db.conn.execute(
                "SELECT COUNT(*) as cnt FROM expressions WHERE (rejected=0 OR rejected IS NULL)"
            ).fetchone()["cnt"]
            jargon_count = db.conn.execute(
                "SELECT COUNT(*) as cnt FROM jargons"
            ).fetchone()["cnt"]
            logger.info(
                f"[SL] ⚠️ no hint | umo={chat_id} "
                f"DB(expr={expr_count}, jargon={jargon_count}) "
                f"mode={injection_mode} sel={selection_mode}"
            )

        # 注入最近 N 条聊天消息作为上下文（放在最后，确保在用户消息尾部）
        ctx_count = cfg.get("context_recent_messages_count", 0)
        if ctx_count > 0 and chat_id in self._recent_messages:
            recent = list(self._recent_messages[chat_id])[-ctx_count:]
            if recent:
                lines = [
                    "你是群聊中的一员。以下是最新的聊天记录，"
                    "请根据上下文判断是否需要回复。\n"
                ]
                for m in recent:
                    sender = m.get("sender", m.get("role", "?"))
                    text = m.get("text", "")
                    if m.get("role") == "assistant":
                        line = f"[你]: {text}"
                    else:
                        line = f"[聊天] {sender}: {text}"
                    images = m.get("images", [])
                    if images:
                        captions = [img.get("caption") for img in images if img.get("caption")]
                        if captions:
                            line += " [图片: " + "; ".join(captions) + "]"
                        else:
                            line += " [图片]"
                    lines.append(line)
                req.extra_user_content_parts.append(
                    TextPart(text="\n".join(lines)).mark_as_temp()
                )
                logger.info(
                    f"[SL] 📋 context injected | umo={chat_id} "
                    f"recent_msgs={len(recent)}"
                )
        # 工具指令双端注入：系统提示 + 用户消息尾部
        _tool_hint = (
            "- 你只能用 send_message_to_user 工具向用户发送消息"
            "（参数格式：{'messages': [{'type': 'plain', 'text': '要发送的消息'}]}），"
            "如果无需回复，不要使用工具也不要输出任何文本。"
        )
        if _tool_hint not in req.system_prompt:
            req.system_prompt = req.system_prompt.rstrip() + "\n\n" + _tool_hint
        req.extra_user_content_parts.append(
            TextPart(text=_tool_hint).mark_as_temp()
        )
        event.set_extra("_guard_tool_expected", True)
        logger.debug(
            f"[SL] 🛡️ guard armed | umo={chat_id} "
            f"tool_expected=True"
        )

    @filter.on_llm_tool_respond()
    async def on_tool_respond(self, event: AstrMessageEvent, tool, tool_args, tool_result):
        if tool.name == "send_message_to_user":
            event.set_extra("_tool_sent_message", True)
            logger.debug(
                f"[SL] 🔨 tool sent | umo={event.unified_msg_origin} "
                f"tool={tool.name} args_keys={list(tool_args.keys()) if isinstance(tool_args, dict) else '?'}"
            )

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, response):
        umo = event.unified_msg_origin or ""
        if not self.recorder:
            return
        # Guard：标记 LLM 是否通过 send_message_to_user 工具发送了消息
        tool_sent = hasattr(response, "tools_call_name") and "send_message_to_user" in (
            response.tools_call_name or []
        )
        ct = (response.completion_text or "").strip()

        flags = {}
        if tool_sent:
            event.set_extra("_tool_sent_message", True)
            flags["tool_sent"] = True
        if ct and not tool_sent:
            event.set_extra("_llm_heart_words", True)
            flags["heart_words"] = True

        logger.debug(
            f"[SL] 📤 on_llm_response | umo={umo} "
            f"text_len={len(ct)} flags={flags}"
        )

        # 记录到对话历史。关掉 guard 时直接文本也记录，否则只记工具发送的消息
        guard_on = self.config.get("guard_enabled", True) if isinstance(self.config, dict) else True
        if ct and (tool_sent or not guard_on):
            self.recorder.record(
                umo, "assistant", ct, sender_name=self._bot_name
            )
            if umo not in self._recent_messages:
                self._recent_messages[umo] = deque(maxlen=200)
            self._recent_messages[umo].append({
                "role": "assistant", "sender": f"{self._bot_name}（你）", "text": ct,
                "images": [],
            })

    @filter.on_decorating_result(priority=9999)
    async def on_guard_result(self, event: AstrMessageEvent):
        cfg = await self._get_config()
        if not cfg.get("guard_enabled", True):
            return
        result = event.get_result()
        if not result or not result.chain:
            return

        guard_expected = event.get_extra("_guard_tool_expected")
        tool_sent = event.get_extra("_tool_sent_message")
        heart_words = event.get_extra("_llm_heart_words")
        plain = (result.get_plain_text() or "").strip()
        chain_types = [type(c).__name__ for c in result.chain]

        if guard_expected:
            if tool_sent:
                result.chain.clear()
                logger.debug(
                    f"[SL] 🛡️ guard: cleared (tool sent) | "
                    f"umo={event.unified_msg_origin} chain={chain_types}"
                )
            elif plain:
                result.chain.clear()
                event.stop_event()
                logger.debug(
                    f"[SL] 🛡️ guard: blocked heart words | "
                    f"umo={event.unified_msg_origin} text_preview={plain[:80]}"
                )
            else:
                logger.debug(
                    f"[SL] 🛡️ guard: pass (empty chain, intermediate yield) | "
                    f"umo={event.unified_msg_origin} chain={chain_types}"
                )
        elif tool_sent or heart_words:
            result.chain.clear()
            event.stop_event()
            reason = "tool" if tool_sent else "heart_words"
            logger.debug(
                f"[SL] 🛡️ guard: blocked ({reason}, fallback) | "
                f"umo={event.unified_msg_origin} chain={chain_types}"
            )

    # ── Commands ──

    @filter.command("style")
    async def style_cmd(self, event: AstrMessageEvent, action: str = "", emotion: str = "all"):
        if action == "list":
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
        elif action == "stats":
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
        else:
            yield event.plain_result(
                "🎭 表达风格学习插件\n"
                "用法：\n"
                "/style list [情绪] - 查看表达列表\n"
                "/style stats - 查看学习统计"
            )

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

    async def terminate(self):
        logger.info("[SL] terminating...")
        if self.auto_check:
            self.auto_check.stop()
        cron = getattr(self.context, "cron_manager", None)
        if cron:
            for job_id in self._cron_jobs:
                try:
                    await cron.delete_job(job_id)
                except Exception as e:
                    logger.warning(f"[SL] failed to delete cron job {job_id}: {e}")
        self._cron_jobs.clear()
