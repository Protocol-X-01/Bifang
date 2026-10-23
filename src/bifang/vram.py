from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch not available")

try:
    import tensorrt_llm
    from tensorrt_llm.runtime import ModelRunner
    HAS_TENSORRT_LLM = True
except ImportError:
    HAS_TENSORRT_LLM = False


if TYPE_CHECKING:
    import torch
    import torch.nn as nn


class VRAMPressure(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GPUInfo:
    """Information about a GPU device."""
    index: int
    name: str
    total_memory_mb: int
    free_memory_mb: int
    used_memory_mb: int
    utilization_percent: float
    temperature_c: int
    power_draw_w: float
    power_limit_w: float


@dataclass
class ModelLayer:
    """Represents a model layer that can be offloaded."""
    layer_index: int
    name: str
    module: Any = None  # Actual nn.Module reference
    size_mb: float = 0.0
    on_gpu: bool = True
    device: str = "cuda"
    priority: int = 0
    weight_bytes: int = 0
    kv_cache_bytes: int = 0


@dataclass
class OffloadConfig:
    """Configuration for dynamic offloading."""
    enabled: bool = True
    check_interval_sec: int = 5
    high_watermark_percent: float = 0.85
    low_watermark_percent: float = 0.70
    critical_watermark_percent: float = 0.95
    min_layers_on_gpu: int = 4
    offload_batch_size: int = 2
    preferred_offload_device: str = "cpu"


class VRAMManager:
    """Manages dynamic VRAM allocation and layer offloading for PyTorch/TensorRT models."""
    
    def __init__(self, config: OffloadConfig | None = None):
        self.config = config or OffloadConfig()
        self.layers: list[ModelLayer] = []
        self.gpu_info: list[GPUInfo] = []
        self.model_name: str = ""
        self.model_path: str = ""
        self._model: Optional[Any] = None
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._callbacks: dict[str, list[callable]] = {
            "pressure_change": [],
            "offload_complete": [],
            "emergency_offload": [],
        }
        self._device_map: dict[str, str] = {}  # layer_name -> device
    
    async def initialize(self, model_name: str, model_path: str | None = None):
        """Initialize VRAM manager for a model."""
        self.model_name = model_name
        self.model_path = model_path or ""
        await self._detect_gpus()
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def _detect_gpus(self):
        """Detect available GPUs and their memory."""
        self.gpu_info = []
        
        # Try nvidia-smi
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 8:
                        self.gpu_info.append(GPUInfo(
                            index=int(parts[0]),
                            name=parts[1],
                            total_memory_mb=int(float(parts[2])),
                            free_memory_mb=int(float(parts[3])),
                            used_memory_mb=int(float(parts[4])),
                            utilization_percent=float(parts[5]),
                            temperature_c=int(float(parts[6])),
                            power_draw_w=float(parts[6]),
                            power_limit_w=float(parts[7]),
                        ))
        except Exception as e:
            logger.warning(f"Failed to detect GPUs via nvidia-smi: {e}")
        
        # Fallback: try to get GPU info from torch
        if not self.gpu_info and HAS_TORCH:
            try:
                import torch
                if torch.cuda.is_available():
                    for i in range(torch.cuda.device_count()):
                        props = torch.cuda.get_device_properties(i)
                        total_mem = props.total_memory // (1024 * 1024)
                        allocated = torch.cuda.memory_allocated(i) // (1024 * 1024)
                        free_mem = total_mem - allocated
                        self.gpu_info.append(GPUInfo(
                            index=i,
                            name=props.name,
                            total_memory_mb=total_mem,
                            free_memory_mb=free_mem,
                            used_memory_mb=allocated,
                            utilization_percent=0.0,
                            temperature_c=0,
                            power_draw_w=0.0,
                            power_limit_w=0.0,
                        ))
            except ImportError:
                pass
    
    def bind_model(self, model: Any, model_name: str = ""):
        """Bind a PyTorch/TensorRT model for VRAM management."""
        self._model = model
        self.model_name = model_name
        
        # Auto-discover layers from the model
        if hasattr(model, 'named_modules'):
            self._discover_layers_from_model(model)
    
    def _discover_layers_from_model(self, model: Any):
        """Discover model layers for offloading management."""
        self.layers = []
        
        if hasattr(model, 'named_children'):
            # Standard PyTorch model
            layer_idx = 0
            for name, module in model.named_children():
                if self._is_leaf_layer(module):
                    layer = ModelLayer(
                        layer_index=layer_idx,
                        name=name,
                        module=module,
                        size_mb=self._calculate_module_size(module),
                        on_gpu=True,
                        device="cuda",
                        priority=self._calculate_layer_priority(name, layer_idx),
                    )
                    self.layers.append(layer)
                    layer_idx += 1
        elif hasattr(model, 'model') and hasattr(model.model, 'layers'):
            # HuggingFace-style model (model.model.layers)
            for i, layer in enumerate(model.model.layers):
                size_mb = sum(p.numel() * p.element_size() for p in layer.parameters()) / (1024 * 1024)
                self.layers.append(ModelLayer(
                    layer_index=i,
                    name=f"layer_{i}",
                    module=layer,
                    size_mb=size_mb,
                    on_gpu=True,
                    device="cuda",
                    priority=self._calculate_layer_priority(f"layer_{i}", i),
                ))
        elif hasattr(model, 'transformer') and hasattr(model.transformer, 'h'):
            # GPT-style
            for i, layer in enumerate(model.transformer.h):
                size_mb = sum(p.numel() * p.element_size() for p in layer.parameters()) / (1024 * 1024)
                self.layers.append(ModelLayer(
                    layer_index=i,
                    name=f"h_{i}",
                    module=layer,
                    size_mb=size_mb,
                    on_gpu=True,
                    device="cuda",
                    priority=self._calculate_layer_priority(f"h_{i}", i),
                ))
    
    def _is_leaf_layer(self, module: "nn.Module") -> bool:
        """Check if module is a leaf layer (no children with parameters)."""
        child_count = sum(1 for _ in module.children())
        return child_count == 0 and any(True for _ in module.parameters())
    
    def _calculate_module_size(self, module: "nn.Module") -> float:
        """Calculate module size in MB."""
        return sum(p.numel() * p.element_size() for p in module.parameters()) / (1024 * 1024)
    
    def _calculate_layer_priority(self, name: str, index: int) -> int:
        """Calculate layer priority (lower = higher priority to keep on GPU)."""
        name_lower = name.lower()
        
        # Embeddings and output layers - highest priority (keep on GPU)
        if any(kw in name for kw in ['embed', 'wte', 'wpe', 'lm_head', 'output', 'ln_f', 'norm_f']):
            return 0
        
        # First and last few layers - high priority
        # We'll adjust based on position after we know total layers
        return 2  # Default normal priority
    
    def _finalize_priorities(self):
        """Finalize layer priorities after all layers discovered."""
        n = len(self.layers)
        for i, layer in enumerate(self.layers):
            if layer.priority == 2:  # Only adjust default priority layers
                if i < 2 or i >= len(self.layers) - 2:
                    layer.priority = 1  # High priority for first/last layers
    
    def bind_model(self, model: Any, model_name: str = ""):
        """Bind a PyTorch model for VRAM management."""
        self._model = model
        self.model_name = model_name
        self._discover_layers_from_model(model)
        self._finalize_priorities()
    
    def get_vram_pressure(self) -> VRAMPressure:
        """Get current VRAM pressure level."""
        if not self.gpu_info:
            return VRAMPressure.LOW
        
        # Use the GPU with highest utilization
        max_usage = max(
            (gpu.used_memory_mb / gpu.total_memory_mb for gpu in self.gpu_info),
            default=0.0,
        )
        
        if max_usage >= self.config.critical_watermark_percent:
            return VRAMPressure.CRITICAL
        elif max_usage >= self.config.high_watermark_percent:
            return VRAMPressure.HIGH
        elif max_usage >= self.config.low_watermark_percent:
            return VRAMPressure.MEDIUM
        return VRAMPressure.LOW
    
    def get_gpu_stats(self) -> dict[str, Any]:
        """Get current GPU statistics."""
        if not self.gpu_info:
            return {"gpus": [], "pressure": VRAMPressure.LOW.value}
        
        total_mem = sum(g.total_memory_mb for g in self.gpu_info)
        used_mem = sum(g.used_memory_mb for g in self.gpu_info)
        free_mem = sum(g.free_memory_mb for g in self.gpu_info)
        
        return {
            "gpus": [
                {
                    "index": g.index,
                    "name": g.name,
                    "total_mb": g.total_memory_mb,
                    "used_mb": g.used_memory_mb,
                    "free_mb": g.free_memory_mb,
                    "utilization": g.utilization_percent,
                    "temperature_c": g.temperature_c,
                    "power_w": g.power_draw_w,
                }
                for g in self.gpu_info
            ],
            "total_mb": total_mem,
            "used_mb": used_mem,
            "free_mb": free_mem,
            "usage_percent": (used_mem / total_mem * 100) if total_mem > 0 else 0,
            "pressure": self.get_vram_pressure().value,
        }
    
    def get_offloadable_layers(self) -> list[ModelLayer]:
        """Get layers that can be offloaded, sorted by priority (lowest priority first)."""
        offloadable = [l for l in self.layers if l.on_gpu and l.priority > 0]
        return sorted(offloadable, key=lambda l: (l.priority, -l.layer_index))
    
    def get_gpu_layers(self) -> list[ModelLayer]:
        """Get layers currently on GPU."""
        return [l for l in self.layers if l.on_gpu]
    
    async def offload_layers(self, count: int | None = None) -> int:
        """Offload layers from GPU to CPU."""
        if not self.config.enabled:
            return 0
        
        count = count or self.config.offload_batch_size
        offloadable = self.get_offloadable_layers()
        
        offloaded = 0
        for layer in offloadable[:count]:
            if await self._offload_layer(layer):
                offloaded += 1
        
        return offloaded
    
    async def _offload_layer(self, layer: ModelLayer) -> bool:
        """Offload a single layer to CPU using PyTorch."""
        try:
            if layer.module is None:
                logger.warning(f"Layer {layer.layer_index} has no module reference")
                return False
            
            # Move module parameters and buffers to CPU
            layer.module.to("cpu")
            layer.on_gpu = False
            layer.device = self.config.preferred_offload_device
            
            # Clear CUDA cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info(f"Offloaded layer {layer.layer_index} ({layer.name}) to {layer.device} "
                       f"({layer.size_mb:.1f} MB freed)")
            return True
        except Exception as e:
            logger.error(f"Failed to offload layer {layer.layer_index}: {e}")
            return False
    
    async def reload_layers(self, count: int | None = None) -> int:
        """Reload layers back to GPU."""
        if not self.config.enabled:
            return 0
        
        cpu_layers = [l for l in self.layers if not l.on_gpu]
        cpu_layers.sort(key=lambda l: l.priority)  # Reload highest priority first
        
        reloaded = 0
        for layer in cpu_layers[:count]:
            if await self._reload_layer(layer):
                reloaded += 1
        
        return reloaded
    
    async def _reload_layer(self, layer: ModelLayer) -> bool:
        """Reload a layer to GPU."""
        try:
            if layer.module is None:
                logger.warning(f"Layer {layer.layer_index} has no module reference")
                return False
            
            # Move module back to GPU
            layer.module.to("cuda")
            layer.on_gpu = True
            layer.device = "cuda"
            
            logger.info(f"Reloaded layer {layer.layer_index} ({layer.name}) to GPU")
            return True
        except Exception as e:
            logger.error(f"Failed to reload layer {layer.layer_index}: {e}")
            return False
    
    def add_callback(self, event: str, callback: callable):
        """Register a callback for VRAM events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit_event(self, event: str, data: Any):
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")
    
    async def _monitor_loop(self):
        """Background monitoring loop for VRAM pressure."""
        while self._monitoring:
            try:
                await self._detect_gpus()
                
                pressure = self.get_vram_pressure()
                
                if pressure == VRAMPressure.CRITICAL:
                    self._emit_event("emergency_offload", {"pressure": pressure})
                    await self._emergency_offload()
                elif pressure == VRAMPressure.HIGH:
                    self._emit_event("pressure_change", {"pressure": pressure})
                    await self.offload_layers()
                elif pressure == VRAMPressure.LOW:
                    await self.reload_layers()
                
            except Exception as e:
                logger.error(f"VRAM monitor error: {e}")
            
            await asyncio.sleep(self.config.check_interval_sec)
    
    async def _emergency_offload(self):
        """Emergency offload - move as many layers as possible to CPU."""
        logger.warning("CRITICAL VRAM pressure - emergency offloading!")
        
        offloadable = self.get_offloadable_layers()
        for layer in offloadable:
            if self.get_vram_pressure() != VRAMPressure.CRITICAL:
                break
            await self._offload_layer(layer)
        
        self._emit_event("emergency_offload", {"layers_offloaded": len(offloadable)})
    
    async def shutdown(self):
        """Shutdown the VRAM manager."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # Reload all layers back to GPU before shutdown
        await self.reload_layers()


