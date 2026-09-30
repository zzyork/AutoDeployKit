import hmac
import os
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi_users import InvalidPasswordException
from fastapi_users.exceptions import UserAlreadyExists, UserNotExists
from pydantic import BaseModel, ConfigDict, Field

from webui.users import public_user


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: str = Field(min_length=3, max_length=32)
    password: str


class AccountCreate(Input):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z][a-z0-9_.-]*$")
    password: str = Field(min_length=12)
    admin_password: str


class AccountStatus(Input):
    is_active: bool
    admin_password: str


class AccountPassword(Input):
    new_password: str = Field(min_length=12)
    admin_password: str


class OwnPassword(Input):
    current_password: str
    new_password: str = Field(min_length=12)


class HostCreate(Input):
    name: str
    address: str
    username: str
    port: int = Field(default=22, ge=1, le=65535)
    group_name: str = "default"
    tags: list[str] = []
    password: str | None = None
    ssh_key_id: str | None = None
    proxy_host_id: str | None = None


class HostPatch(Input):
    name: str | None = None
    address: str | None = None
    username: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    group_name: str | None = None
    tags: list[str] | None = None
    password: str | None = None
    ssh_key_id: str | None = None
    proxy_host_id: str | None = None
    enabled: bool | None = None
    admin_password: str | None = None


class KeyCreate(Input):
    name: str


class SettingsPatch(Input):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    admin_password: str


class Chat(Input):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


