from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from .config import Config

if TYPE_CHECKING:
    from .provider import ProviderManager


class TaskType(Enum):
    """Task types for routing decisions."""
    # Fast path - use Nemotron Nano/Super
    AUTOCOMPLETE = "autocomplete"
    SIMPLE_FIX = "simple_fix"
    SYNTAX_CHECK = "syntax_check"
    DOC_LOOKUP = "doc_lookup"
    SIMPLE_REFACTOR = "simple_refactor"
    
    # Medium path - use Nemotron Super/Ultra
    REFACTOR = "refactor"
    CODE_REVIEW = "code_review"
    TEST_GENERATION = "test_generation"
    DOC_GENERATION = "doc_generation"
    
    # Reasoning path - use Nemotron 3 Ultra
    REASONING = "reasoning"
    ARCHITECTURE = "architecture"
    COMPLEX_REFACTOR = "complex_refactor"
    DEBUGGING = "debugging"
    ARCHITECTURE_DESIGN = "architecture_design"
    COMPLEX_DEBUGGING = "complex_debugging"
    SECURITY_AUDIT = "security_audit"
    PERFORMANCE_TUNING = "performance_tuning"
    
    # Special
    CHAT = "chat"
    UNKNOWN = "unknown"


class ModelTier(Enum):
    """Model performance tiers."""
    FAST = "fast"           # Nemotron Nano/Super - low latency, high throughput
    MEDIUM = "medium"       # Nemotron Super - balanced
    REASONING = "reasoning" # Nemotron 3 Ultra - deep reasoning


@dataclass
class ModelSpec:
    """Specification for a model."""
    model_id: str
    provider: str
    tier: ModelTier
    max_tokens: int = 4096
    temperature: float = 0.2
    use_case: str = ""
    cost_per_1k_tokens: float = 0.0


@dataclass
class RoutingRule:
    """A routing rule mapping task types to model specs."""
    task_types: list[TaskType]
    model_spec: ModelSpec
    priority: int = 0  # Higher priority = more specific
    conditions: dict[str, Any] = field(default_factory=dict)


# Nemotron model specs for Nebius Token Factory / NVIDIA API
NEMOTRON_MODELS = {
    # Fast tier - Nemotron Nano/Super
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": ModelSpec(
        model_id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        provider="nvidia",
        tier=ModelTier.FAST,
        max_tokens=4096,
        temperature=0.1,
        use_case="Ultra-fast autocomplete, simple fixes, syntax checks",
        cost_per_1k_tokens=0.0001,
    ),
    "nvidia/nemotron-3-super-120b-a12b": ModelSpec(
        model_id="nvidia/nemotron-3-super-120b-a12b",
        provider="nvidia",
        tier=ModelTier.FAST,
        max_tokens=8192,
        temperature=0.15,
        use_case="Fast autocomplete, simple refactors, code generation",
        cost_per_1k_tokens=0.0003,
    ),
    # Medium tier
    "nvidia/llama-3.1-nemotron-70b-instruct": ModelSpec(
        model_id="nvidia/llama-3.1-nemotron-70b-instruct",
        provider="nvidia",
        tier=ModelTier.MEDIUM,
        max_tokens=8192,
        temperature=0.2,
        use_case="Code review, test generation, refactoring",
        cost_per_1k_tokens=0.0005,
    ),
    # Reasoning tier - Nemotron 3 Ultra
    "nvidia/nemotron-3-ultra-550b-a55b": ModelSpec(
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        provider="nvidia",
        tier=ModelTier.REASONING,
        max_tokens=16384,
        temperature=0.2,
        use_case="Deep reasoning, architecture, complex debugging, security audit",
        cost_per_1k_tokens=0.001,
    ),
    # Nebius Token Factory variants
    "nebius/nvidia/nemotron-3-ultra-550b-a55b": ModelSpec(
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        provider="nebius",
        tier=ModelTier.REASONING,
        max_tokens=16384,
        temperature=0.2,
        use_case="Deep reasoning via Nebius Token Factory",
        cost_per_1k_tokens=0.001,
    ),
    "nebius/nvidia/nemotron-3-super-120b-a12b": ModelSpec(
        model_id="nvidia/nemotron-3-super-120b-a12b",
        provider="nebius",
        tier=ModelTier.FAST,
        max_tokens=8192,
        temperature=0.15,
        use_case="Fast tasks via Nebius Token Factory",
        cost_per_1k_tokens=0.0003,
    ),
}


