from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.responses import JSONResponse

from .agent import Agent
from .approvals import ApprovalMode
from .config import Config
from .context import ContextManager
from .provider import ProviderManager
from .routing import TOKEN_FACTORY_ROLES, CatalogUnavailable, ModelSelectionError
from .tools.commands import SandboxUnavailableError
from .workspace import Workspace


@dataclass
class Session:
    id: str
    agent: Agent | None
    created_at: float
    message_count: int = 0
    pending_approval: dict | None = None
    approval_future: asyncio.Future | None = None
    busy: bool = False


sessions: dict[str, Session] = {}

log = logging.getLogger(__name__)


def close_session(session: Session) -> None:
    if not session.agent:
        return
    shutdown = getattr(session.agent.tracer, "shutdown", None)
    try:
        if shutdown:
            shutdown()
    finally:
        session.agent.ws.discard()


async def dispose_session(session: Session) -> None:
    try:
        close = getattr(session.agent, "close", None)
        if close:
            await close()
    finally:
        close_session(session)


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routing_mode: Literal["pinned", "auto"]
    model: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_mode(self):
        if self.routing_mode == "auto" and self.model is not None:
            raise ValueError("Automatic mode cannot also pin a model")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=20000)
    selection: ModelSelection | None = None
    approval_mode: ApprovalMode = "manual"
    full_access_confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_approval_mode(self):
        if self.approval_mode == "full" and not self.full_access_confirmed:
            raise ValueError("Full tool approval requires explicit confirmation")
        return self


class ChatResponse(BaseModel):
    session_id: str
    response: str
    message_count: int
    routing: list[dict] = Field(default_factory=list)


async def selectable_models():
    config = Config.load()
    if config.default_provider != "nebius" or "nebius" not in config.providers:
        return {"provider": config.default_provider, "models": [], "auto_available": False,
                "configured_model": config.get_default_model(), "configured_mode": config.routing_mode, "roles": {}}
    manager = ProviderManager(config)
    try:
        identifiers = await manager.verified_model_ids("nebius")
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(503, "Live model catalog unavailable; configured deployment remains selectable") from error
    finally:
        await manager.close()
    roles = {**TOKEN_FACTORY_ROLES, **config.routing_models}
    return {"provider": "nebius", "models": sorted(model for model in identifiers if "nemotron" in model.lower()),
            "auto_available": all(model in identifiers for model in roles.values()),
            "configured_model": config.get_default_model(), "configured_mode": config.routing_mode, "roles": roles}


class SessionCreate(BaseModel):
    workspace: str = "."
    max_steps: int = Field(default=12, ge=1, le=20)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)


class ApprovalRequest(BaseModel):
    approval_id: str
    approved: bool


class SessionResponse(BaseModel):
    session_id: str
    workspace: str
    mode: str
    max_steps: int
    conversation_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    public = os.getenv("BIFANG_SERVER_HOST", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}
    if public and not os.getenv("BIFANG_SERVER_API_KEY"):
        raise RuntimeError("BIFANG_SERVER_API_KEY is required when the server binds to a non-loopback host")
    yield
    for session in sessions.values():
        try:
            if session.approval_future and not session.approval_future.done():
                session.approval_future.cancel()
            await dispose_session(session)
        except Exception as e:
            log.warning("Failed to discard workspace: %s", e)


app = FastAPI(title="Bifang API", version="0.3.0", lifespan=lifespan)
app.add_api_route("/models", selectable_models, methods=["GET"])