class TensorRTModelLoader:
    """Loads TensorRT-LLM models with VRAM optimization."""
    
    def __init__(self, vram_manager: VRAMManager):
        self.vram_manager = vram_manager
    
    async def load_tensorrt_model(
        self,
        engine_path: str,
        tokenizer_path: str,
        max_batch_size: int = 1,
        max_input_len: int = 8192,
        max_output_len: int = 4096,
    ) -> ModelRunner:
        """Load a TensorRT-LLM engine with VRAM optimization."""
        if not HAS_TENSORRT_LLM:
            raise RuntimeError("TensorRT-LLM not available")
        
        runner = ModelRunner.from_dir(
            engine_path,
            rank=0,
            gpu_id=0,
            max_batch_size=1,
            max_input_len=8192,
            max_output_len=4096,
            enable_kv_cache_reuse=True,
        )
        
        # Estimate layers from engine
        # In practice, you'd parse the engine or use the model config
        return runner
    
    async def load_pytorch_model_with_offloading(
        self,
        model_name: str,
        model_path: str,
        device_map: str = "auto",
        torch_dtype: str = "float16",
        max_gpu_layers: int | None = None,
    ) -> Any:
        """Load a PyTorch model with VRAM-aware offloading."""
        import torch
        from transformers import AutoModelForCausalLM, AutoConfig
        
        config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
        
        # Determine device map with offloading
        if device_map == "auto":
            # Calculate how many layers fit on GPU
            total_layers = getattr(config, 'num_hidden_layers', 32)
            gpu_layers = max_gpu_layers or self._calculate_max_gpu_layers()
            
            device_map = {}
            # Embeddings on GPU
            device_map["model.embed_tokens"] = 0
            device_map["model.norm"] = 0
            device_map["lm_head"] = 0
            
            # Distribute layers
            for i in range(total_layers):
                if i < gpu_layers:
                    device_map[f"model.layers.{i}"] = 0
                else:
                    device_map[f"model.layers.{i}"] = "cpu"
            
            device_map["model.norm"] = 0
            device_map["lm_head"] = 0
        
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            config=config,
            torch_dtype=getattr(torch, torch_dtype),
            device_map=device_map,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        
        self.bind_model(model, model_name)
        return model
    
    def _calculate_max_gpu_layers(self) -> int:
        """Calculate how many layers can fit on GPU."""
        if not self.gpu_info:
            return 8
        
        total_vram_mb = sum(g.free_memory_mb for g in self.gpu_info)
        # Estimate ~2-3 GB per layer for 7B-70B models
        layer_mb = 2048  # Conservative estimate
        return max(1, min(32, total_vram_mb // layer_mb))


def create_vram_manager(config: OffloadConfig | None = None) -> VRAMManager:
    """Create and initialize VRAM manager."""
    manager = VRAMManager(config)
    return manager


# Utility functions for memory management
async def get_available_vram_mb() -> int:
    """Get available VRAM in MB across all GPUs."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return sum(int(line.strip()) for line in result.stdout.strip().split("\n") if line.strip())
    except Exception:
        pass
    return 0


async def get_total_vram_mb() -> int:
    """Get total VRAM in MB across all GPUs."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return sum(int(line.strip()) for line in result.stdout.strip().split("\n") if line.strip())
    except Exception:
        pass
    return 0


def estimate_model_vram(model_name: str, precision: str = "float16") -> int:
    """Estimate VRAM needed for a model."""
    param_estimates = {
        "nano": 1_000_000_000,
        "super": 12_000_000_000,
        "ultra": 55_000_000_000,
    }
    
    params = 0
    for key, value in param_estimates.items():
        if key in model_name.lower():
            params = value
            break
    
    if params == 0:
        params = 7_000_000_000
    
    bytes_per_param = {
        "float16": 2,
        "bfloat16": 2,
        "float32": 4,
        "int8": 1,
        "int4": 0.5,
    }.get(precision, 2)
    
    weights_mb = (params * bytes_per_param) / (1024 * 1024)
    kv_cache_mb = weights_mb * 0.2
    overhead_mb = 1024
    
    return int(weights_mb + kv_cache_mb + overhead_mb)


async def create_vram_optimized_provider(
    config: Config,
    offload_config: OffloadConfig | None = None,
) -> tuple["TieredProviderManager", VRAMManager]:
    """Create a provider manager with VRAM optimization."""
    from .routing import create_tiered_provider
    
    provider = create_tiered_provider(config)
    vram_manager = VRAMManager(offload_config)
    await vram_manager.initialize("bifang-model")
    
    return provider, vram_manager