# Default routing rules - ordered by priority (higher = more specific)
DEFAULT_ROUTING_RULES: list[RoutingRule] = [
    # Fast path - Nemotron Nano/Super
    RoutingRule(
        task_types=[
            TaskType.AUTOCOMPLETE,
            TaskType.SYNTAX_CHECK,
            TaskType.DOC_LOOKUP,
        ],
        model_spec=NEMOTRON_MODELS["nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"],
        priority=100,
    ),
    RoutingRule(
        task_types=[
            TaskType.SIMPLE_FIX,
            TaskType.SIMPLE_REFACTOR,
            TaskType.DOC_LOOKUP,
        ],
        model_spec=NEMOTRON_MODELS["nvidia/nemotron-3-super-120b-a12b"],
        priority=90,
    ),
    # Medium path
    RoutingRule(
        task_types=[
            TaskType.REFACTOR,
            TaskType.CODE_REVIEW,
            TaskType.TEST_GENERATION,
            TaskType.DOC_GENERATION,
        ],
        model_spec=NEMOTRON_MODELS["nvidia/llama-3.1-nemotron-70b-instruct"],
        priority=80,
    ),
    # Reasoning path - Nemotron 3 Ultra
    RoutingRule(
        task_types=[
            TaskType.REASONING,
            TaskType.ARCHITECTURE,
            TaskType.COMPLEX_REFACTOR,
            TaskType.DEBUGGING,
            TaskType.ARCHITECTURE_DESIGN,
            TaskType.COMPLEX_DEBUGGING,
            TaskType.SECURITY_AUDIT,
            TaskType.PERFORMANCE_TUNING,
        ],
        model_spec=NEMOTRON_MODELS["nvidia/nemotron-3-ultra-550b-a55b"],
        priority=100,
    ),
    # Chat default - use reasoning model for complex conversations
    RoutingRule(
        task_types=[TaskType.CHAT, TaskType.UNKNOWN],
        model_spec=NEMOTRON_MODELS["nvidia/nemotron-3-ultra-550b-a55b"],
        priority=10,
    ),
]