allowed_origins = [origin.strip() for origin in os.getenv(
    "BIFANG_CORS_ORIGINS",
    "http://localhost:1420,tauri://localhost,http://tauri.localhost",
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def authenticate_remote_requests(request: Request, call_next):
    public = os.getenv("BIFANG_SERVER_HOST", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}
    if public and request.url.path != "/health":
        expected = os.getenv("BIFANG_SERVER_API_KEY", "")
        supplied = request.headers.get("x-api-key", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "bifang"}


@app.post("/sessions", response_model=SessionResponse)
async def create_session(req: SessionCreate):
    cfg = Config.load()
    cfg.mode = "assist"
    cfg.approval_mode = "manual"
    cfg.max_steps = min(req.max_steps, cfg.max_steps)
    ws = Workspace.create(resolve_workspace(req.workspace, repository=cfg.use_worktree), cfg.use_worktree)
    session_id = uuid.uuid4().hex[:12]
    session = Session(id=session_id, agent=None, created_at=asyncio.get_running_loop().time())

    async def approve(action: str) -> bool:
        approval_id = secrets.token_urlsafe(12)
        future = asyncio.get_running_loop().create_future()
        session.pending_approval = {"approval_id": approval_id, "action": action}
        session.approval_future = future
        try:
            return await asyncio.wait_for(future, timeout=120)
        except TimeoutError:
            return False
        finally:
            session.pending_approval = None
            session.approval_future = None

    try:
        session.agent = Agent(cfg, ws, approve=approve)
        if req.conversation_id:
            if not cfg.enable_conversation_history:
                raise HTTPException(400, "Conversation history is disabled")
            await session.agent.context.initialize()
            cache = session.agent.context.conversation_cache.cache
            if cache.get_session(req.conversation_id) is None:
                raise HTTPException(404, "Conversation not found in this workspace")
        if cfg.enable_conversation_history:
            await session.agent.context.start_session(req.conversation_id)
    except BaseException:
        try:
            if session.agent:
                await session.agent.close()
        finally:
            ws.discard()
        raise
    sessions[session_id] = session
    return SessionResponse(
        session_id=session_id,
        workspace=str(ws.root),
        mode=cfg.mode,
        max_steps=cfg.max_steps,
        conversation_id=session.agent.context.get_current_session_id(),
    )


def resolve_workspace(value: str, repository: bool = False) -> Path:
    root_value = os.getenv("BIFANG_WORKSPACE_ROOT")
    host = os.getenv("BIFANG_SERVER_HOST", "127.0.0.1")
    allow_absolute = (
        os.getenv("BIFANG_ALLOW_ABSOLUTE_WORKSPACES") == "1"
        and host in {"127.0.0.1", "localhost", "::1"}
    )
    root = Path(root_value or Path.cwd()).resolve()
    requested = Path(value)
    if requested.is_absolute():
        if not allow_absolute:
            raise HTTPException(400, "Workspace must be relative to BIFANG_WORKSPACE_ROOT")
        target = requested.resolve()
    else:
        target = (root / requested).resolve()
        if target != root and root not in target.parents:
            raise HTTPException(403, "Workspace path escapes the configured root")
    if not target.exists() or not target.is_dir():
        raise HTTPException(400, "Workspace must be an existing directory")
    if repository:
        target = Workspace.resolve_source(target)
        if not allow_absolute and target != root and root not in target.parents:
            raise HTTPException(403, "Repository root escapes the configured workspace root")
    return target


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    session = sessions[session_id]
    if session.busy:
        raise HTTPException(409, "Wait for the current agent request to finish before discarding the session")
    sessions.pop(session_id)
    if session.approval_future and not session.approval_future.done():
        session.approval_future.cancel()
    try:
        await dispose_session(session)
    except Exception as e:
        log.warning("Failed to discard workspace: %s", e)
    return {"deleted": True}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    session = sessions[session_id]
    return {
        "session_id": session.id,
        "workspace": str(session.agent.ws.root) if session.agent else "",
        "mode": session.agent.cfg.mode if session.agent else "assist",
        "approval_mode": session.agent.cfg.approval_mode if session.agent else "manual",
        "max_steps": session.agent.cfg.max_steps if session.agent else 0,
        "message_count": session.message_count,
        "conversation_id": session.agent.context.get_current_session_id() if session.agent else None,
    }


@app.get("/conversations")
async def list_conversations(workspace: str = ".", limit: int = Query(20, ge=1, le=100),
                              offset: int = Query(0, ge=0)):
    cfg = Config.load()
    context = ContextManager(cfg, project_path=resolve_workspace(workspace, repository=cfg.use_worktree))
    try:
        if not context.conversation_cache:
            return []
        cache = context.conversation_cache.cache
        if not (cache.storage_path / "conversations.db").exists():
            return []
        await context.initialize()
        return cache.list_summaries(limit, offset)
    finally:
        await context.close()


@app.get("/sessions/{session_id}/history")
async def get_conversation_history(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    context = session.agent.context
    cache = context.conversation_cache
    record = cache.get_current_session() if cache else None
    return [{"turn_id": turn.turn_id, "user_message": turn.user_message,
             "assistant_response": turn.assistant_response, "timestamp": turn.timestamp,
             "status": turn.metadata.get("status", "completed"),
             "routing": [message["routing"] for message in turn.metadata.get("messages", [])
                         if isinstance(message.get("routing"), dict)]}
            for turn in record.turns] if record else []


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    raise HTTPException(410, "Create a session first, then use /sessions/{session_id}/chat")


@app.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def session_chat(session_id: str, req: ChatRequest):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    session.busy = True
    try:
        session.agent.cfg.approval_mode = req.approval_mode
        session.agent.audit.add("approval_mode", approval_mode=req.approval_mode)
        response = await session.agent.ask(req.prompt, selection=(
            req.selection.model_dump(exclude_none=True) if req.selection else None))
    except ModelSelectionError as error:
        raise HTTPException(400, str(error)) from error
    except CatalogUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except SandboxUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    finally:
        session.busy = False
    session.message_count += 1

    return ChatResponse(
        session_id=session.id,
        response=response,
        message_count=session.message_count,
        routing=list(session.agent.provider.requests),
    )


@app.get("/sessions/{session_id}/approval")
async def get_pending_approval(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return session.pending_approval or {"pending": False}


@app.post("/sessions/{session_id}/pause-auto-approval")
async def pause_automatic_approval(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    session.agent.cfg.approval_mode = "manual"
    session.agent.audit.add("approval_mode", approval_mode="manual", source="pause_auto_approval")
    return {"approval_mode": "manual", "effect": "Subsequent tool requests require manual review"}


@app.get("/sessions/{session_id}/tasks")
async def session_tasks(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return session.agent.tasks.snapshot()


@app.get("/sessions/{session_id}/diff")
async def get_session_diff(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return {"diff": session.agent.ws.diff()}


@app.post("/sessions/{session_id}/apply")
async def apply_session_changes(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.busy:
        raise HTTPException(409, "Wait for the current agent request to finish before applying changes")
    try:
        applied = session.agent.ws.apply()
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    return {"applied": applied}


@app.post("/sessions/{session_id}/approval")
async def resolve_pending_approval(session_id: str, req: ApprovalRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    pending = session.pending_approval
    future = session.approval_future
    if not pending or not future or pending["approval_id"] != req.approval_id or future.done():
        raise HTTPException(404, "Approval request not found or expired")
    future.set_result(req.approved)
    return {"resolved": True}


@app.get("/sessions")
async def list_sessions():
    return [
        {
            "session_id": s.id,
            "workspace": str(s.agent.ws.root) if s.agent else "",
            "mode": s.agent.cfg.mode if s.agent else "",
            "message_count": s.message_count,
        }
        for s in sessions.values()
    ]


def main():
    import uvicorn
    host = os.getenv("BIFANG_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("BIFANG_SERVER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
