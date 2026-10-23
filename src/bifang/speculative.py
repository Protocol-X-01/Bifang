from __future__ import annotations

import asyncio
import logging
import os
import json
import hashlib
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING
from pathlib import Path

from .config import Config

if TYPE_CHECKING:
    from .provider import TieredProviderManager
    # Use string annotations for routing types to avoid circular import
    from .routing import TaskType, ModelSpec, NEMOTRON_MODELS, ModelTier

logger = logging.getLogger(__name__)

try:
    import tensorrt as trt
    import tensorrt_llm
    from tensorrt_llm.runtime import ModelRunner, SamplingConfig
    from tensorrt_llm._utils import str_dtype_to_trt
    HAS_TENSORRT_LLM = True
except ImportError:
    HAS_TENSORRT_LLM = False
    logger.warning("TensorRT-LLM not available. Install with: pip install tensorrt-llm")

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class SpeculativeConfig:
    """Configuration for TensorRT speculative decoding."""
    enabled: bool = True
    draft_model_path: str = ""  # Path to TensorRT engine for draft model
    target_model_path: str = ""  # Path to TensorRT engine for target model
    max_draft_tokens: int = 4
    acceptance_threshold: float = 0.9
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 50
    repetition_penalty: float = 1.0
    enable_kv_cache_reuse: bool = True


@dataclass
class SpeculativeResult:
    accepted_tokens: int = 0
    rejected_tokens: int = 0
    total_drafted: int = 0
    speedup_ratio: float = 1.0


