from __future__ import annotations

import json
import inspect
from typing import Callable, AsyncIterator
from rich.prompt import Confirm

from .audit import Audit
from .config import Config
from .context import ContextManager, create_summarizer
from .mcp import MCPManager
from .memory import MemoryManager, MemoryStore, MemoryEntry, create_simple_embedder
from .plugins import PluginManager
from .policy import Policy
from .provider import ProviderManager, create_tiered_provider, TieredProviderManager
from .tools import list_files, read_file, run_command, schemas, search
from .tools.builtin import get_builtin_tool, get_builtin_tools
from .tracing import PhoenixTracer, NoOpTracer, create_phoenix_tracer
from .workspace import Workspace
from .routing import TaskClassifier, TaskType


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
            db_path = state_home() / "memory.db"
            store = MemoryStore(db_path)
            embedder = create_simple_embedder() if cfg.enable_memory else None
            self.memory = MemoryManager(store, embedder)

        # Context management
        self.context = ContextManager(cfg, self.provider)

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
        self.messages = [{"role": "system", "content": SYSTEM}]
        self._step_count = 0
        self._mcp_started = False
        self._plugins_started = False

    async def _approval_granted(self, prompt: str) -> bool:
        result = self.approve(prompt)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def tool(self, name: str, args: dict) -> str:
        self.audit.add("tool_request", name=name, args=args)
        if self.on_tool:
            self.on_tool(name, args)

        with self.tracer.span(
            f"tool.{name}",
            attributes={"tool": name, "argument_names": ",".join(sorted(args))},
        ) as span:
            # Handle MCP tools
            if name.startswith("mcp_"):
                try:
                    result = await self.mcp.call_tool(name, args)
                    self.audit.add("tool_result", name=name, result=str(result)[:100000])
                    return json.dumps(result) if not isinstance(result, str) else result
                except Exception as e:
                    error_msg = f"MCP tool error: {e}"
                    self.audit.add("tool_result", name=name, result=error_msg)
                    span.set_attribute("error", True)
                    return error_msg

            # Handle plugin tools
            plugin_tool = self.plugins.get_tool(name)
            if plugin_tool:
                try:
                    result = await plugin_tool(**args)
                    self.audit.add("tool_result", name=name, result=str(result)[:100000])
                    return result
                except Exception as e:
                    error_msg = f"Plugin tool error: {e}"
                    self.audit.add("tool_result", name=name, result=error_msg)
                    span.set_attribute("error", True)
                    return error_msg

            # Handle memory tools
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

            # Handle builtin tools
            builtin_tool = get_builtin_tool(name)
            if builtin_tool:
                if name == "code_execute":
                    if self.cfg.mode == "observe":
                        return "DENIED: observe mode"
                    if self.cfg.mode == "assist" and not await self._approval_granted(
                        "Allow Bifang to execute generated Python code?"
                    ):
                        return "DENIED by user"
                try:
                    result = await builtin_tool(**args)
                    self.audit.add("tool_result", name=name, result=str(result)[:100000])
                    return result
                except Exception as e:
                    error_msg = f"Builtin tool error: {e}"
                    self.audit.add("tool_result", name=name, result=error_msg)
                    span.set_attribute("error", True)
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
            if self.cfg.mode == "observe":
                result = "DENIED: observe mode"
            elif self.cfg.mode == "assist" and not await self._approval_granted(f"Allow Bifang to write {args['path']}?"):
                result = "DENIED by user"
            else:
                p = self.policy.path(args["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args["content"], encoding="utf-8")
                result = f"Wrote {args['path']}"
        elif name == "run_command":
            d = self.policy.command(args["command"])
            if not d.allowed:
                result = f"DENIED: {d.reason}"
            elif d.approval and not await self._approval_granted(f"Run command?\n{args['command']}"):
                result = "DENIED by user"
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

    async def ask(self, prompt: str, on_text: Callable[[str], None] | None = None, task_type: TaskType | None = None) -> str:
        """Ask the agent a question (non-streaming)."""
        await self._ensure_services_started()

        self.messages.append({"role": "user", "content": prompt})
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
                    "provider": self.cfg.default_provider,
                    "model": self.cfg.get_default_model() or "",
                    "task_type": task_type.value,
                },
            ) as span:
                msg = await self.provider.complete(
                    self.messages,
                    tools=self._get_tools_schema(),
                    task_type=task_type,
                )
                usage = msg.get("usage") or {}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if key in usage:
                        span.set_attribute(f"usage.{key}", usage[key])
            self.messages.append(msg)
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
                self.messages.append(tool_msg)
                self.context.add_message(tool_msg)

        return "Stopped after maximum agent steps. Inspect /diff and the transcript."

    async def ask_stream(
        self,
        prompt: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
        task_type: TaskType | None = None,
    ) -> AsyncIterator[str]:
        """Ask the agent a question with streaming response."""
        await self._ensure_services_started()

        self.messages.append({"role": "user", "content": prompt})
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

            async for chunk in self.provider.complete_stream(self.messages, tools=self._get_tools_schema(), task_type=task_type):
                if chunk.get("content"):
                    accumulated_content += chunk["content"]
                    if on_text:
                        on_text(chunk["content"])

                if chunk.get("tool_calls"):
                    accumulated_tool_calls.extend(chunk["tool_calls"])

            # Create assistant message
            assistant_msg = {"role": "assistant", "content": accumulated_content}
            if accumulated_tool_calls:
                assistant_msg["tool_calls"] = accumulated_tool_calls
            self.messages.append(assistant_msg)
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
                self.messages.append(tool_msg)
                self.context.add_message(tool_msg)

        yield "Stopped after maximum agent steps. Inspect /diff and the transcript."

    async def close(self):
        """Clean up resources."""
        await self.provider.close()
        await self.mcp.close_all()
        await self.plugins.shutdown_all()
