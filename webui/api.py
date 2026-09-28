import hmac
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    password: str


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
    new_password: str | None = None


class Chat(Input):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


def create_router(db, runner):
    router = APIRouter(prefix="/api")
    attempts = {}

    def require_auth(request: Request):
        csrf = db.get_session(request.cookies.get("webui_session"))
        if csrf is None:
            raise HTTPException(status_code=401, detail="需要登录")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                raise HTTPException(status_code=403, detail="CSRF 校验失败")
            check_origin(request)
        return csrf

    def check_origin(request):
        origin = request.headers.get("origin")
        if origin and (
            urlsplit(origin).netloc != request.headers.get("host")
            or urlsplit(origin).scheme not in ("http", "https")
        ):
            raise HTTPException(status_code=403, detail="请求来源不符")

    @router.post("/login")
    def login(payload: Login, request: Request):
        check_origin(request)
        identity = request.client.host if request.client else "local"
        recent = [when for when in attempts.get(identity, []) if time.monotonic() - when < 60]
        if len(recent) >= 5:
            raise HTTPException(status_code=429, detail="请稍后再试")
        if not db.verify_admin(payload.password):
            attempts[identity] = recent + [time.monotonic()]
            raise HTTPException(status_code=401, detail="口令不正确")
        attempts.pop(identity, None)
        token, csrf = db.create_session()
        from fastapi.responses import JSONResponse

        response = JSONResponse({"csrf_token": csrf})
        response.set_cookie(
            "webui_session",
            token,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            max_age=43200,
        )
        return response

    @router.get("/session", dependencies=[Depends(require_auth)])
    def session(csrf: str = Depends(require_auth)):
        return {"csrf_token": csrf}

    @router.post("/logout")
    def logout(request: Request, _=Depends(require_auth)):
        from fastapi.responses import JSONResponse

        db.end_session(request.cookies.get("webui_session"))
        response = JSONResponse({"ok": True})
        response.delete_cookie("webui_session")
        return response

    @router.get("/hosts")
    def hosts(_=Depends(require_auth)):
        return db.list_hosts()

    @router.post("/hosts", status_code=201)
    def add_host(payload: HostCreate, _=Depends(require_auth)):
        return db.add_host(**payload.model_dump())

    @router.patch("/hosts/{host_id}")
    def update_host(host_id: str, payload: HostPatch, _=Depends(require_auth)):
        changes = payload.model_dump(exclude_unset=True, exclude={"admin_password"})
        if any(
            key in changes for key in ("password", "ssh_key_id", "proxy_host_id")
        ) and not db.verify_admin(payload.admin_password or ""):
            raise HTTPException(status_code=403, detail="请再次验证管理员口令")
        return db.update_host(host_id, **changes)

    @router.get("/ssh-keys")
    def keys(_=Depends(require_auth)):
        return db.list_keys()

    @router.post("/ssh-keys", status_code=201)
    def create_key(payload: KeyCreate, _=Depends(require_auth)):
        return db.create_key(payload.name)

    @router.get("/settings")
    def settings(_=Depends(require_auth)):
        return db.get_model_settings()

    @router.patch("/settings")
    def update_settings(payload: SettingsPatch, request: Request, _=Depends(require_auth)):
        if not db.verify_admin(payload.admin_password):
            raise HTTPException(status_code=403, detail="管理员口令不正确")
        current = db.model_credentials()
        if payload.base_url is not None or payload.model is not None or payload.api_key is not None:
            db.set_model_settings(
                payload.base_url if payload.base_url is not None else current["base_url"],
                payload.model if payload.model is not None else current["model"],
                payload.api_key,
            )
        if payload.new_password is not None:
            db.change_admin_password(payload.admin_password, payload.new_password)
            from fastapi.responses import JSONResponse

            response = JSONResponse(db.get_model_settings())
            response.delete_cookie("webui_session")
            return response
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