class TensorRTSpeculativeDecoder:
    """TensorRT-LLM based speculative decoding implementation."""
    
    def __init__(
        self,
        provider_manager: "TieredProviderManager",
        config: SpeculativeConfig | None = None,
    ):
        if not HAS_TENSORRT_LLM:
            raise RuntimeError("TensorRT-LLM required for speculative decoding. Install: pip install tensorrt-llm")
        
        self.provider_manager = provider_manager
        self.config = config or SpeculativeConfig()
        self.stats = SpeculativeResult()
        
        self._draft_runner: Optional[ModelRunner] = None
        self._target_runner: Optional[ModelRunner] = None
        self._draft_tokenizer = None
        self._target_tokenizer = None
        self._initialized = False
        
        # KV cache for draft and target models
        self._draft_kv_cache = None
        self._target_kv_cache = None
    
    def _get_model_paths(self) -> tuple[str, str]:
        """Get paths to TensorRT engines for draft and target models."""
        from .routing import NEMOTRON_MODELS
        
        draft_spec = NEMOTRON_MODELS.get(self.config.draft_model)
        target_spec = NEMOTRON_MODELS.get(self.config.target_model)
        
        if not draft_spec or not target_spec:
            raise ValueError(f"Model specs not found for draft: {self.config.draft_model} or target: {self.config.target_model}")
        
        # Model paths should point to TensorRT engine directories
        base_path = os.getenv("TENSORRT_MODEL_PATH", "/opt/tensorrt-engines")
        
        draft_path = os.path.join(base_path, self.config.draft_model.replace("/", "_"))
        target_path = os.path.join(base_path, self.config.target_model.replace("/", "_"))
        
        return draft_path, target_path
    
    async def initialize(self):
        """Initialize TensorRT model runners for draft and target models."""
        if self._initialized:
            return
            
        if not HAS_TENSORRT_LLM:
            raise RuntimeError("TensorRT-LLM not available")
        
        draft_path, target_path = self._get_model_paths()
        
        # Load draft model (Nemotron Nano/Super)
        logger.info(f"Loading draft model from {draft_path}")
        self._draft_runner = ModelRunner.from_dir(
            draft_path,
            rank=0,
            gpu_id=0,
            max_batch_size=1,
            max_input_len=4096,
            max_output_len=self.config.max_draft_tokens,
            enable_kv_cache_reuse=self.config.enable_kv_cache_reuse,
        )
        
        # Load target model (Nemotron 3 Ultra)
        logger.info(f"Loading target model from {target_path}")
        self._target_runner = ModelRunner.from_dir(
            target_path,
            rank=0,
            gpu_id=0,
            max_batch_size=1,
            max_input_len=8192,
            max_output_len=4096,
            enable_kv_cache_reuse=self.config.enable_kv_cache_reuse,
        )
        
        # Load tokenizers
        from transformers import AutoTokenizer
        draft_model_id = self.config.draft_model
        target_model_id = self.config.target_model
        
        # Map to HF model IDs for tokenizer
        tokenizer_map = {
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": "nvidia/Nemotron-3-Nano-Omni-30B-A3B",
            "nvidia/nemotron-3-super-120b-a12b": "nvidia/Nemotron-3-Super-120B",
            "nvidia/nemotron-3-ultra-550b-a55b": "nvidia/Nemotron-3-Ultra-550B",
        }
        
        draft_tokenizer_id = draft_model_id
        target_tokenizer_id = target_model_id
        
        if draft_model_id in tokenizer_map:
            draft_tokenizer_id = tokenizer_map[draft_model_id]
        if target_model_id in tokenizer_map:
            target_tokenizer_id = tokenizer_map[target_model_id]
        
        self._draft_tokenizer = AutoTokenizer.from_pretrained(draft_tokenizer_id, trust_remote_code=True)
        self._target_tokenizer = AutoTokenizer.from_pretrained(target_tokenizer_id, trust_remote_code=True)
        
        # Ensure pad token
        if self._draft_tokenizer.pad_token is None:
            self._draft_tokenizer.pad_token = self._draft_tokenizer.eos_token
        if self._target_tokenizer.pad_token is None:
            self._target_tokenizer.pad_token = self._target_tokenizer.eos_token
        
        self._initialized = True
        logger.info("TensorRT speculative decoder initialized")
    
    def _get_model_paths(self) -> tuple[str, str]:
        """Get paths to TensorRT engines for draft and target models."""
        from .routing import NEMOTRON_MODELS
        
        draft_spec = NEMOTRON_MODELS.get(self.config.draft_model)
        target_spec = NEMOTRON_MODELS.get(self.config.target_model)
        
        if not draft_spec or not target_spec:
            raise ValueError(f"Model specs not found for draft: {self.config.draft_model} or target: {self.config.target_model}")
        
        # Model paths should point to TensorRT engine directories
        base_path = os.getenv("TENSORRT_MODEL_PATH", "/opt/tensorrt-engines")
        
        draft_path = os.path.join(base_path, self.config.draft_model.replace("/", "_"))
        target_path = os.path.join(base_path, self.config.target_model.replace("/", "_"))
        
        return draft_path, target_path
    
    def _messages_to_prompt(self, messages: list[dict]) -> str:
        """Convert messages to prompt string for TensorRT-LLM."""
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"<|system|>\n{content}")
            elif role == "user":
                prompt_parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                prompt_parts.append(f"<|assistant|>\n{content}")
            elif role == "tool":
                prompt_parts.append(f"<|tool|>\n{content}")
        prompt_parts.append("<|assistant|>")
        return "\n".join(prompt_parts)
    
    def _encode_prompt(self, prompt: str, tokenizer) -> tuple:
        """Encode prompt to token IDs."""
        input_ids = tokenizer.encode(prompt, return_tensors="pt")
        return input_ids.to("cuda") if HAS_TORCH else input_ids
    
    def _decode_tokens(self, token_ids, tokenizer) -> str:
        """Decode token IDs to string."""
        return tokenizer.decode(token_ids, skip_special_tokens=True)
    
    def _compute_logprobs(self, logits, token_ids) -> list[float]:
        """Compute log probabilities for token sequence."""
        import torch.nn.functional as F
        log_probs = F.log_softmax(logits, dim=-1)
        return [log_probs[0, i, token_id].item() for i, token_id in enumerate(token_ids)]
    
    def _verify_draft_tokens(
        self,
        draft_token_ids: list[int],
        target_logits: list,
        draft_logits: list,
        acceptance_threshold: float
    ) -> tuple[list[int], list[int]]:
        """
        Verify draft tokens using target model logits.
        Returns (accepted_token_ids, rejected_token_ids).
        """
        import torch
        import torch.nn.functional as F
        
        accepted = []
        rejected = []
        
        for i, draft_id in enumerate(draft_token_ids):
            if i >= len(target_logits):
                break
                
            # Get target model's probability for the draft token
            target_logit = target_logits[i][draft_id]
            target_prob = F.softmax(target_logits[i], dim=-1)[draft_id].item()
            
            # Get draft model's probability for the draft token
            if i < len(draft_logits):
                draft_prob = F.softmax(draft_logits[i], dim=-1)[draft_id].item()
            else:
                draft_prob = 1.0
            
            # Acceptance criteria: target model assigns high probability to draft token
            # and draft probability is close to target probability
            prob_ratio = target_prob / max(draft_prob, 1e-10)
            
            if target_prob >= self.config.acceptance_threshold * draft_prob:
                accepted.append(draft_id)
            else:
                rejected.append(draft_id)
        
        return accepted, rejected
    
    async def generate_with_speculation(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        task_type = None,
        context: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        top_p: float = 0.95,
        top_k: int = 50,
        on_token: Optional[callable] = None,
    ) -> AsyncIterator[str]:
        """Generate text using TensorRT speculative decoding."""
        
        if not self._initialized:
            await self.initialize()
        
        if not self.config.enabled:
            # Fallback to regular generation
            async for chunk in self.provider_manager.complete_stream(
                messages=messages,
                tools=tools,
                task_type=task_type,
                context=context,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if chunk.get("content"):
                    if on_token:
                        on_token(chunk["content"])
                    yield chunk["content"]
            return
        
        # Prepare sampling config for TensorRT-LLM
        sampling_config = SamplingConfig(
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
            repetition_penalty=self.config.repetition_penalty,
            max_new_tokens=max_tokens,
            end_id=self._target_tokenizer.eos_token_id,
            pad_id=self._target_tokenizer.pad_token_id,
        )
        
        # Create sampling config for draft (higher temperature for diversity)
        draft_sampling = SamplingConfig(
            temperature=min(temperature * 1.5, 1.0),
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=self.config.repetition_penalty,
            max_new_tokens=self.config.max_draft_tokens,
            end_id=self._draft_tokenizer.eos_token_id,
            pad_id=self._draft_tokenizer.pad_token_id,
        )
        
        # Prepare prompt
        prompt = self._messages_to_prompt(messages)
        input_ids = self._encode_prompt(prompt, self._target_tokenizer)
        input_ids = input_ids.to("cuda")
        
        accumulated_content = ""
        tokens_generated = 0
        
        while tokens_generated < max_tokens:
            # Step 1: Generate draft tokens using fast model
            draft_output = self._draft_runner.generate(
                input_ids=input_ids,
                sampling_config=draft_sampling,
                streaming=True,
            )
            
            draft_token_ids = []
            draft_logits = []
            
            # Collect draft tokens and their logits
            for step_output in draft_output:
                if step_output.token_ids is not None:
                    draft_token_ids.extend(step_output.token_ids[0].tolist())
                if step_output.logits is not None:
                    draft_logits.append(step_output.logits[0])  # [vocab_size]
                
                if len(draft_token_ids) >= self.config.max_draft_tokens:
                    break
            
            if not draft_token_ids:
                break
            
            self.stats.total_drafted += len(draft_token_ids)
            draft_text = self._decode_tokens(draft_token_ids, self._draft_tokenizer)
            
            # Step 2: Verify with target model
            # Run target model on prompt + draft tokens
            verification_input_ids = torch.cat([input_ids, torch.tensor([draft_token_ids], device="cuda")], dim=-1)
            
            target_output = self._target_runner.generate(
                input_ids=verification_input_ids,
                sampling_config=SamplingConfig(
                    temperature=0.0,  # Greedy for verification
                    top_p=1.0,
                    top_k=1,
                    max_new_tokens=1,
                ),
                streaming=False,
            )
            
            target_logits = target_output.logits  # [batch, seq_len, vocab]
            
            # Verify draft tokens
            accepted_ids, rejected_ids = self._verify_draft_tokens(
                draft_token_ids=draft_token_ids,
                target_logits=target_logits[-len(draft_token_ids):],  # Last N positions
                draft_logits=draft_logits,  # We don't have draft logits easily, skip for now
                acceptance_threshold=self.config.acceptance_threshold,
            )
            
            if accepted_ids:
                # Accept all draft tokens
                for token_id in accepted_ids:
                    token_text = self._decode_tokens([token_id], self._target_tokenizer)
                    if on_token:
                        on_token(token_text)
                    yield token_text
                
                accumulated_content = draft_text
                self.stats.accepted_tokens += len(accepted_ids)
                tokens_generated += len(accepted_ids)
                
                # Update input_ids for next iteration
                input_ids = torch.cat([input_ids, torch.tensor([accepted_ids], device="cuda")], dim=-1)
            else:
                # Reject draft, fallback to target model
                self.stats.rejected_tokens += len(draft_token_ids)
                
                # Generate with target model
                target_output = self._target_runner.generate(
                    input_ids=input_ids,
                    sampling_config=SamplingConfig(
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        max_new_tokens=max_tokens - len(accumulated_content),
                    ),
                    streaming=True,
                )
                
                for chunk in target_output:
                    if chunk.get("content"):
                        if on_token:
                            on_token(chunk["content"])
                        yield chunk["content"]
                    accumulated_content += chunk.get("content", "")
                    tokens_generated += len(chunk.get("token_ids", []))
                
                break
        
        if self.stats.total_drafted > 0:
            self.stats.speedup_ratio = (self.stats.accepted_tokens + self.stats.rejected_tokens) / max(1, self.stats.total_drafted)
    
    def _is_model_available(self, model_spec: ModelSpec) -> bool:
        """Check if a model is available."""
        if not model_spec:
            return False
        provider = self.provider_manager.provider_manager.registry.get(model_spec.provider)
        return provider is not None
    
    def get_stats(self) -> SpeculativeResult:
        return self.stats
    
    def reset_stats(self):
        self.stats = SpeculativeResult()


class AdaptiveSpeculativeDecoder:
    """Adaptive speculative decoder that adjusts draft length based on acceptance rate."""
    
    def __init__(
        self,
        provider_manager: "TieredProviderManager",
        base_config: SpeculativeConfig | None = None,
    ):
        self.base_decoder = SpeculativeDecoder(provider_manager, base_config)
        self.acceptance_history: list[float] = []
        self.target_acceptance_rate = 0.7
        self.min_draft_tokens = 1
        self.max_draft_tokens = 8
    
    def update_acceptance_rate(self, accepted: int, total: int):
        if total == 0:
            return
        
        rate = accepted / total
        self.acceptance_history.append(rate)
        
        if len(self.acceptance_history) > 100:
            self.acceptance_history.pop(0)
        
        avg_rate = sum(self.acceptance_history) / len(self.acceptance_history)
        
        if avg_rate > self.target_acceptance_rate + 0.1:
            self.base_decoder.config.max_draft_tokens = min(
                self.base_decoder.config.max_draft_tokens + 1,
                self.max_draft_tokens,
            )
        elif avg_rate < self.target_acceptance_rate - 0.1:
            self.base_decoder.config.max_draft_tokens = max(
                self.base_decoder.config.max_draft_tokens - 1,
                self.min_draft_tokens,
            )
    
    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        task_type = None,
        context: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        on_token: Optional[callable] = None,
    ) -> AsyncIterator[str]:
        async for token in self.base_decoder.generate_with_speculation(
            messages=messages,
            tools=tools,
            task_type=task_type,
            context=context,
            max_tokens=max_tokens,
            temperature=temperature,
            on_token=on_token,
        ):
            yield token
        
        stats = self.base_decoder.get_stats()
        if stats.total_drafted > 0:
            self.update_acceptance_rate(stats.accepted_tokens, stats.total_drafted)
    
    def get_stats(self) -> SpeculativeResult:
        return self.base_decoder.get_stats()


def create_speculative_decoder(
    provider_manager: "TieredProviderManager",
    config: SpeculativeConfig | None = None,
) -> "TensorRTSpeculativeDecoder":
    """Factory function to create a TensorRT speculative decoder."""
    return TensorRTSpeculativeDecoder(provider_manager, config)


def create_adaptive_speculative_decoder(
    provider_manager: "TieredProviderManager",
    config: SpeculativeConfig | None = None,
) -> "AdaptiveSpeculativeDecoder":
    return AdaptiveSpeculativeDecoder(provider_manager, config)