class TaskClassifier:
    """Classifies user requests into task types."""
    
    # Keywords for each task type
    KEYWORDS = {
        TaskType.AUTOCOMPLETE: ["complete", "autocomplete", "suggest", "tab", "inline"],
        TaskType.SIMPLE_FIX: ["fix typo", "syntax error", "missing import", "typo", "missing semicolon"],
        TaskType.SIMPLE_REFACTOR: ["rename", "extract method", "extract variable", "inline variable"],
        TaskType.DOC_LOOKUP: ["documentation", "docs", "api reference", "how to use"],
        TaskType.REFACTOR: ["refactor", "restructure", "clean up", "organize", "modernize"],
        TaskType.CODE_REVIEW: ["review", "audit", "check code", "best practices", "security review"],
        TaskType.TEST_GENERATION: ["write test", "generate test", "unit test", "integration test", "test coverage"],
        TaskType.DOC_GENERATION: ["write docs", "generate docs", "documentation", "readme", "comments"],
        TaskType.REASONING: ["why", "explain", "reason", "analyze", "understand", "think through"],
        TaskType.ARCHITECTURE: ["architecture", "design", "system design", "scalability", "patterns"],
        TaskType.COMPLEX_REFACTOR: ["large refactor", "major restructure", "migrate", "rewrite"],
        TaskType.DEBUGGING: ["debug", "bug", "error", "crash", "exception", "traceback", "not working"],
        TaskType.ARCHITECTURE_DESIGN: ["design system", "architecture design", "system design"],
        TaskType.COMPLEX_DEBUGGING: ["race condition", "deadlock", "memory leak", "performance issue", "production bug"],
        TaskType.SECURITY_AUDIT: ["security", "vulnerability", "injection", "xss", "csrf", "auth", "authorization"],
        TaskType.PERFORMANCE_TUNING: ["optimize", "performance", "latency", "throughput", "bottleneck", "profile"],
        TaskType.COMPLEX_DEBUGGING: ["root cause", "production issue", "intermittent", "flaky"],
    }
    
    # File patterns that suggest task types
    FILE_PATTERNS = {
        TaskType.TEST_GENERATION: ["test_", "_test.py", "spec.", "spec.ts", "test.ts"],
        TaskType.DOC_GENERATION: ["README", "CHANGELOG", "CONTRIBUTING", ".md"],
        TaskType.SECURITY_AUDIT: ["auth", "security", "crypto", "password", "token", "jwt", "oauth"],
        TaskType.PERFORMANCE_TUNING: ["benchmark", "profile", "optimize", "cache", "async", "concurrent"],
    }
    
    @classmethod
    def classify(cls, prompt: str, context: dict | None = None) -> TaskType:
        """Classify a prompt into a task type."""
        prompt_lower = prompt.lower()
        
        # Check for explicit task type mentions
        scores = {}
        
        for task_type, keywords in cls.KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in prompt_lower)
            if score > 0:
                scores[task_type] = score
        
        # Check file patterns from context
        if context and "files" in context:
            for file_path in context.get("files", []):
                file_lower = file_path.lower()
                for task_type, patterns in cls.FILE_PATTERNS.items():
                    if any(p in file_lower for p in patterns):
                        scores[task_type] = scores.get(task_type, 0) + 2
        
        # Check for reasoning keywords
        reasoning_indicators = ["think", "reason", "step by step", "analyze", "consider", "evaluate", "trade-off", "tradeoff", "pros and cons", "architecture", "design"]
        reasoning_score = sum(1 for ind in reasoning_indicators if ind in prompt_lower)
        if reasoning_score >= 2:
            scores[TaskType.REASONING] = scores.get(TaskType.REASONING, 0) + reasoning_score
        
        # Check for complex debugging
        debug_indicators = ["race condition", "deadlock", "memory leak", "production", "intermittent", "flaky", "core dump", "segfault"]
        debug_score = sum(1 for ind in debug_indicators if ind in prompt_lower)
        if debug_score >= 1:
            scores[TaskType.COMPLEX_DEBUGGING] = scores.get(TaskType.COMPLEX_DEBUGGING, 0) + debug_score * 3
        
        # Check for security
        security_indicators = ["sql injection", "xss", "csrf", "authentication", "authorization", "rbac", "oauth", "jwt", "encryption", "hash", "salt"]
        security_score = sum(1 for ind in security_indicators if ind in prompt_lower)
        if security_score >= 1:
            scores[TaskType.SECURITY_AUDIT] = scores.get(TaskType.SECURITY_AUDIT, 0) + security_score * 3
        
        # Check for performance
        perf_indicators = ["optimize", "slow", "latency", "throughput", "bottleneck", "profile", "benchmark", "memory usage", "cpu usage"]
        perf_score = sum(1 for ind in perf_indicators if ind in prompt_lower)
        if perf_score >= 1:
            scores[TaskType.PERFORMANCE_TUNING] = scores.get(TaskType.PERFORMANCE_TUNING, 0) + perf_score * 2
        
        if not scores:
            return TaskType.CHAT
        
        return max(scores.items(), key=lambda x: x[1])[0]


