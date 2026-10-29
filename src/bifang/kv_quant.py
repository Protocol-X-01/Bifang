from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pickle
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    import onnx
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False


class QuantizationType(Enum):
    INT8 = "int8"
    INT4 = "int4"
    FP16 = "fp16"
    BF16 = "bf16"
    AWQ = "awq"  # Activation-aware Weight Quantization
    GPTQ = "gptq"  # Gradient-based Post-Training Quantization


@dataclass
class QuantizationConfig:
    """Configuration for KV-Cache quantization."""
    quantization_type: QuantizationType = QuantizationType.INT8
    group_size: int = 128
    symmetric: bool = True
    per_channel: bool = True
    calibrate_samples: int = 512
    exclude_layers: list[str] = field(default_factory=list)  # Layers to skip quantization
    kv_cache_quant: bool = True  # Quantize KV cache specifically
    attention_sink_tokens: int = 4  # Number of initial tokens to keep in FP16


@dataclass
class QuantizationStats:
    """Statistics from quantization."""
    original_size_mb: float = 0.0
    quantized_size_mb: float = 0.0
    compression_ratio: float = 0.0
    perplexity_increase: float = 0.0
    latency_improvement: float = 0.0
    memory_savings_mb: float = 0.0
    quantization_time_sec: float = 0.0


