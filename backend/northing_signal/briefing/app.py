"""AI reader: shared content, one account per token."""

import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from .. import __version__
from .models import (
    TOPICS,
    CancelRequest,
    ConfirmFollow,
    Contract,
    DiscoveryRequest,
    FollowState,
    Interaction,
    InterpretFollow,
    MergeRequest,
    Preferences,
    RefreshRequest,
    SplitRequest,
    VisitRequest,
    day_start,
)
from .service import ContentService
from .settings import ReaderSettings
from .store import LOCAL_USER, Store

COOKIE = "ns_token"
COOKIE_AGE = 400 * 86400  # the longest lifetime browsers accept
ADMIN_FOLLOW_LIMIT = 12
TOUCH_SECONDS = 300  # write "last seen" at most this often per account


class LoginRequest(Contract):
    token: str = Field(min_length=1, max_length=200)


def create_app(settings=None, store=None):
    settings = settings or ReaderSettings()
    store = store or Store(settings.root / ".local/briefing-v2.db")
    service = ContentService(store, settings)
    auth = getattr(settings, "reader_auth", "token")
    touched = {}
    signups = defaultdict(deque)  # client address -> creation times within the last hour

    @asynccontextmanager
    async def lifespan(app):
        if service.analyzer.configured and settings.reader_requests_per_day is None \
                and settings.reader_tokens_per_day is None:
            logging.getLogger(__name__).warning(
                "No daily model limit is set (READER_REQUESTS_PER_DAY / READER_TOKENS_PER_DAY); usage is only recorded.")
        if auth == "token" and not any(u["role"] == "admin" and u["has_token"] for u in store.users()):
            logging.getLogger(__name__).warning(
                "No admin token yet: run `python -m northing_signal.briefing token --admin --claim-local`.")
        service.start_tracking()
        yield
        await service.close()

    app = FastAPI(title="Northing Signal · AI 简报", version=__version__, lifespan=lifespan)
    app.state.content = service

    extra_origins = {o.strip().rstrip("/") for o in getattr(settings, "reader_allowed_origins", "").split(",")
                     if o.strip()}

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            # Changes come only from this site's own pages (and configured origins): a cookie
            # sent by another site's form or script is refused.
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            allowed = {f"{scheme}://{host}" for scheme in ("http", "https")} | extra_origins
            allowed |= {f"http://{name}:{port}" for name in ("127.0.0.1", "localhost")
                        for port in (request.url.port or 80, 5173)}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "仅接受本站页面的操作"}, status_code=403)
            body = await request.body()
            if len(body) > 32768:
                return JSONResponse({"detail": "请求过大"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- accounts ------------------------------------------------------------------------------

    def token_of(request):
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.cookies.get(COOKIE)

    def signed_in(request):
        if auth == "off":
            return store.user(LOCAL_USER)
        user = store.user_by_token(token_of(request))
        if user and time.monotonic() - touched.get(user["id"], -TOUCH_SECONDS) >= TOUCH_SECONDS:
            touched[user["id"]] = time.monotonic()
            store.touch_user(user["id"])
        return user

    async def current_user(request: Request):
        user = await asyncio.to_thread(signed_in, request)
        if not user:
            raise HTTPException(401, "请先登录")
        return user

    async def admin_user(user=Depends(current_user)):
        if user["role"] != "admin":
            raise HTTPException(403, "只有管理员可以执行这个操作")
        return user

    def limited(user):
        return auth == "token" and user["role"] != "admin"

    def follow_limit(user):
        return settings.reader_user_follow_limit if limited(user) else ADMIN_FOLLOW_LIMIT

    def quota_since():
        return day_start(getattr(settings, "reader_timezone", ""))

    def spend(user, kind):
        """One of the reader's daily requests (search, intent, manual topic check)."""
        limit = settings.reader_user_requests_per_day if limited(user) else None
        try:
            store.reserve_usage(user["id"], kind, limit, quota_since())
        except ValueError:
            raise HTTPException(429, f"今天的 {limit} 次主动检索与 AI 理解额度已用完，明天再试。") from None

    def account(user):
        is_limited = limited(user)
        return {"id": user["id"], "role": user["role"], "auth": auth,
                "limits": {"follows": follow_limit(user),
                           "requests_per_day": settings.reader_user_requests_per_day if is_limited else None,
                           "requests_today": store.usage_count(user["id"], quota_since())}}

    def secure(request):
        mode = getattr(settings, "reader_cookie_secure", "auto")
        if mode != "auto":
            return mode == "always"
        return (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"

    def keep_session(response, request, token):
        response.set_cookie(COOKIE, token, max_age=COOKIE_AGE, httponly=True, samesite="lax",
                            secure=secure(request), path="/")

    @app.get("/api/auth/session")
    async def session(request: Request):
        """Who is signed in (or null), and whether visitors may create a token."""
        user = await asyncio.to_thread(signed_in, request)
        return {"auth": auth, "signup": auth == "token" and settings.reader_signup,
                "user": account(user) if user else None}

    @app.post("/api/auth/login")
    async def login(body: LoginRequest, request: Request, response: Response):
        if auth == "off":
            return {"user": account(store.user(LOCAL_USER))}
        user = await asyncio.to_thread(store.user_by_token, body.token.strip())
        if not user:
            await asyncio.sleep(0.5)  # unhurried guessing only
            raise HTTPException(401, "令牌无效，请检查是否完整复制")
        keep_session(response, request, body.token.strip())
        return {"user": account(user)}

    @app.post("/api/auth/register", status_code=201)
    async def register(request: Request, response: Response):
        """Create an account and return its token once; the page asks the reader to keep it."""
        if auth == "off":
            raise HTTPException(409, "本机模式不需要令牌")
        if not settings.reader_signup:
            raise HTTPException(403, "本站暂未开放创建令牌，请向管理员索取")
        address = request.client.host if request.client else "unknown"
        recent, clock = signups[address], time.monotonic()
        while recent and clock - recent[0] > 3600:
            recent.popleft()
        if len(recent) >= settings.reader_signups_per_hour:
            raise HTTPException(429, "创建令牌太频繁，请一小时后再试")
        recent.append(clock)
        user, token = await asyncio.to_thread(store.create_user, "user")
        keep_session(response, request, token)
        return {"user": account(user), "token": token}

    @app.post("/api/auth/logout")
    async def logout(response: Response):
        response.delete_cookie(COOKIE, path="/")
        return {"signed_out": True}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__, "engine": "content-v1"}

    # SQLite reads and the briefing projection are blocking; keep them off the event loop.
    def off_loop(function, *args, **kwargs):
        return asyncio.to_thread(function, *args, **kwargs)

    async def personal_view(user):
        value = await off_loop(service.view, user["id"])
        return {**value, "account": account(user)}

    # ---- reading -------------------------------------------------------------------------------

    @app.get("/api/reader")
    async def reader(user=Depends(current_user)):
        return await personal_view(user)

    @app.post("/api/reader/visits")
    async def visit(body: VisitRequest, user=Depends(current_user)):
        await off_loop(store.visit, body.request_id, user["id"])
        return {"recorded": True}

    @app.get("/api/reader/snapshots")
    async def snapshots(user=Depends(current_user)):
        return await off_loop(store.snapshots, None, user["id"])

    @app.get("/api/reader/snapshots/{key}")
    async def snapshot(key: str, user=Depends(current_user)):
        result = await off_loop(store.snapshots, key, user["id"])
        if result is None:
            raise HTTPException(404, "这份简报不存在")
        return result

    @app.get("/api/reader/reports/weekly")
    async def weekly(range: Literal["recent", "last_week"] = "recent", user=Depends(current_user)):
        return await off_loop(service.weekly_report, range, user["id"])

    @app.get("/api/reader/status")
    async def status(user=Depends(current_user)):
        return {"run": service.visible_run(service.run, user["id"]),
                "queue": [service.visible_run(r, user["id"]) for r in service.queued()],
                "sources": service.source_list(), "model_configured": service.analyzer.configured,
                "usage": service.model_usage()}

    @app.get("/api/reader/topics")
    async def topics():
        return TOPICS

    @app.put("/api/reader/preferences")
    async def preferences(body: Preferences, user=Depends(current_user)):
        await off_loop(store.save_preferences, body, user["id"])
        return await personal_view(user)

    @app.post("/api/reader/interactions")
    async def interact(body: Interaction, user=Depends(current_user)):
        try:
            created = await off_loop(service.record_interaction, body, user["id"])
            return {"created": created}
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.get("/api/reader/materials/{version}")
    async def material(version: str, user=Depends(current_user)):
        row = await off_loop(store.material, version)
        if not row:
            raise HTTPException(404, "原始材料不存在")
        return row.model_dump()

    # ---- shared updates (any reader may start one; one runs at a time) ------------------------

    @app.post("/api/reader/refresh", status_code=202)
    async def refresh(body: RefreshRequest, user=Depends(current_user)):
        try:
            return service.visible_run(service.start(body, user=user["id"]), user["id"])
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/reader/cancel")
    async def cancel(body: CancelRequest | None = None, user=Depends(current_user)):
        owner = None if user["role"] == "admin" else user["id"]
        try:
            return service.visible_run(await service.cancel(body.id if body else None, owner), user["id"])
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None

    @app.post("/api/reader/discover", status_code=202)
    async def discovery(body: DiscoveryRequest, user=Depends(current_user)):
        await off_loop(spend, user, "discovery")
        try:
            return service.start_discovery(body, user["id"])
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    # ---- topic tracking (each reader's own) ----------------------------------------------------

    def own_follow(user, key):
        if not any(f["id"] == key for f in store.follows(user["id"])):
            raise HTTPException(404, "这个关注话题不存在")

    @app.post("/api/reader/follows/interpret")
    async def interpret_follow(body: InterpretFollow, user=Depends(current_user)):
        if body.follow_id:
            own_follow(user, body.follow_id)
        elif len(store.follows(user["id"])) >= follow_limit(user):
            raise HTTPException(409, f"最多关注 {follow_limit(user)} 个话题，请先取消不再需要的话题")
        await off_loop(spend, user, "intent")
        try:
            return await service.intent.interpret(body.description, body.follow_id, user["id"])
        except ValueError as error:
            messages = {"model_not_configured": "请先配置 AI 模型，再理解追踪意图。",
                        "daily_model_budget_reached": "今天的 AI 处理额度已用完，尚未创建追踪。",
                        "intent_model_request_failed": "AI 服务暂时请求失败，请稍后重试；追踪尚未启动。",
                        "intent_model_response_invalid": "AI 返回的方案不完整，请重试；追踪尚未启动。"}
            raise HTTPException(409, messages.get(str(error), "暂时无法理解需求，请稍后重试。")) from None

    @app.post("/api/reader/follows", status_code=201)
    async def follow(body: ConfirmFollow, user=Depends(current_user)):
        key = user["id"]
        try:
            row, changed = store.confirm_follow(body, key, follow_limit(user))
            if changed:
                # Work queued or running under the replaced plan must not finish under the new one.
                if await service.cancel_follow(row["id"], key):
                    store.update_follow(row["id"], user=key, last_checked=None, last_status="not_checked",
                                        last_errors=[])
                if row["active"]:
                    service.start_follow(row["id"], user=key)
            return {**await personal_view(user), "confirmed_follow_id": row["id"]}
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.patch("/api/reader/follows/{key}")
    async def follow_state(key: str, body: FollowState, user=Depends(current_user)):
        try:
            current = next((f for f in store.follows(user["id"]) if f["id"] == key), None)
            if body.active and current and not current.get("intent_plan"):
                raise HTTPException(409, "请先重新描述需求，确认 AI 追踪方案后再开启。")
            store.update_follow(key, user=user["id"], active=body.active)
            if not body.active:
                await service.cancel_follow(key, user["id"])
            return await personal_view(user)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @app.delete("/api/reader/follows/{key}")
    async def unfollow(key: str, user=Depends(current_user)):
        try:
            own_follow(user, key)
            await service.cancel_follow(key, user["id"])
            store.update_follow(key, user=user["id"], active=False, archived=True)
            return await personal_view(user)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @app.post("/api/reader/follows/{key}/refresh", status_code=202)
    async def refresh_follow(key: str, user=Depends(current_user)):
        own_follow(user, key)
        await off_loop(spend, user, "follow_check")
        try:
            return service.start_follow(key, user=user["id"])
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/reader/follows/{key}/seen")
    async def seen_follow(key: str, user=Depends(current_user)):
        view = await off_loop(service.view, user["id"])
        item = next((f for f in view["follows"] if f["id"] == key), None)
        if not item:
            raise HTTPException(404, "这个关注话题不存在")
        store.update_follow(key, user=user["id"], seen_versions=item["versions"])
        return await personal_view(user)

    # ---- shared corrections: they change what every reader sees ------------------------------

    @app.post("/api/reader/events/{key}/split")
    async def split_event(key: str, body: SplitRequest, user=Depends(admin_user)):
        """A reader says one report is not the same occurrence; it becomes its own event."""
        try:
            await off_loop(service.split_event, key, body.version)
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return await personal_view(user)

    @app.post("/api/reader/events/{key}/merge")
    async def merge_event(key: str, body: MergeRequest, user=Depends(admin_user)):
        try:
            await off_loop(service.merge_events, key, body.into)
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return await personal_view(user)

    @app.post("/api/reader/materials/{version}/retry")
    async def retry_material(version: str, user=Depends(admin_user)):
        """Clear a material's failed judgments so the next update tries it again."""
        if not await off_loop(store.clear_failure, version):
            raise HTTPException(404, "这条材料没有整理失败记录")
        return await personal_view(user)

    # ---- the page ------------------------------------------------------------------------------

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
