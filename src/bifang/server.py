from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.responses import JSONResponse

from .agent import Agent
from .approvals import ApprovalMode
from .config import Config
from .context import ContextManager
from .implementation import EngineeringWorkflow
from .provider import ProviderManager
from .review_workflow import ReviewWorkflow
from .routing import TOKEN_FACTORY_ROLES, CatalogUnavailable, ModelSelectionError
from .model_ids import PROVIDER_ROLES
from .tools.commands import SandboxUnavailableError
from .vision import (
    MAX_REQUEST_BYTES,
    VisionAttachments,
    VisionError,
    VisionRequest,
    VisionUnavailable,
    discover_vision_models,
    inspect_images,
    prepare_image,
)
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
    review: ReviewWorkflow | None = None
    engineering: EngineeringWorkflow | None = None
    vision_task: asyncio.Task | None = None
    vision_request_id: str | None = None
    vision_cancelled: deque[str] = field(default_factory=lambda: deque(maxlen=64))


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
        if session.vision_task and not session.vision_task.done():
            session.vision_task.cancel()
            await asyncio.gather(session.vision_task, return_exceptions=True)
        if session.review:
            await session.review.cancel()
        if session.engineering:
            await session.engineering.close()
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


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4000)
    inference_confirmed: bool = Field(default=False, strict=True)


class CandidateRequest(ReviewRequest):
    files: list[str] = Field(default_factory=list, max_length=128)
    writable: list[str] = Field(default_factory=list, max_length=128)


class CandidateCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: list[str] = Field(min_length=1, max_length=64)
    timeout: int = Field(default=30, ge=1, le=60, strict=True)
    confirmed: bool = Field(default=False, strict=True)


class CandidateStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool = Field(default=False, strict=True)


async def selectable_models():
    """Live model catalog across every configured provider.

    The legacy top-level keys (provider/models/roles/...) describe the DEFAULT
    provider so existing clients keep working. The 'providers' map carries the
    full catalog with per-provider roles; ids from non-default providers are
    'provider::model' composites that the completion router splits.
    """
    config = Config.load()
    if not config.providers:
        return {"provider": "", "models": [], "auto_available": False,
                "configured_model": None, "configured_mode": config.routing_mode,
                "roles": {}, "providers": {}}
    default_provider = config.default_provider if config.default_provider in config.providers else next(iter(config.providers))
    manager = ProviderManager(config)
    try:
        payload_providers = {}
        for name in config.providers:
            roles = dict(PROVIDER_ROLES.get(name, {}))
            if name == default_provider:
                roles = {**roles, **config.routing_models}
            try:
                identifiers = await manager.verified_model_ids(name)
                live_name = name
            except (httpx.HTTPError, ValueError):
                identifiers = None
            if identifiers:
                models = sorted(identifiers)
                auto_available = all(model in identifiers for model in roles.values()) if roles else False
            else:
                models = []
                auto_available = False
                try:
                    provider = manager.registry.get(name)
                    fallback = [m.id for m in (await provider.list_models())] if provider else []
                except Exception:
                    fallback = []
                models = fallback
                live_name = name
            payload_providers[name] = {
                "models": models[:4096],
                "roles": roles,
                "auto_available": auto_available,
                "live": True if identifiers else False,
            }
    finally:
        await manager.close()
    default_entry = payload_providers.get(default_provider, {"models": [], "roles": {}, "auto_available": False})
    tagged_models = []
    for name, entry in payload_providers.items():
        if name == default_provider:
            tagged_models.extend(entry["models"])
        else:
            tagged_models.extend(f"{name}::{model}" for model in entry["models"] if "::" not in model)
    return {"provider": default_provider, "models": sorted(tagged_models)[:8192],
            "auto_available": default_entry["auto_available"],
            "configured_model": config.get_default_model(default_provider),
            "configured_mode": config.routing_mode,
            "roles": default_entry["roles"],
            "providers": payload_providers}


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
    if (public or os.getenv("BIFANG_SERVER_REQUIRE_AUTH") == "1") and not os.getenv("BIFANG_SERVER_API_KEY"):
        raise RuntimeError("BIFANG_SERVER_API_KEY is required for authenticated serving")
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
    "http://localhost:1420,tauri://localhost,http://tauri.localhost,https://tauri.localhost",
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
    preflight = request.method == "OPTIONS" and "access-control-request-method" in request.headers
    if (public or os.getenv("BIFANG_SERVER_REQUIRE_AUTH") == "1") and request.url.path != "/health" and not preflight:
        expected = os.getenv("BIFANG_SERVER_API_KEY", "")
        supplied = request.headers.get("x-api-key", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "bifang"}