def create_router(db, runner, users):
    router = APIRouter(prefix="/api")
    attempts = {}

    def require_auth(request: Request):
        current = db.get_session(request.cookies.get("webui_session"))
        if current is None:
            raise HTTPException(status_code=401, detail="需要登录")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), current["csrf_token"]):
                raise HTTPException(status_code=403, detail="CSRF 校验失败")
            check_origin(request)
        return current

    def require_admin(current=Depends(require_auth)):
        if not current["is_admin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return current

    async def recheck_admin(current, password):
        user = await users.verify(current["username"], password)
        if user is None or str(user.id) != current["id"] or not user.is_superuser:
            raise HTTPException(status_code=403, detail="管理员口令不正确")

    def check_origin(request):
        origin = request.headers.get("origin")
        if origin and (
            urlsplit(origin).netloc != request.headers.get("host")
            or urlsplit(origin).scheme not in ("http", "https")
        ):
            raise HTTPException(status_code=403, detail="请求来源不符")

    @router.post("/login")
    async def login(payload: Login, request: Request):
        check_origin(request)
        identity = (request.client.host if request.client else "local", payload.username.lower())
        now = time.monotonic()
        if len(attempts) >= 1024:
            for key, times in list(attempts.items()):
                if now - times[-1] >= 60:
                    attempts.pop(key, None)
            if identity not in attempts and len(attempts) >= 1024:
                raise HTTPException(status_code=429, detail="请稍后再试")
        recent = [when for when in attempts.get(identity, []) if now - when < 60]
        if len(recent) >= 5:
            raise HTTPException(status_code=429, detail="请稍后再试")
        user = await users.authenticate(payload.username, payload.password)
        if user is None:
            attempts[identity] = recent + [now]
            raise HTTPException(status_code=401, detail="账号或口令不正确")
        attempts.pop(identity, None)
        token, csrf = db.create_session(user.id, user.session_version)

        response = JSONResponse({"csrf_token": csrf, "user": public_user(user)})
        response.set_cookie(
            "webui_session",
            token,
            httponly=True,
            samesite="lax",
            secure=os.getenv("WEBUI_SECURE_COOKIES") == "1" or request.url.scheme == "https",
            max_age=43200,
        )
        return response

    @router.get("/session")
    def session(current=Depends(require_auth)):
        return {"csrf_token": current["csrf_token"], "user": {
            "id": current["id"], "username": current["username"], "is_admin": current["is_admin"],
        }}

    @router.post("/logout")
    def logout(request: Request, _=Depends(require_auth)):
        db.end_session(request.cookies.get("webui_session"))
        response = JSONResponse({"ok": True})
        response.delete_cookie("webui_session")
        return response

    @router.get("/users")
    async def list_accounts(_=Depends(require_admin)):
        return [public_user(user) for user in await users.list_users()]

    @router.post("/users", status_code=201)
    async def create_account(payload: AccountCreate, current=Depends(require_admin)):
        await recheck_admin(current, payload.admin_password)
        if payload.username == "admin":
            raise HTTPException(status_code=409, detail="账号已存在")
        try:
            user = await users.create(payload.username, payload.password)
        except UserAlreadyExists as exc:
            raise HTTPException(status_code=409, detail="账号已存在") from exc
        except InvalidPasswordException as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc
        return public_user(user)

    @router.patch("/users/me/password")
    async def change_own_password(payload: OwnPassword, current=Depends(require_auth)):
        user = await users.verify(current["username"], payload.current_password)
        if user is None or str(user.id) != current["id"]:
            raise HTTPException(status_code=403, detail="当前口令不正确")
        try:
            await users.update(current["id"], password=payload.new_password)
        except InvalidPasswordException as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc
        db.revoke_user_sessions(current["id"])
        response = JSONResponse({"ok": True})
        response.delete_cookie("webui_session")
        return response

    @router.patch("/users/{user_id}/status")
    async def change_account_status(user_id: str, payload: AccountStatus, current=Depends(require_admin)):
        await recheck_admin(current, payload.admin_password)
        try:
            user = await users.get(user_id)
            if user.is_superuser:
                raise HTTPException(status_code=403, detail="不能停用管理员账号")
            updated = await users.update(user_id, is_active=payload.is_active)
        except (UserNotExists, ValueError) as exc:
            raise HTTPException(status_code=404, detail="账号不存在") from exc
        db.revoke_user_sessions(user_id)
        return public_user(updated)

    @router.patch("/users/{user_id}/password")
    async def reset_account_password(user_id: str, payload: AccountPassword, current=Depends(require_admin)):
        await recheck_admin(current, payload.admin_password)
        try:
            user = await users.get(user_id)
            if user.is_superuser:
                raise HTTPException(status_code=403, detail="请使用修改本人密码功能")
            await users.update(user_id, password=payload.new_password)
        except (UserNotExists, ValueError) as exc:
            raise HTTPException(status_code=404, detail="账号不存在") from exc
        except InvalidPasswordException as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc
        db.revoke_user_sessions(user_id)
        return {"ok": True}

    @router.get("/hosts")
    def hosts(_=Depends(require_auth)):
        return db.list_hosts()

    @router.post("/hosts", status_code=201)
    def add_host(payload: HostCreate, _=Depends(require_admin)):
        return db.add_host(**payload.model_dump())

    @router.patch("/hosts/{host_id}")
    async def update_host(host_id: str, payload: HostPatch, current=Depends(require_admin)):
        changes = payload.model_dump(exclude_unset=True, exclude={"admin_password"})
        if any(
            key in changes for key in ("password", "ssh_key_id", "proxy_host_id")
        ):
            await recheck_admin(current, payload.admin_password or "")
        return db.update_host(host_id, **changes)

    @router.get("/ssh-keys")
    def keys(_=Depends(require_auth)):
        return db.list_keys()

    @router.post("/ssh-keys", status_code=201)
    def create_key(payload: KeyCreate, _=Depends(require_admin)):
        return db.create_key(payload.name)

    @router.get("/settings")
    def settings(_=Depends(require_admin)):
        return db.get_model_settings()

    @router.patch("/settings")
    async def update_settings(payload: SettingsPatch, current=Depends(require_admin)):
        await recheck_admin(current, payload.admin_password)
        current = db.model_credentials()
        if payload.base_url is not None or payload.model is not None or payload.api_key is not None:
            db.set_model_settings(
                payload.base_url if payload.base_url is not None else current["base_url"],
                payload.model if payload.model is not None else current["model"],
                payload.api_key,
            )
        return db.get_model_settings()

    @router.post("/chat", status_code=202)
    def chat(payload: Chat, _=Depends(require_auth)):
        if not db.get_model_settings()["base_url"]:
            raise HTTPException(status_code=409, detail="请先配置模型接口")
        if payload.conversation_id:
            if not db.has_conversation(payload.conversation_id):
                raise HTTPException(status_code=404, detail="会话不存在")
            conversation_id = payload.conversation_id
        else:
            conversation_id = db.create_conversation(payload.message)
        db.add_message(conversation_id, "user", payload.message)
        return {"conversation_id": conversation_id, "job_id": runner.enqueue(conversation_id)}

    @router.get("/conversations")
    def conversations(_=Depends(require_auth)):
        return db.list_conversations()

    @router.get("/conversations/{conversation_id}/messages")
    def conversation_messages(conversation_id: str, _=Depends(require_auth)):
        if not db.has_conversation(conversation_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        return db.get_messages(conversation_id)

    @router.get("/jobs")
    def jobs(_=Depends(require_auth)):
        return db.list_jobs()

    @router.get("/jobs/{job_id}")
    def job(job_id: str, _=Depends(require_auth)):
        result = db.get_job(job_id)
        if result is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return result

    @router.get("/jobs/{job_id}/events")
    def job_events(job_id: str, _=Depends(require_auth)):
        if db.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return StreamingResponse(
            runner.events(job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/reports")
    def reports(_=Depends(require_auth)):
        return db.list_reports()

    @router.get("/reports/{report_id}")
    def report(report_id: str, _=Depends(require_auth)):
        try:
            content = db.report_path(report_id).read_text(encoding="utf-8")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="报告不存在") from exc
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8")

    return router
