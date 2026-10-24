from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from pathlib import Path

from rich.prompt import Confirm

from .approvals import INSPECTION_TOOLS, auto_approves_edit
from .audit import Audit
from .config import Config
from .context import ContextManager
from .mcp import MCPManager
from .memory import MemoryManager, MemoryStore, ProviderEmbedder
from .plugins import PluginManager
from .policy import Policy
from .provider import create_tiered_provider
from .routing import TaskClassifier, TaskType
from .tools import list_files, read_file, run_command, schemas, search
from .tools.builtin import get_builtin_tool, get_builtin_tools
from .tools.tasks import TaskPlan
from .tracing import NoOpTracer, PhoenixTracer, create_phoenix_tracer
from .workspace import Workspace

SYSTEM = """You are Bifang, an evidence-driven coding agent inside an isolated development box. Inspect before editing. Use typed tools. Keep changes minimal. Run relevant tests. Never claim commands, tests, or benchmarks succeeded without tool evidence. Stop when the task is complete and summarize changed files, verification, and remaining risks."""


class Agent:
    def __init__(
        self,
        cfg: Config,
        ws: Workspace,
        approve: Callable[[str], bool] | None = None,
        on_tool: Callable[[str], bool] | None = None,
    ):
        self.cfg = cfg
        self.ws = ws
        self.policy = Policy(ws.root, cfg.mode)
        self.provider = create_tiered_provider(cfg)
        self.mcp = MCPManager()
        self.plugins = PluginManager()
        self.memory = None
        if cfg.enable_memory:
            from .config import state_home
            project_id = hashlib.sha256(str(ws.source.resolve()).encode()).hexdigest()[:24]
            db_path = (Path(cfg.memory_db_path).expanduser() if cfg.memory_db_path else
                       state_home() / "memory" / f"{project_id}.db")
            store = MemoryStore(db_path)
            embedder = (ProviderEmbedder(self.provider, cfg.memory_embedding_model,
                                        cfg.memory_embedding_provider)
                        if cfg.memory_embedding_model else None)
            self.memory = MemoryManager(store, embedder)

        # Context management
        self.context = ContextManager(cfg, self.provider, project_path=ws.source)
        self._request_lock = asyncio.Lock()
        self.tasks = TaskPlan()

        # Tracing
        self.tracer: NoOpTracer | PhoenixTracer = NoOpTracer()
        if cfg.enable_tracing:
            self.tracer = create_phoenix_tracer(
                service_name="bifang-agent",
                endpoint=cfg.tracing_endpoint,
            )

        self.audit = Audit(ws.root)
        self.approve = approve or (lambda text: Confirm.ask(text))
        self.on_tool = on_tool
        self.context.add_message({"role": "system", "content": SYSTEM})
        self.messages = self.context.get_messages()
        self._step_count = 0
        self._mcp_started = False
        self._plugins_started = False

    async def _approval_granted(self, prompt: str) -> bool:
        result = self.approve(prompt)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def _tool_approval(self, name: str, args: dict) -> bool:
        if self.cfg.approval_mode == "full":
            approved, source = True, "full"
        elif self.cfg.approval_mode == "auto" and name == "write_file" and auto_approves_edit(
            self.ws.root, self.ws.source, self.ws.isolated, args
        ):
            approved, source = True, "auto_workspace_edit"
        else:
            if name == "write_file":
                prompt = f"Allow Bifang to write {args['path']}?"
            elif name == "run_command":
                prompt = f"Run command?\n{args['command']}"
            elif name == "code_execute":
                prompt = "Allow Bifang to execute generated Python code?"
            else:
                prompt = f"Allow Bifang to use {name}?\n{json.dumps(args, ensure_ascii=False)}"
            approved, source = await self._approval_granted(prompt), "manual"
        self.audit.add("tool_approval", name=name, approval_mode=self.cfg.approval_mode,
                       source=source, approved=approved)
        return approved

    async def tool(self, name: str, args: dict) -> str:
        with self.tracer.span(
            "tool.execute",
            attributes={"tool": name, "argument_names": ",".join(sorted(args)),
                        "openinference.span.kind": "TOOL"},
        ) as span:
            return await self._execute_tool(name, args, span)

    async def _execute_tool(self, name: str, args: dict, span) -> str:
        self.audit.add("tool_request", name=name, args=args)
        if self.on_tool:
            self.on_tool(name, args)

        inspection = name in INSPECTION_TOOLS and not self.plugins.get_tool(name)
        if not inspection:
            if self.cfg.mode == "observe":
                return "DENIED: observe mode"
            if name == "write_file":
                self.policy.path(args["path"])
            if name == "run_command":
                decision = self.policy.command(args["command"])
                if not decision.allowed:
                    return f"DENIED: {decision.reason}"
            if not await self._tool_approval(name, args):
                return "DENIED by user"

        if name.startswith("mcp_"):
            try:
                result = await self.mcp.call_tool(name, args)
                self.audit.add("tool_result", name=name, result=str(result)[:100000])
                return json.dumps(result) if not isinstance(result, str) else result
            except Exception as e:
                error_msg = f"MCP tool error: {e}"
                self.audit.add("tool_result", name=name, result=error_msg)
                span.set_status("error")
                span.set_attribute("error.type", type(e).__name__)
                return error_msg

        plugin_tool = self.plugins.get_tool(name)
        if plugin_tool:
            try:
                result = await plugin_tool(**args)
                self.audit.add("tool_result", name=name, result=str(result)[:100000])
                return result
            except Exception as e:
                error_msg = f"Plugin tool error: {e}"
                self.audit.add("tool_result", name=name, result=error_msg)
                span.set_status("error")
                span.set_attribute("error.type", type(e).__name__)
                return error_msg

        if name == "memory_recall":
            if not self.memory:
                return "Memory not enabled"
            query = args.get("query", "")
            limit = args.get("limit", 5)
            memories = await self.memory.recall(query, limit=limit)
            return "\n".join([f"- {m.content}" for m in memories])

        if name == "memory_store":
            if not self.memory:
                return "Memory not enabled"
            content = args.get("content", "")
            importance = args.get("importance", 1.0)
            metadata = args.get("metadata", {})
            mem_id = await self.memory.remember(content, metadata=metadata, importance=importance)
            return f"Stored memory: {mem_id}"

        if name == "memory_context":
            if not self.memory:
                return "Memory not enabled"
            query = args.get("query", "")
            max_tokens = args.get("max_tokens", 2000)
            context = await self.memory.get_context(query, max_tokens=max_tokens)
            return context

        builtin_tool = get_builtin_tool(name)
        if builtin_tool:
            try:
                if name in {"todo_write", "todo_read"}:
                    result = await builtin_tool(state=self.tasks, **args)
                else:
                    result = await builtin_tool(**args)
                self.audit.add("tool_result", name=name, result=str(result)[:100000])
                return result
            except Exception as e:
                error_msg = f"Builtin tool error: {e}"
                self.audit.add("tool_result", name=name, result=error_msg)
                span.set_status("error")
                span.set_attribute("error.type", type(e).__name__)
                return error_msg

        if name == "list_files":
            result = list_files(self.ws.root, args.get("limit", 500))
        elif name == "read_file":
            result = read_file(self.policy, args["path"], args.get("start", 1), args.get("end", 400))
        elif name == "search":
            result = search(self.ws.root, args["query"])
        elif name == "git_diff":
            result = self.ws.diff() or "No changes"
        elif name == "write_file":
            p = self.policy.path(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            result = f"Wrote {args['path']}"
        elif name == "run_command":
            d = self.policy.command(args["command"])
            if not d.allowed:
                result = f"DENIED: {d.reason}"
            else:
                result = json.dumps(await run_command(self.policy, args["command"], args.get("timeout", self.cfg.timeout), self.cfg.use_bwrap))
        else:
            result = "Unknown tool"

        self.audit.add("tool_result", name=name, result=result[:100000])
        return result

    def _get_tools_schema(self) -> list[dict]:
        """Get combined schema including MCP, plugin, memory, and builtin tools."""
        base_schemas = schemas()
        mcp_tools = self.mcp.get_tools_for_llm()
        plugin_schemas = self.plugins.get_all_schemas()
        builtin_schemas = get_builtin_tools()

        # Add memory tools if enabled
        memory_schemas = []
        if self.memory:
            memory_schemas = [
                {
                    "type": "function",
                    "function": {
                        "name": "memory_recall",
                        "description": "Recall relevant memories from long-term storage",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query for memories"},
                                "limit": {"type": "integer", "description": "Maximum memories to return", "default": 5},
                            },
                            "required": ["query"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "memory_store",
                        "description": "Store a new memory for future recall",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "Memory content"},
                                "importance": {"type": "number", "description": "Importance weight (0.0-2.0)", "default": 1.0},
                                "metadata": {"type": "object", "description": "Additional metadata", "default": {}},
                            },
                            "required": ["content"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "memory_context",
                        "description": "Get relevant context from memories for a query",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Query to find relevant context for"},
                                "max_tokens": {"type": "integer", "description": "Maximum tokens in context", "default": 2000},
                            },
                            "required": ["query"],
                        },
                    },
                },
            ]

        return base_schemas + mcp_tools + plugin_schemas + memory_schemas + builtin_schemas

    async def _ensure_services_started(self) -> None:
        """Ensure MCP servers and plugins are started."""
        if not self._mcp_started and self.cfg.mcp_servers:
            for server_config in self.cfg.mcp_servers:
                self.mcp.add_server(server_config)
            await self.mcp.start_all()
            self._mcp_started = True

        if not self._plugins_started:
            await self.plugins.discover_and_load()
            await self.plugins.load_entry_points()
            await self.plugins.initialize_all()
            self._plugins_started = True

    @asynccontextmanager
    async def _conversation_request(self):
        async with self._request_lock:
            if self.cfg.enable_conversation_history and not self.context.get_current_session_id():
                await self.context.start_session()
            self.context.begin_request()
            self.provider.requests.clear()
            try:
                with self.tracer.span("agent.request", attributes={"openinference.span.kind": "AGENT"}):
                    yield
            except BaseException as error:
                status = "cancelled" if isinstance(error, (asyncio.CancelledError, GeneratorExit)) else "failed"
                self.context.abort_pending(status)
                raise
            else:
                self.context.finish_pending("stopped")

    async def ask(self, prompt: str, on_text: Callable[[str], None] | None = None,
                  task_type: TaskType | None = None, *, selection: dict | None = None) -> str:
        async with self._conversation_request():
            return await self._ask(prompt, on_text, task_type, selection)

    async def _ask(self, prompt: str, on_text: Callable[[str], None] | None = None, task_type: TaskType | None = None,
                   selection: dict | None = None) -> str:
        """Ask the agent a question (non-streaming)."""
        await self._ensure_services_started()

        self.audit.add("user", content=prompt)
        self.context.add_message({"role": "user", "content": prompt})

        for _ in range(self.cfg.max_steps):
            self._step_count += 1

            # Check if context needs summarization
            if self.context.should_summarize():
                await self.context.maybe_summarize()
                self.messages = self.context.get_messages()

            # Determine task type if not provided
            if task_type is None:
                task_type = TaskClassifier.classify(prompt, {"files": list(self.ws.root.glob("**/*"))})

            with self.tracer.span(
                "llm.complete",
                attributes={
                    "task_type": task_type.value,
                    "openinference.span.kind": "LLM",
                },
            ) as span:
                msg = await self.provider.complete(
                    self.messages,
                    tools=self._get_tools_schema(),
                    task_type=task_type,
                    **(selection or {}),
                )
                usage = msg.get("usage") or {}
                for key in ("provider", "reported_model"):
                    if msg.get(key):
                        span.set_attribute(key, msg[key])
                if msg.get("model"):
                    span.set_attribute("requested_model", msg["model"])
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if key in usage:
                        span.set_attribute(f"usage.{key}", usage[key])
            self.context.add_message(msg)

            calls = msg.get("tool_calls") or []
            if not calls:
                text = msg.get("content") or ""
                self.audit.add("assistant", content=text)
                if on_text:
                    on_text(text)
                return text

            for call in calls:
                try:
                    args = json.loads(call["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                result = await self.tool(call["function"]["name"], args)
                tool_msg = {"role": "tool", "tool_call_id": call["id"], "content": result}
                self.context.add_message(tool_msg)

        return "Stopped after maximum agent steps. Inspect /diff and the transcript."

    async def ask_stream(self, prompt: str, on_text: Callable[[str], None] | None = None,
                         on_tool_start=None, on_tool_end=None,
                         task_type: TaskType | None = None) -> AsyncIterator[str]:
        async with self._conversation_request():
            async with aclosing(self._ask_stream(prompt, on_text, on_tool_start, on_tool_end, task_type)) as stream:
                async for chunk in stream:
                    yield chunk

    async def _ask_stream(
        self,
        prompt: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
        task_type: TaskType | None = None,
    ) -> AsyncIterator[str]:
        """Ask the agent a question with streaming response."""
        await self._ensure_services_started()

        self.audit.add("user", content=prompt)
        self.context.add_message({"role": "user", "content": prompt})

        for _ in range(self.cfg.max_steps):
            self._step_count += 1

            # Check if context needs summarization
            if self.context.should_summarize():
                await self.context.maybe_summarize()
                self.messages = self.context.get_messages()

            # Determine task type if not provided
            if task_type is None:
                task_type = TaskClassifier.classify(prompt, {"files": list(self.ws.root.glob("**/*"))})

            # Stream the model response
            accumulated_content = ""
            accumulated_tool_calls = []

            with self.tracer.span("llm.stream", attributes={"openinference.span.kind": "LLM",
                                                          "task_type": task_type.value}) as span:
                async with aclosing(self.provider.complete_stream(
                    self.messages, tools=self._get_tools_schema(), task_type=task_type,
                )) as completion:
                    async for chunk in completion:
                        if chunk.get("content"):
                            accumulated_content += chunk["content"]
                            if on_text:
                                on_text(chunk["content"])
                            yield chunk["content"]

                        if chunk.get("tool_calls"):
                            accumulated_tool_calls.extend(chunk["tool_calls"])
                if self.provider.requests:
                    receipt = self.provider.requests[-1]
                    for key in ("provider", "requested_model", "reported_model"):
                        if receipt.get(key):
                            span.set_attribute(key, receipt[key])
                    for key, value in receipt.get("usage", {}).items():
                        span.set_attribute(f"usage.{key}", value)

            # Create assistant message
            assistant_msg = {"role": "assistant", "content": accumulated_content}
            if self.provider.requests:
                assistant_msg["routing"] = dict(self.provider.requests[-1])
            if accumulated_tool_calls:
                assistant_msg["tool_calls"] = accumulated_tool_calls
            self.context.add_message(assistant_msg)

            if not accumulated_tool_calls:
                self.audit.add("assistant", content=accumulated_content)
                return

            # Execute tool calls
            for call in accumulated_tool_calls:
                if on_tool_start:
                    on_tool_start(call["function"]["name"], json.loads(call["function"]["arguments"]) if call["function"]["arguments"] else {})

                try:
                    args = json.loads(call["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                result = await self.tool(call["function"]["name"], args)

                if on_tool_end:
                    on_tool_end(call["function"]["name"], result)

                tool_msg = {"role": "tool", "tool_call_id": call["id"], "content": result}
                self.context.add_message(tool_msg)

        yield "Stopped after maximum agent steps. Inspect /diff and the transcript."

    async def close(self):
        """Clean up resources."""
        try:
            await self.context.close()
            await self.provider.close()
            await self.mcp.close_all()
            await self.plugins.shutdown_all()
        finally:
            if self.memory:
                self.memory.store.close()
            shutdown = getattr(self.tracer, "shutdown", None)
            if shutdown:
                await asyncio.to_thread(shutdown)
