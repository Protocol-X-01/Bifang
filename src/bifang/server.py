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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .agent import Agent
from .config import Config
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


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)


class ChatResponse(BaseModel):
    session_id: str
    response: str
    message_count: int


class SessionCreate(BaseModel):
    workspace: str = "."
    max_steps: int = Field(default=12, ge=1, le=20)


class ApprovalRequest(BaseModel):
    approval_id: str
    approved: bool


class SessionResponse(BaseModel):
    session_id: str
    workspace: str
    mode: str
    max_steps: int


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
            close_session(session)
        except Exception as e:
            log.warning("Failed to discard workspace: %s", e)


app = FastAPI(title="Bifang API", version="0.3.0", lifespan=lifespan)

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
    cfg.max_steps = min(req.max_steps, cfg.max_steps)
    ws = Workspace.create(resolve_workspace(req.workspace), cfg.use_worktree)
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

    session.agent = Agent(cfg, ws, approve=approve)
    sessions[session_id] = session
    return SessionResponse(
        session_id=session_id,
        workspace=str(ws.root),
        mode=cfg.mode,
        max_steps=cfg.max_steps,
    )


def resolve_workspace(value: str) -> Path:
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
        close_session(session)
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
        "max_steps": session.agent.cfg.max_steps if session.agent else 0,
        "message_count": session.message_count,
    }


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
        response = await session.agent.ask(req.prompt)
    finally:
        session.busy = False
    session.message_count += 1

    return ChatResponse(
        session_id=session.id,
        response=response,
        message_count=session.message_count,
    )


@app.get("/sessions/{session_id}/approval")
async def get_pending_approval(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return session.pending_approval or {"pending": False}


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