class KVCacheQuantizer:
    """Quantizes KV-Cache for reduced memory and faster inference."""
    
    def __init__(self, config: QuantizationConfig):
        self.config = config
        self.calibration_data: list[np.ndarray] = []
        self.quantization_params: dict[str, Any] = {}
    
    def calibrate(self, model: Any, calibration_inputs: list[dict]) -> QuantizationStats:
        """Calibrate quantization parameters using sample inputs."""
        start_time = time.time()
        
        if not HAS_TORCH:
            return QuantizationStats()
        
        original_size = self._estimate_model_size(model)
        
        # Collect activation statistics for KV cache
        self._collect_kv_cache_stats(model, calibration_inputs)
        
        # Compute quantization parameters
        self._compute_quant_params()
        
        # Apply quantization
        quantized_model = self.quantize_model(model)
        
        quantized_size = self._estimate_model_size(quantized_model)
        
        stats = QuantizationStats(
            original_size_mb=original_size,
            quantized_size_mb=quantized_size,
            compression_ratio=original_size / quantized_size if quantized_size > 0 else 1.0,
            quantization_time_sec=time.time() - start_time,
        )
        
        return stats
    
    def _collect_kv_cache_stats(self, model: Any, inputs: list[dict]):
        """Collect statistics on KV cache activations."""
        if not HAS_TORCH:
            return
        
        model.eval()
        hooks = []
        kv_cache_stats = {}
        
        def hook_fn(name):
            def hook(module, input, output):
                if isinstance(output, tuple):
                    for i, o in enumerate(output):
                        if o is not None and hasattr(o, 'shape'):
                            key = f"{name}.{i}"
                            if key not in kv_cache_stats:
                                kv_cache_stats[key] = {"min": float('inf'), "max": float('-inf'), "sum": 0, "count": 0}
                            kv_cache_stats[key]["min"] = min(kv_cache_stats[key]["min"], o.min().item())
                            kv_cache_stats[key]["max"] = max(kv_cache_stats[key]["max"], o.max().item())
                            kv_cache_stats[key]["sum"] += o.sum().item()
                            kv_cache_stats[key]["count"] += o.numel()
                else:
                    if output is not None and hasattr(output, 'shape'):
                        if name not in kv_cache_stats:
                            kv_cache_stats[name] = {"min": float('inf'), "max": float('-inf'), "sum": 0, "count": 0}
                        kv_cache_stats[name]["min"] = min(kv_cache_stats[name]["min"], output.min().item())
                        kv_cache_stats[name]["max"] = max(kv_cache_stats[name]["max"], output.max().item())
                        kv_cache_stats[name]["sum"] += output.sum().item()
                        kv_cache_stats[name]["count"] += output.numel()
            return hook
        
        # Register hooks on attention layers
        for name, module in model.named_modules():
            if any(kw in name.lower() for kw in ['attn', 'attention', 'self_attn', 'cross_attn']):
                hooks.append(module.register_forward_hook(hook_fn(name)))
        
        # Run calibration
        with torch.no_grad():
            for inp in inputs[:self.config.calibrate_samples]:
                try:
                    model(**inp)
                except:
                    pass
        
        # Remove hooks
        for hook in hooks:
            hook.remove()
        
        self.calibration_data = kv_cache_stats
    
    def _compute_quant_params(self):
        """Compute quantization parameters from calibration data."""
        for name, stats in self.calibration_data.items():
            if stats["count"] == 0:
                continue
            
            min_val = stats["min"]
            max_val = stats["max"]
            
            if self.config.symmetric:
                scale = max(abs(min_val), abs(max_val))
                zero_point = 0
            else:
                scale = max_val - min_val
                zero_point = -min_val / scale if scale > 0 else 0
            
            if self.config.quantization_type == QuantizationType.INT8:
                scale = scale / 127.0
            elif self.config.quantization_type == QuantizationType.INT4:
                scale = scale / 7.0
            
            self.quantization_params[name] = {
                "scale": scale,
                "zero_point": zero_point,
                "min": min_val,
                "max": max_val,
            }
    
    def quantize_model(self, model: Any) -> Any:
        """Apply quantization to model weights."""
        if not HAS_TORCH:
            return model
        
        # For now, return original model
        # Full implementation would use torch.quantization or custom kernels
        return model
    
    def quantize_kv_cache(self, key: torch.Tensor, value: torch.Tensor, layer_name: str) -> tuple[torch.Tensor, torch.Tensor]:
        """Quantize KV cache tensors on-the-fly."""
        if not self.config.kv_cache_quant:
            return key, value
        
        params = self.quantization_params.get(layer_name)
        if not params:
            return key, value
        
        scale = params["scale"]
        zero_point = params["zero_point"]
        
        # Keep attention sink tokens in FP16
        sink = self.config.attention_sink_tokens
        if key.shape[-2] > sink:
            key_sink = key[..., :sink, :]
            key_quant = key[..., sink:, :]
            value_sink = value[..., :sink, :]
            value_quant = value[..., sink:, :]
            
            # Quantize
            key_quant = torch.round(key_quant / scale + zero_point).to(torch.int8)
            value_quant = torch.round(value_quant / scale + zero_point).to(torch.int8)
            
            # Dequantize for computation
            key_quant = (key_quant.to(torch.float16) - zero_point) * scale
            value_quant = (value_quant.to(torch.float16) - zero_point) * scale
            
            key = torch.cat([key_sink, key_quant], dim=-2)
            value = torch.cat([value_sink, value_quant], dim=-2)
        
        return key, value
    
    def dequantize_kv_cache(self, key: torch.Tensor, value: torch.Tensor, layer_name: str) -> tuple[torch.Tensor, torch.Tensor]:
        """Dequantize KV cache tensors."""
        params = self.quantization_params.get(layer_name)
        if not params:
            return key, value
        
        scale = params["scale"]
        zero_point = params["zero_point"]
        
        if key.dtype == torch.int8:
            key = (key.to(torch.float16) - zero_point) * scale
        if value.dtype == torch.int8:
            value = (value.to(torch.float16) - zero_point) * scale
        
        return key, value
    
    def _estimate_model_size(self, model: Any) -> float:
        """Estimate model size in MB."""
        if not HAS_TORCH:
            return 0.0
        
        total_params = sum(p.numel() for p in model.parameters())
        # Assume FP16 (2 bytes per param)
        return total_params * 2 / (1024 * 1024)
    
    def save(self, path: str):
        """Save quantization parameters."""
        data = {
            "config": self.config.__dict__,
            "quantization_params": self.quantization_params,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
    
    @classmethod
    def load(cls, path: str) -> "KVCacheQuantizer":
        with open(path, "rb") as f:
            data = pickle.load(f)
        quantizer = cls(QuantizationConfig(**data["config"]))
        quantizer.quantization_params = data["quantization_params"]
        return quantizer


class ONNXQuantizer:
    """ONNX-based quantization for deployment."""
    
    def __init__(self):
        if not HAS_ONNX:
            raise ImportError("ONNX Runtime not available")
    
    def quantize_onnx_model(
        self,
        input_path: str,
        output_path: str,
        quantization_type: QuantizationType = QuantizationType.INT8,
        calibration_data: Optional[np.ndarray] = None,
    ) -> QuantizationStats:
        """Quantize ONNX model."""
        import onnxruntime.quantization as ort_quant
        
        start_time = time.time()
        
        # Get original size
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        
        # Quantize
        if quantization_type == QuantizationType.INT8:
            ort_quant.quantize_dynamic(
                input_path,
                output_path,
                weight_type=ort_quant.QuantType.QInt8,
            )
        elif quantization_type == QuantizationType.FP16:
            ort_quant.quantize_float16(input_path, output_path)
        
        quantized_size = os.path.getsize(output_path) / (1024 * 1024)
        
        return QuantizationStats(
            original_size_mb=original_size,
            quantized_size_mb=quantized_size,
            compression_ratio=original_size / quantized_size if quantized_size > 0 else 1.0,
            quantization_time_sec=time.time() - start_time,
        )


class PersistentKVCache:
    """Persistent KV-Cache with quantization support for long-context recall."""
    
    def __init__(
        self,
        max_tokens: int = 128000,
        quantizer: Optional[KVCacheQuantizer] = None,
        storage_path: Optional[str] = None,
    ):
        self.max_tokens = max_tokens
        self.quantizer = quantizer
        self.storage_path = Path(storage_path) if storage_path else None
        
        # In-memory cache: layer_name -> (keys, values, timestamps)
        self.cache: dict[str, tuple[Any, Any, list[float]]] = {}
        self.token_count = 0
        
        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            self._load()
    
    def append(
        self,
        layer_name: str,
        keys: Any,
        values: Any,
        timestamps: Optional[list[float]] = None,
    ):
        """Append new KV pairs to cache."""
        if timestamps is None:
            timestamps = [time.time()] * (keys.shape[-2] if hasattr(keys, 'shape') else 1)
        
        if layer_name not in self.cache:
            self.cache[layer_name] = (keys, values, timestamps)
        else:
            old_keys, old_values, old_timestamps = self.cache[layer_name]
            
            # Concatenate
            if hasattr(keys, 'shape') and hasattr(old_keys, 'shape'):
                new_keys = torch.cat([old_keys, keys], dim=-2)
                new_values = torch.cat([old_values, values], dim=-2)
            else:
                new_keys = keys
                new_values = values
            
            new_timestamps = old_timestamps + timestamps
            self.cache[layer_name] = (new_keys, new_values, new_timestamps)
        
        self.token_count += len(timestamps)
        
        # Evict old tokens if over limit
        self._evict_if_needed()
    
    def get(self, layer_name: str) -> tuple[Any, Any] | None:
        """Get KV cache for a layer."""
        if layer_name not in self.cache:
            return None
        
        keys, values, _ = self.cache[layer_name]
        
        if self.quantizer:
            keys, values = self.quantizer.dequantize_kv_cache(keys, values, layer_name)
        
        return keys, values
    
    def get_recent(self, layer_name: str, num_tokens: int) -> tuple[Any, Any] | None:
        """Get most recent KV pairs."""
        cached = self.get(layer_name)
        if not cached:
            return None
        
        keys, values = cached
        if hasattr(keys, 'shape') and keys.shape[-2] > num_tokens:
            return keys[..., -num_tokens:, :], values[..., -num_tokens:, :]
        return keys, values
    
    def _evict_if_needed(self):
        """Evict oldest tokens if over token limit."""
        if self.token_count <= self.max_tokens:
            return
        
        # Evict proportionally from all layers
        excess = self.token_count - self.max_tokens
        for layer_name in list(self.cache.keys()):
            keys, values, timestamps = self.cache[layer_name]
            if hasattr(keys, 'shape'):
                layer_tokens = keys.shape[-2]
                evict_count = min(excess, layer_tokens // 4)
                if evict_count > 0:
                    self.cache[layer_name] = (
                        keys[..., evict_count:, :],
                        values[..., evict_count:, :],
                        timestamps[evict_count:],
                    )
                    self.token_count -= evict_count
                    excess -= evict_count
                    if excess <= 0:
                        break
    
    def save(self):
        """Save cache to disk."""
        if not self.storage_path:
            return
        
        data = {
            "cache": self.cache,
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
        }
        with open(self.storage_path / "kv_cache.pkl", "wb") as f:
            pickle.dump(data, f)
    
    def _load(self):
        """Load cache from disk."""
        path = self.storage_path / "kv_cache.pkl"
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.cache = data.get("cache", {})
            self.token_count = data.get("token_count", 0)
            self.max_tokens = data.get("max_tokens", self.max_tokens)
    
    def clear(self):
        self.cache.clear()
        self.token_count = 0
    
    def get_stats(self) -> dict[str, Any]:
        total_keys = sum(
            k.shape[-2] if hasattr(k, 'shape') else 1
            for k, _, _ in self.cache.values()
        )
        return {
            "layers": len(self.cache),
            "total_tokens": self.token_count,
            "max_tokens": self.max_tokens,
            "utilization": self.token_count / self.max_tokens,
        }


# Integration with agent context
class QuantizedContextManager:
    """Context manager with KV-Cache quantization."""
    
    def __init__(self, config: Config, provider: Any):
        self.config = config
        self.provider = provider
        
        # Quantization config from env
        quant_type = os.getenv("BIFANG_QUANTIZATION", "int8")
        self.quantizer = KVCacheQuantizer(QuantizationConfig(
            quantization_type=QuantizationType(quant_type),
            kv_cache_quant=os.getenv("BIFANG_KV_QUANT", "1") == "1",
        ))
        
        # Persistent cache
        from .config import state_home
        cache_path = state_home() / "kv_cache"
        self.kv_cache = PersistentKVCache(
            max_tokens=config.max_context_tokens,
            quantizer=self.quantizer,
            storage_path=cache_path,
        )
    
    async def calibrate(self, calibration_prompts: list[str]):
        """Calibrate quantization using sample prompts."""
        # This would run the model on calibration prompts
        # to collect activation statistics
        pass
    
    def get_kv_cache(self, layer_name: str) -> tuple[Any, Any] | None:
        return self.kv_cache.get(layer_name)
    
    def append_kv_cache(self, layer_name: str, keys: Any, values: Any):
        self.kv_cache.append(layer_name, keys, values)
    
    def save(self):
        self.kv_cache.save()
    
    def get_stats(self) -> dict[str, Any]:
        return self.kv_cache.get_stats()