class TieredRouter:
    """Routes requests to appropriate models based on task type and availability."""
    
    def __init__(self, provider_manager: ProviderManager, config: Config):
        self.provider_manager = provider_manager
        self.config = config
        self.rules = DEFAULT_ROUTING_RULES.copy()
        self._available_models: set[str] = set()
        self._refresh_available_models()
    
    def _refresh_available_models(self):
        """Refresh the set of available models from all providers."""
        # This would be called async, for now we'll use a sync approximation
        # In practice, this should be called after provider initialization
        pass
    
    async def refresh_models(self):
        """Refresh available models from all providers."""
        self._available_models.clear()
        models = await self.provider_manager.list_models()
        self._available_models = set(models)
    
    def _is_model_available(self, model_spec: ModelSpec) -> bool:
        """Check if a model is available from any provider."""
        if not self._available_models:
            return True  # If we don't know, assume available
        
        # Check both with and without provider prefix
        return (model_spec.model_id in self._available_models or 
                f"{model_spec.provider}/{model_spec.model_id.split('/')[-1]}" in self._available_models)
    
    def select_model(self, task_type: TaskType) -> Optional[ModelSpec]:
        """Select the best model for a task type."""
        # Filter rules that match the task type
        matching_rules = [r for r in self.rules if task_type in r.task_types]
        
        if not matching_rules:
            # Fallback to reasoning model
            return NEMOTRON_MODELS.get("nvidia/nemotron-3-ultra-550b-a55b")
        
        # Sort by priority (highest first)
        matching_rules.sort(key=lambda r: r.priority, reverse=True)
        
        # Find first available model
        for rule in matching_rules:
            if self._is_model_available(rule.model_spec):
                return rule.model_spec
        
        # Fallback: any available model from the highest priority rule
        for rule in matching_rules:
            if self._find_available_alternative(rule.model_spec.tier):
                return self._find_available_alternative(rule.model_spec.tier)
        
        # Ultimate fallback
        return NEMOTRON_MODELS.get("nvidia/nemotron-3-ultra-550b-a55b")
    
    def _find_available_alternative(self, tier: ModelTier) -> Optional[ModelSpec]:
        """Find any available model of a given tier."""
        for model in NEMOTRON_MODELS.values():
            if model.tier == tier and self._is_model_available(model):
                return model
        return None
    
    def get_model_for_prompt(self, prompt: str, context: dict | None = None) -> ModelSpec:
        """Get the best model for a prompt."""
        task_type = TaskClassifier.classify(prompt, context)
        return self.select_model(task_type)
    
    def get_model_tier(self, task_type: TaskType) -> ModelTier:
        """Get the recommended model tier for a task type."""
        model = self.select_model(task_type)
        return model.tier if model else ModelTier.REASONING
    
    def add_rule(self, rule: RoutingRule):
        """Add a custom routing rule."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def get_routing_info(self, task_type: TaskType) -> dict:
        """Get detailed routing information for a task type."""
        model = self.select_model(task_type)
        tier = self.get_model_tier(task_type)
        
        return {
            "task_type": task_type.value,
            "recommended_model": model.model_id if model else None,
            "tier": tier.value,
            "provider": model.provider if model else None,
            "max_tokens": model.max_tokens if model else 4096,
            "temperature": model.temperature if model else 0.2,
            "use_case": model.use_case if model else "",
            "estimated_cost_per_1k": model.cost_per_1k_tokens if model else 0.0,
        }


class TieredProviderManager:
    """Provider manager with tiered routing."""
    
    def __init__(self, provider_manager: ProviderManager, config: Config):
        self.provider_manager = provider_manager
        self.router = TieredRouter(provider_manager, None)
        self._initialize_routing()
    
    def _initialize_routing(self):
        """Initialize routing with available models."""
        # The router will be fully initialized after models are loaded
        pass
    
    async def initialize(self):
        """Initialize the router with available models."""
        await self.router.refresh_models()
    
    async def complete(
        self,
        messages: list[dict],
        task_type: TaskType | None = None,
        prompt: str | None = None,
        context: dict | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Complete with automatic model selection based on task type."""
        # Determine task type
        if task_type is None:
            if prompt:
                task_type = TaskClassifier.classify(prompt, context)
            else:
                # Infer from last user message
                last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
                if last_user:
                    task_type = TaskClassifier.classify(last_user.get("content", ""), context)
                else:
                    task_type = TaskType.CHAT
        
        # Select model
        model_spec = self.router.select_model(task_type)
        
        # Prepare context for classification
        if context is None:
            context = {}
        
        # Complete
        return await self.provider_manager.complete(
            messages=messages,
            provider=model_spec.provider if model_spec else None,
            model=model_spec.model_id if model_spec else None,
            **kwargs,
        )
    
    async def complete_stream(
        self,
        messages: list[dict],
        task_type: TaskType | None = None,
        prompt: str | None = None,
        context: dict | None = None,
        **kwargs,
    ):
        """Stream completion with automatic model selection."""
        if task_type is None:
            if prompt:
                task_type = TaskClassifier.classify(prompt, context)
            else:
                last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
                if last_user:
                    task_type = TaskClassifier.classify(last_user.get("content", ""), context)
                else:
                    task_type = TaskType.CHAT
        
        model_spec = self.router.select_model(task_type)
        
        async for chunk in self.provider_manager.complete_stream(
            messages=messages,
            provider=model_spec.provider if model_spec else None,
            model=model_spec.model_id if model_spec else None,
            **kwargs,
        ):
            # Add routing metadata to stream
            chunk["routing"] = {
                "task_type": task_type.value,
                "model": model_spec.model_id if model_spec else None,
                "tier": model_spec.tier.value if model_spec else None,
            }
            yield chunk
    
    def get_routing_info(self, task_type: TaskType | None = None) -> dict:
        """Get routing information."""
        if task_type:
            return self.router.get_routing_info(task_type)
        
        # Return info for all task types
        return {
            task.value: self.router.get_routing_info(task)
            for task in TaskType
        }
    
    def get_model_spec(self, model_id: str) -> Optional[ModelSpec]:
        """Get model spec by ID."""
        return NEMOTRON_MODELS.get(model_id)
    
    def list_available_models_by_tier(self) -> dict[ModelTier, list[ModelSpec]]:
        """List available models grouped by tier."""
        result = {tier: [] for tier in ModelTier}
        for model in NEMOTRON_MODELS.values():
            if self.provider_manager.registry.get(model.provider):
                result[model.tier].append(model)
        return result


# Speculative decoding exports (imported at module level to avoid circular dependency)
# These are imported here to make them available as bifang.routing.SpeculativeDecoder etc.
try:
    from .speculative import (
        SpeculativeDecoder,
        AdaptiveSpeculativeDecoder,
        SpeculativeConfig,
        SpeculativeResult,
        create_speculative_decoder,
        create_adaptive_speculative_decoder,
    )
except ImportError:
    # If speculative module has issues, define placeholder classes
    SpeculativeDecoder = None
    AdaptiveSpeculativeDecoder = None
    SpeculativeConfig = None
    SpeculativeResult = None
    create_speculative_decoder = None
    create_adaptive_speculative_decoder = None


__all__ = [
    "TaskType",
    "ModelTier", 
    "ModelSpec",
    "RoutingRule",
    "TaskClassifier",
    "TieredRouter",
    "TieredProviderManager",
    "create_tiered_provider",
    "NEMOTRON_MODELS",
    "DEFAULT_ROUTING_RULES",
    # Speculative decoding
    "SpeculativeDecoder",
    "AdaptiveSpeculativeDecoder",
    "SpeculativeConfig",
    "SpeculativeResult",
    "create_speculative_decoder",
    "create_adaptive_speculative_decoder",
]