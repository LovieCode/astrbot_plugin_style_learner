import asyncio
import contextvars
import json

from astrbot.api import logger

from .models import get_db

_request_ctx = contextvars.ContextVar("request")


class _AiohttpRequestAdapter:
    def __init__(self, request):
        self._req = request
        self.args = request.query

    async def get_json(self, silent=True):
        try:
            return await self._req.json()
        except Exception:
            if silent:
                return None
            raise


def _get_request():
    req = _request_ctx.get(None)
    if req is not None:
        return req
    from quart import request as quart_request

    return quart_request


class ApiRouter:
    """WebUI API 路由，包装插件实例的 API 方法"""

    def __init__(self, plugin):
        self.plugin = plugin

    def register(self):
        p = self.plugin
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/expressions",
            self._api_get_expressions,
            ["GET"],
            "获取表达列表",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>",
            self._api_get_expression,
            ["GET"],
            "获取单个表达",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>/check",
            self._api_check_expression,
            ["POST"],
            "审核表达",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>",
            self._api_delete_expression,
            ["POST"],
            "删除表达",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/expression/<int:expr_id>/edit",
            self._api_edit_expression,
            ["POST"],
            "编辑表达",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/jargons",
            self._api_get_jargons,
            ["GET"],
            "获取黑话列表",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>",
            self._api_get_jargon,
            ["GET"],
            "获取单个黑话",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>/meaning",
            self._api_update_jargon_meaning,
            ["POST"],
            "编辑黑话含义",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>",
            self._api_delete_jargon,
            ["POST"],
            "删除黑话",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/jargon/<int:jargon_id>/check",
            self._api_check_jargon,
            ["POST"],
            "审核黑话",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/statistics",
            self._api_statistics,
            ["GET"],
            "获取学习统计",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/trigger-learn",
            self._api_trigger_learn,
            ["POST"],
            "手动触发学习",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/chat-groups",
            self._api_chat_groups,
            ["GET"],
            "获取群列表",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/known-chats",
            self._api_known_chats,
            ["GET"],
            "获取已知会话列表（含名称），用于配置下拉选择",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/settings",
            self._api_get_settings,
            ["GET"],
            "获取配置",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/settings",
            self._api_update_settings,
            ["POST"],
            "更新配置",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/pending-messages",
            self._api_pending_messages,
            ["GET"],
            "获取待学习消息",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/prompts",
            self._api_get_prompts,
            ["GET"],
            "获取所有 Prompt 模板",
        )
        p.context.register_web_api(
            "/astrbot_plugin_style_learner/prompts",
            self._api_save_prompts,
            ["POST"],
            "保存 Prompt 模板",
        )

    # ── handlers ──

    async def _api_get_expressions(self, *args, **kwargs):
        req = _get_request()
        chat_id = req.args.get("chat_id", "")
        emotion = req.args.get("emotion", "")
        status = req.args.get("status", "")
        search = req.args.get("search", "")
        page = int(req.args.get("page", 1))
        page_size = int(req.args.get("page_size", 20))
        db = get_db()
        exprs, total = db.get_expressions(
            chat_id=chat_id if chat_id else None,
            emotion=emotion if emotion and emotion != "all" else None,
            status=status,
            search=search,
            page=page,
            page_size=page_size,
        )
        chat_ids = list({e.get("chat_id", "") for e in exprs})
        name_map = db.get_chat_name_map(chat_ids)
        for e in exprs:
            e["_chat_name"] = name_map.get(e.get("chat_id", ""), "")
        return {"success": True, "data": {"items": exprs, "total": total}}

    async def _api_get_expression(self, expr_id: int, *args, **kwargs):
        db = get_db()
        expr = db.get_expression_by_id(expr_id)
        if expr is None:
            return {"success": False, "message": "表达方式不存在"}
        return {"success": True, "data": expr}

    async def _api_check_expression(self, expr_id: int, *args, **kwargs):
        req = _get_request()
        body = await req.get_json(silent=True) or {}
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
        req = _get_request()
        body = await req.get_json(silent=True) or {}
        db = get_db()
        db.update_expression(
            expr_id,
            **{k: v for k, v in body.items() if k in ("emotion", "situation", "style")},
        )
        return {"success": True}

    async def _api_get_jargons(self, *args, **kwargs):
        req = _get_request()
        chat_id = req.args.get("chat_id", "")
        search = req.args.get("search", "")
        page = int(req.args.get("page", 1))
        page_size = int(req.args.get("page_size", 20))
        db = get_db()
        jargons, total = db.get_jargons(
            chat_id=chat_id if chat_id else None,
            search=search,
            page=page,
            page_size=page_size,
        )
        chat_ids = list({j.get("chat_id", "") for j in jargons})
        name_map = db.get_chat_name_map(chat_ids)
        for j in jargons:
            j["_chat_name"] = name_map.get(j.get("chat_id", ""), "")
        return {"success": True, "data": {"items": jargons, "total": total}}

    async def _api_get_jargon(self, jargon_id: int, *args, **kwargs):
        db = get_db()
        j = db.get_jargon_by_id(jargon_id)
        if j is None:
            return {"success": False, "message": "黑话不存在"}
        return {"success": True, "data": j}

    async def _api_update_jargon_meaning(self, jargon_id: int, *args, **kwargs):
        req = _get_request()
        body = await req.get_json(silent=True) or {}
        meaning = body.get("meaning", "")
        db = get_db()
        db.update_jargon_meaning(jargon_id, meaning, is_jargon=True)
        return {"success": True}

    async def _api_check_jargon(self, jargon_id: int, *args, **kwargs):
        req = _get_request()
        body = await req.get_json(silent=True) or {}
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
        plugin = self.plugin
        if not plugin.recorder:
            return {"success": False, "message": "插件未初始化"}
        db = get_db()
        results = []
        for chat_id in plugin.recorder.get_all_chat_ids():
            messages = plugin.recorder.get_buffered_messages(chat_id)
            if not messages:
                continue
            chat_name = db.get_chat_name(chat_id) or chat_id
            logger.info(
                f"StyleLearner: manually triggering learning for {chat_id} ({chat_name}), {len(messages)} messages"
            )
            try:
                items = await plugin._run_learning(chat_id, list(messages))
            except Exception as e:
                logger.error(f"StyleLearner: learning failed for {chat_id}: {e}")
                results.append({
                    "chat_id": chat_id,
                    "_chat_name": chat_name,
                    "message_count": len(messages),
                    "items": [],
                    "error": str(e),
                })
                continue
            if items:
                plugin.recorder.clear_buffer(chat_id)
            results.append({
                "chat_id": chat_id,
                "_chat_name": chat_name,
                "message_count": len(messages),
                "items": items,
            })
        if not results:
            return {"success": True, "message": "没有待学习的消息"}
        total_items = sum(len(r["items"]) for r in results)
        return {
            "success": True,
            "data": results,
            "message": f"完成 {len(results)} 个群的学习，共学到 {total_items} 条",
        }

    async def _api_pending_messages(self, *args, **kwargs):
        req = _get_request()
        chat_id = req.args.get("chat_id", "")
        plugin = self.plugin
        if not plugin.recorder:
            return {"success": True, "data": []}
        if chat_id:
            msgs = plugin.recorder.get_buffered_messages(chat_id)
            return {"success": True, "data": msgs, "total": len(msgs)}
        summary = plugin.recorder.get_all_buffered_summary()
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
        cfg = await self.plugin._get_config()
        return {"success": True, "data": cfg}

    async def _api_update_settings(self, *args, **kwargs):
        req = _get_request()
        body = await req.get_json(silent=True) or {}
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
            self.plugin.config.update(body)
            if hasattr(self.plugin.config, "save_config"):
                self.plugin.config.save_config()
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
        return {"success": False, "message": "保存配置失败"}

    async def _api_get_prompts(self, *args, **kwargs):
        from .prompt_manager import get_all_prompts

        return {"success": True, "data": get_all_prompts()}

    async def _api_save_prompts(self, *args, **kwargs):
        from .prompt_manager import reset_prompt, set_prompt

        req = _get_request()
        body = await req.get_json(silent=True) or {}
        key = body.get("key", "")
        value = body.get("value")
        if not key:
            return {"success": False, "message": "缺少 key 参数"}
        if value is None or (isinstance(value, str) and not value.strip()):
            reset_prompt(key)
            return {"success": True, "message": f"Prompt '{key}' 已重置为默认值"}
        set_prompt(key, value)
        return {"success": True, "message": f"Prompt '{key}' 已保存"}

    # ── 自建管理页面 ──

    async def _serve_admin_page(self, request):
        from pathlib import Path

        from aiohttp import web

        html_path = Path(__file__).parent / "admin_page.html"
        try:
            return web.FileResponse(html_path)
        except Exception:
            return web.Response(text="admin_page.html not found", status=404)

    def start_self_hosted(self, host="0.0.0.0", port=6187):
        from aiohttp import web

        def _aiohttp_route(handler):
            async def wrapper(request):
                token = _request_ctx.set(_AiohttpRequestAdapter(request))
                try:
                    kwargs = {}
                    for k, v in request.match_info.items():
                        kwargs[k] = int(v) if v.isdigit() else v
                    result = await handler(**kwargs)
                    return web.json_response(result)
                finally:
                    _request_ctx.reset(token)
            return wrapper

        app = web.Application()

        @web.middleware
        async def cors_middleware(request, handler):
            if request.method == "OPTIONS":
                return web.Response(
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                    }
                )
            resp = await handler(request)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp

        app.middlewares.append(cors_middleware)

        P = "/astrbot_plugin_style_learner"

        # GET
        app.router.add_get(f"{P}/expressions", _aiohttp_route(self._api_get_expressions))
        app.router.add_get(f"{P}/expression/{{expr_id}}", _aiohttp_route(self._api_get_expression))
        app.router.add_get(f"{P}/jargons", _aiohttp_route(self._api_get_jargons))
        app.router.add_get(f"{P}/jargon/{{jargon_id}}", _aiohttp_route(self._api_get_jargon))
        app.router.add_get(f"{P}/statistics", _aiohttp_route(self._api_statistics))
        app.router.add_get(f"{P}/chat-groups", _aiohttp_route(self._api_chat_groups))
        app.router.add_get(f"{P}/known-chats", _aiohttp_route(self._api_known_chats))
        app.router.add_get(f"{P}/settings", _aiohttp_route(self._api_get_settings))
        app.router.add_get(f"{P}/pending-messages", _aiohttp_route(self._api_pending_messages))
        app.router.add_get(f"{P}/prompts", _aiohttp_route(self._api_get_prompts))

        # 前端管理页面
        app.router.add_get("/", self._serve_admin_page)

        async def _run():
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()
            logger.info(f"[SL] self-hosted API server started on http://{host}:{port}")

        asyncio.ensure_future(_run())