@app.get("/vision/models")
async def vision_models(provider: Literal["nebius", "nvidia"] | None = None):
    try:
        config = Config.load()
        available = [name for name in ("nebius", "nvidia") if name in config.providers]
        selected = provider or (config.default_provider if config.default_provider in available else next(iter(available), None))
        async with asyncio.timeout(25):
            models = await discover_vision_models(config, provider=selected) if selected else []
        return {"provider": selected, "providers": available, "models": models}
    except (httpx.HTTPError, ValueError, VisionUnavailable, TimeoutError):
        raise HTTPException(503, "Visual model capabilities unavailable; refresh before sharing images") from None


async def visual_request_body(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Visual request exceeds the six-megabyte limit")
        raw.extend(chunk)
    try:
        return json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Invalid visual-review JSON") from None


@app.post("/vision/prepare")
async def prepare_visual_attachments(request: Request):
    raw = await visual_request_body(request)
    try:
        attachments = VisionAttachments.model_validate(raw)
        prepared = [await asyncio.to_thread(prepare_image, image.data_url) for image in attachments.images]
        return {"images": [{**metadata, "data_url": data_url} for data_url, metadata in prepared]}
    except (ValidationError, VisionError):
        raise HTTPException(422, "Use up to two still PNG, JPEG or WebP images, each below 2 MB and four million pixels") from None


@app.post("/sessions/{session_id}/vision")
async def session_vision(session_id: str, request: Request):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    raw = await visual_request_body(request)
    try:
        selected = VisionRequest.model_validate(raw)
    except (ValueError, ValidationError):
        raise HTTPException(422, "Invalid visual-review request; use bounded inline images and an exact model") from None
    if not selected.sharing_confirmed:
        raise HTTPException(400, "Confirm image sharing with the selected provider")
    if selected.request_id in session.vision_cancelled:
        raise HTTPException(409, "Visual review cancelled before inference")
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    session.busy = True
    session.vision_request_id = selected.request_id
    task = asyncio.create_task(inspect_images(session.agent.cfg, selected))
    session.vision_task = task
    try:
        result = await task
        session.agent.audit.add("vision_review", receipt=result["receipt"], images=result["images"])
        return result
    except VisionError:
        raise HTTPException(400, "Choose valid bounded images and a currently listed vision model") from None
    except (httpx.HTTPError, VisionUnavailable):
        raise HTTPException(502, "Visual provider unavailable; no model substitution or tools were used") from None
    except TimeoutError:
        raise HTTPException(504, "Visual review timed out; no automatic retry was made") from None
    except asyncio.CancelledError:
        raise HTTPException(409, "Visual review cancelled") from None
    finally:
        if session.vision_task is task:
            session.vision_task = None
            session.vision_request_id = None
            session.busy = False


@app.post("/sessions/{session_id}/vision/cancel")
async def cancel_session_vision(session_id: str, request_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$")):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if request_id:
        session.vision_cancelled.append(request_id)
        if session.vision_request_id != request_id:
            return {"cancelled": True, "pending": True}
    task = session.vision_task
    if not task or task.done():
        return {"cancelled": False}
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    if session.vision_task is task:
        session.vision_task = None
        session.vision_request_id = None
        session.busy = False
    return {"cancelled": True}


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


@app.post("/sessions/{session_id}/review")
async def start_review(session_id: str, req: ReviewRequest):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    if not req.inference_confirmed:
        raise HTTPException(400, "Confirm up to eight model requests before starting two read-only workers")
    review = ReviewWorkflow(session.agent, req.prompt)
    session.review = review
    session.busy = True

    async def execute():
        try:
            await review.run()
        finally:
            session.busy = False

    review.task = asyncio.create_task(execute())
    return review.snapshot()


@app.get("/sessions/{session_id}/review")
async def review_status(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return session.review.snapshot() if session.review else {"status": "idle", "workers": []}


@app.post("/sessions/{session_id}/review/cancel")
async def cancel_review(session_id: str):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.review:
        active = session.review.task and not session.review.task.done()
        await session.review.cancel()
        if active:
            session.busy = False
    return session.review.snapshot() if session.review else {"status": "idle", "workers": []}


def candidate_session(session_id: str) -> Session:
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    return session


def launch_candidate(session: Session, workflow: EngineeringWorkflow, operation):
    session.busy = True

    async def execute():
        try:
            await operation()
        finally:
            session.busy = False

    workflow.task = asyncio.create_task(execute())


@app.post("/sessions/{session_id}/candidate")
async def start_candidate(session_id: str, req: CandidateRequest):
    session = candidate_session(session_id)
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    if not req.inference_confirmed:
        raise HTTPException(400, "Confirm up to six model steps before starting the isolated implementer")
    try:
        workflow = EngineeringWorkflow(session.agent, req.files, req.writable, req.prompt)
    except (ValueError, OSError):
        raise HTTPException(422, "Select existing UTF-8 source files or explicit output paths within the path and size budget") from None
    session.busy = True
    try:
        if session.engineering:
            await session.engineering.close()
        session.engineering = workflow
        launch_candidate(session, workflow, workflow.run)
    except BaseException:
        session.busy = False
        await workflow.close()
        raise
    return workflow.snapshot()


@app.get("/sessions/{session_id}/candidate")
async def candidate_status(session_id: str):
    session = candidate_session(session_id)
    return session.engineering.snapshot() if session.engineering else {"status": "idle"}


@app.post("/sessions/{session_id}/candidate/cancel")
async def cancel_candidate(session_id: str):
    session = candidate_session(session_id)
    if session.engineering:
        active = session.engineering.task and not session.engineering.task.done()
        await session.engineering.cancel()
        if active:
            session.busy = False
    return session.engineering.snapshot() if session.engineering else {"status": "idle"}


@app.get("/sessions/{session_id}/candidate/patch")
async def candidate_patch(session_id: str):
    session = candidate_session(session_id)
    if session.busy:
        raise HTTPException(409, "Wait for the current operation before reviewing the candidate patch")
    if not session.engineering:
        raise HTTPException(404, "No candidate")
    return {"patch": session.engineering.candidate.patch(), **session.engineering.candidate.describe()}


@app.post("/sessions/{session_id}/candidate/check")
async def check_candidate(session_id: str, req: CandidateCheckRequest):
    session = candidate_session(session_id)
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    if not req.confirmed:
        raise HTTPException(400, "Confirm the exact verification argument vector")
    workflow = session.engineering
    if not workflow or workflow.status not in {"ready", "verified", "check_failed"}:
        raise HTTPException(409, "Finish the isolated implementation before running checks")
    workflow.status = "checking"
    launch_candidate(session, workflow, lambda: workflow.check(req.command, req.timeout))
    return workflow.snapshot()


@app.post("/sessions/{session_id}/candidate/stage")
async def stage_candidate(session_id: str, req: CandidateStageRequest):
    session = candidate_session(session_id)
    if session.busy:
        raise HTTPException(409, "A request is already running for this session")
    if not req.confirmed:
        raise HTTPException(400, "Confirm the reviewed patch before staging")
    if not session.engineering:
        raise HTTPException(404, "No candidate")
    try:
        staged = session.engineering.stage(req.candidate_sha256)
        return {**session.engineering.snapshot(), **staged}
    except (ValueError, OSError, TimeoutError):
        raise HTTPException(409, "Candidate is stale, unverified, conflicting or not targeting an isolated worktree") from None


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
    patch = session.agent.ws.diff()
    return {"diff": patch, "patch_sha256": hashlib.sha256(patch.encode()).hexdigest()}


class ApplyPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@app.post("/sessions/{session_id}/apply")
async def apply_session_changes(session_id: str, req: ApplyPatchRequest):
    session = sessions.get(session_id)
    if not session or not session.agent:
        raise HTTPException(404, "Session not found")
    if session.busy:
        raise HTTPException(409, "Wait for the current agent request to finish before applying changes")
    try:
        applied = session.agent.ws.apply(expected_patch_sha256=req.patch_sha256)
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
    if os.getenv("BIFANG_DESKTOP_BOOTSTRAP") == "1":
        from bifang.desktop_bootstrap import serve_desktop
        serve_desktop(app)
        return
    import uvicorn
    host = os.getenv("BIFANG_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("BIFANG_SERVER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
