"""Standalone local AI reader."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .models import (
    TOPICS,
    ConfirmFollow,
    DiscoveryRequest,
    FollowState,
    Interaction,
    InterpretFollow,
    Preferences,
    RefreshRequest,
    VisitRequest,
)
from .service import ContentService
from .settings import ReaderSettings
from .store import Store


def create_app(settings=None, store=None):
    settings = settings or ReaderSettings()
    store = store or Store(settings.root / ".local/briefing-v2.db")
    service = ContentService(store, settings)

    @asynccontextmanager
    async def lifespan(app):
        service.start_tracking()
        yield
        await service.close()

    app = FastAPI(title="CFAW News · AI 简报", version=__version__, lifespan=lifespan)
    app.state.content = service

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost")
                       for port in (request.url.port or 80, 5173)}
            if origin and origin not in allowed:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "仅接受本机阅读页面的操作"}, status_code=403)
            body = await request.body()
            if len(body) > 32768:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "请求过大"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__, "engine": "content-v1"}

    # SQLite reads and the briefing projection are blocking; keep them off the event loop.
    def off_loop(function, *args):
        return asyncio.to_thread(function, *args)

    @app.get("/api/reader")
    async def reader():
        return await off_loop(service.view)

    @app.post("/api/reader/visits")
    async def visit(body: VisitRequest):
        await off_loop(store.visit, body.request_id)
        return {"recorded": True}

    @app.get("/api/reader/snapshots")
    async def snapshots():
        return await off_loop(store.snapshots)

    @app.get("/api/reader/snapshots/{key}")
    async def snapshot(key: str):
        result = await off_loop(store.snapshots, key)
        if result is None:
            raise HTTPException(404, "这份简报不存在")
        return result

    @app.get("/api/reader/status")
    async def status():
        return {"run": service.run, "sources": service.source_list(),
                "model_configured": service.analyzer.configured,
                "usage": service.model_usage()}

    @app.get("/api/reader/topics")
    async def topics():
        return TOPICS

    @app.post("/api/reader/refresh", status_code=202)
    async def refresh(body: RefreshRequest):
        try:
            return service.start(body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/reader/cancel")
    async def cancel():
        return await service.cancel()

    @app.post("/api/reader/discover", status_code=202)
    async def discovery(body: DiscoveryRequest):
        try:
            return service.start_discovery(body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.put("/api/reader/preferences")
    async def preferences(body: Preferences):
        await off_loop(store.save_preferences, body)
        return await off_loop(service.view)

    @app.post("/api/reader/follows/interpret")
    async def interpret_follow(body: InterpretFollow):
        if body.follow_id and not any(f["id"] == body.follow_id for f in store.follows()):
            raise HTTPException(404, "这个关注话题不存在")
        try:
            return await service.intent.interpret(body.description, body.follow_id)
        except ValueError as error:
            messages = {"model_not_configured": "请先配置 AI 模型，再理解追踪意图。",
                        "daily_model_budget_reached": "今天的 AI 处理额度已用完，尚未创建追踪。",
                        "intent_model_request_failed": "AI 服务暂时请求失败，请稍后重试；追踪尚未启动。",
                        "intent_model_response_invalid": "AI 返回的方案不完整，请重试；追踪尚未启动。"}
            raise HTTPException(409, messages.get(str(error), "暂时无法理解需求，请稍后重试。")) from None

    @app.post("/api/reader/follows", status_code=201)
    async def follow(body: ConfirmFollow):
        try:
            row, changed = store.confirm_follow(body)
            if changed and service.run and service.run.get("follow_id") == row["id"]:
                await service.cancel()
                store.update_follow(row["id"], last_checked=None, last_status="not_checked", last_errors=[])
            if changed and row["active"] and not (service.task and not service.task.done()):
                service.start_follow(row["id"])
            return {**await off_loop(service.view), "confirmed_follow_id": row["id"]}
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.patch("/api/reader/follows/{key}")
    async def follow_state(key: str, body: FollowState):
        try:
            current = next((f for f in store.follows() if f["id"] == key), None)
            if body.active and current and not current.get("intent_plan"):
                raise HTTPException(409, "请先重新描述需求，确认 AI 追踪方案后再开启。")
            store.update_follow(key, active=body.active)
            if not body.active and service.run and service.run.get("follow_id") == key:
                await service.cancel()
            return await off_loop(service.view)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @app.delete("/api/reader/follows/{key}")
    async def unfollow(key: str):
        try:
            if service.run and service.run.get("follow_id") == key:
                await service.cancel()
            store.update_follow(key, active=False, archived=True)
            return await off_loop(service.view)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @app.post("/api/reader/follows/{key}/refresh", status_code=202)
    async def refresh_follow(key: str):
        try:
            return service.start_follow(key)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/reader/follows/{key}/seen")
    async def seen_follow(key: str):
        view = await off_loop(service.view)
        item = next((f for f in view["follows"] if f["id"] == key), None)
        if not item:
            raise HTTPException(404, "这个关注话题不存在")
        store.update_follow(key, seen_versions=item["versions"])
        return await off_loop(service.view)

    @app.post("/api/reader/interactions")
    async def interact(body: Interaction):
        try:
            created = await off_loop(service.record_interaction, body)
            return {"created": created}
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.get("/api/reader/materials/{version}")
    async def material(version: str):
        row = await off_loop(store.material, version)
        if not row:
            raise HTTPException(404, "原始材料不存在")
        return row.model_dump()

    dist = settings.root / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/icon.svg")
    async def icon():
        return FileResponse(settings.root / "frontend/public/icon.svg")

    @app.get("/")
    async def index():
        path = Path(dist / "index.html")
        if not path.exists():
            raise HTTPException(503, "请先在 frontend 中构建网页")
        return FileResponse(path)

    return app
