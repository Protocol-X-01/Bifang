from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from .config import Config
from .provider import ProviderManager


class ImageModel(Enum):
    DALL_E_3 = "dall-e-3"
    DALL_E_2 = "dall-e-2"
    STABLE_DIFFUSION_XL = "stable-diffusion-xl"
    STABLE_DIFFUSION_3 = "stable-diffusion-3"
    MIDJOURNEY = "midjourney"
    FLUX = "flux"
    FLUX_SCHNELL = "flux-schnell"
    IDEOGRAM = "ideogram"


class VideoModel(Enum):
    SORA = "sora"
    RUNWAY_GEN3 = "runway-gen3"
    LUMA_DREAM_MACHINE = "luma-dream-machine"
    PIKA = "pika"
    STABLE_VIDEO_DIFFUSION = "stable-video-diffusion"
    ZEROSCOPE = "zeroscope"


class TranslationModel(Enum):
    GPT_4O = "gpt-4o"
    CLAUDE_35_SONNET = "claude-3-5-sonnet"
    NEMOTRON_3_ULTRA = "nvidia/nemotron-3-ultra"
    DEEPL = "deepl"
    GOOGLE_TRANSLATE = "google-translate"
    LIBRETRANSLATE = "libretranslate"


@dataclass
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str | None = None
    model: ImageModel = ImageModel.DALL_E_3
    width: int = 1024
    height: int = 1024
    steps: int = 30
    guidance_scale: float = 7.5
    seed: int | None = None
    n: int = 1
    format: str = "png"  # png, jpg, webp
    quality: str = "standard"  # standard, hd
    style: str = "vivid"  # vivid, natural


@dataclass
class ImageGenerationResult:
    images: list[dict]  # {url, base64, revised_prompt}
    model: ImageModel
    prompt: str
    revised_prompt: str | None = None
    seed: int | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    generation_time_sec: float = 0.0


@dataclass
class VideoGenerationRequest:
    prompt: str
    model: VideoModel = VideoModel.RUNWAY_GEN3
    duration: int = 5  # seconds
    fps: int = 24
    width: int = 1024
    height: int = 576
    seed: int | None = None
    motion_bucket_id: int | None = None
    fps_control: bool = False


@dataclass
class VideoGenerationResult:
    video_url: str
    model: VideoModel
    prompt: str
    duration: int
    width: int
    height: int
    seed: int | None = None
    generation_time_sec: float = 0.0
    cost_usd: float = 0.0
    status: str = "completed"  # completed, processing, failed
    task_id: str | None = None


@dataclass
class TranslationRequest:
    text: str
    source_lang: str  # ISO 639-1 code, "auto" for auto-detect
    target_lang: str  # ISO 639-1 code
    model: TranslationModel = TranslationModel.NEMOTRON_3_ULTRA
    context: str = ""  # Additional context for better translation
    preserve_formatting: bool = True
    glossary: dict[str, str] | None = None  # Term -> translation


@dataclass
class TranslationResult:
    translated_text: str
    source_lang: str
    target_lang: str
    detected_lang: str | None = None
    model: TranslationModel = TranslationModel.NEMOTRON_3_ULTRA
    tokens_used: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    confidence: float = 1.0


class ImageGenerator:
    """Generates images using various AI models."""
    
    def __init__(self, provider: ProviderManager, config: Config):
        self.provider = provider
        self.config = config
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.stability_key = os.getenv("STABILITY_API_KEY", "")
        self.replicate_key = os.getenv("REPLICATE_API_TOKEN", "")
    
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        start_time = time.time()
        
        if request.model == ImageModel.DALL_E_3 or request.model == ImageModel.DALL_E_2:
            return await self._generate_openai(request)
        elif request.model in (ImageModel.STABLE_DIFFUSION_XL, ImageModel.STABLE_DIFFUSION_3):
            return await self._generate_stability(request)
        elif request.model in (ImageModel.FLUX, ImageModel.FLUX_SCHNELL):
            return await self._generate_replicate(request)
        else:
            raise ValueError(f"Unsupported image model: {request.model}")
    
    async def _generate_openai(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": request.model.value,
                "prompt": request.prompt,
                "n": request.n,
                "size": f"{request.width}x{request.height}",
                "quality": request.quality,
                "style": request.style,
                "response_format": "b64_json",
            }
            
            if request.model == ImageModel.DALL_E_3:
                # DALL-E 3 only supports 1024x1024, 1792x1024, 1024x1792
                pass
            
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            images = []
            for img in data["data"]:
                images.append({
                    "base64": img.get("b64_json", ""),
                    "url": img.get("url", ""),
                    "revised_prompt": img.get("revised_prompt", ""),
                })
            
            return ImageGenerationResult(
                images=images,
                model=request.model,
                prompt=request.prompt,
                revised_prompt=data["data"][0].get("revised_prompt") if data["data"] else None,
                generation_time_sec=time.time() - start_time,
                cost_usd=self._estimate_cost(request.model, request.n, request.quality),
            )
    
    async def _generate_stability(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if not self.stability_key:
            raise ValueError("STABILITY_API_KEY not set")
        
        # Map model to Stability engine
        engine_map = {
            ImageModel.STABLE_DIFFUSION_XL: "stable-diffusion-xl-1024-v1-0",
            ImageModel.STABLE_DIFFUSION_3: "stable-diffusion-3",
        }
        
        engine = engine_map.get(request.model, "stable-diffusion-xl-1024-v1-0")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "text_prompts": [
                    {"text": request.prompt, "weight": 1.0},
                ],
                "cfg_scale": request.guidance_scale,
                "steps": request.steps,
                "width": request.width,
                "height": request.height,
                "samples": request.n,
                "seed": request.seed,
            }
            
            if request.negative_prompt:
                payload["text_prompts"].append({
                    "text": request.negative_prompt,
                    "weight": -1.0,
                })
            
            headers = {
                "Authorization": f"Bearer {self.stability_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            
            response = await client.post(
                f"https://api.stability.ai/v1/generation/{engine}/text-to-image",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            images = []
            for artifact in data["artifacts"]:
                images.append({
                    "base64": artifact["base64"],
                    "url": "",
                    "seed": artifact.get("seed", 0),
                })
            
            return ImageGenerationResult(
                images=images,
                model=request.model,
                prompt=request.prompt,
                seed=request.seed,
                generation_time_sec=time.time() - start_time,
                cost_usd=0.0,  # Stability pricing varies
            )
    
    async def _generate_replicate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if not self.replicate_key:
            raise ValueError("REPLICATE_API_TOKEN not set")
        
        model_map = {
            ImageModel.FLUX: "black-forest-labs/flux-schnell",
            ImageModel.FLUX_SCHNELL: "black-forest-labs/flux-schnell",
        }
        
        model = model_map.get(request.model, "black-forest-labs/flux-schnell")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            payload = {
                "input": {
                    "prompt": request.prompt,
                    "width": request.width,
                    "height": request.height,
                    "num_outputs": request.n,
                    "guidance_scale": request.guidance_scale,
                    "num_inference_steps": request.steps,
                }
            }
            
            if request.seed:
                payload["input"]["seed"] = request.seed
            
            headers = {
                "Authorization": f"Token {self.replicate_key}",
                "Content-Type": "application/json",
            }
            
            # Start prediction
            response = await client.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            prediction = response.json()
            
            # Poll for completion
            prediction_id = prediction["id"]
            while prediction["status"] not in ("succeeded", "failed", "canceled"):
                await asyncio.sleep(2)
                response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers,
                )
                prediction = response.json()
            
            if prediction["status"] == "failed":
                raise RuntimeError(f"Replicate prediction failed: {prediction.get('error')}")
            
            images = []
            for url in prediction.get("output", []):
                images.append({
                    "url": url,
                    "base64": "",
                })
            
            return ImageGenerationResult(
                images=images,
                model=request.model,
                prompt=request.prompt,
                generation_time_sec=time.time() - start_time,
            )
    
    def _estimate_cost(self, model: ImageModel, n: int, quality: str) -> float:
        costs = {
            ImageModel.DALL_E_3: {"standard": 0.04, "hd": 0.08},
            ImageModel.DALL_E_2: {"standard": 0.02, "hd": 0.04},
        }
        return costs.get(model, {}).get(quality, 0.04) * n


class VideoGenerator:
    """Generates videos using various AI models."""
    
    def __init__(self, config: Config):
        self.config = config
        self.runway_key = os.getenv("RUNWAY_API_KEY", "")
        self.luma_key = os.getenv("LUMA_API_KEY", "")
        self.pika_key = os.getenv("PIKA_API_KEY", "")
        self.replicate_key = os.getenv("REPLICATE_API_TOKEN", "")
    
    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        start_time = time.time()
        
        if request.model == VideoModel.RUNWAY_GEN3:
            return await self._generate_runway(request)
        elif request.model == VideoModel.LUMA_DREAM_MACHINE:
            return await self._generate_luma(request)
        elif request.model == VideoModel.PIKA:
            return await self._generate_pika(request)
        elif request.model in (VideoModel.STABLE_VIDEO_DIFFUSION, VideoModel.ZEROSCOPE):
            return await self._generate_replicate_video(request)
        else:
            raise ValueError(f"Unsupported video model: {request.model}")
    
    async def _generate_runway(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not self.runway_key:
            raise ValueError("RUNWAY_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            payload = {
                "prompt": request.prompt,
                "model": "gen3a_turbo",
                "duration": request.duration,
                "width": request.width,
                "height": request.height,
                "seed": request.seed,
            }
            
            headers = {
                "Authorization": f"Bearer {self.runway_key}",
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                "https://api.runwayml.com/v1/generations",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            task = response.json()
            
            # Poll for completion
            task_id = task["id"]
            while True:
                await asyncio.sleep(5)
                response = await client.get(
                    f"https://api.runwayml.com/v1/generations/{task_id}",
                    headers=headers,
                )
                task = response.json()
                if task["status"] in ("SUCCEEDED", "FAILED"):
                    break
            
            if task["status"] == "FAILED":
                raise RuntimeError(f"Runway generation failed: {task.get('error')}")
            
            return VideoGenerationResult(
                video_url=task["output"][0] if task.get("output") else "",
                model=request.model,
                prompt=request.prompt,
                duration=request.duration,
                width=request.width,
                height=request.height,
                seed=request.seed,
                generation_time_sec=time.time() - start_time,
                task_id=task_id,
            )
    
    async def _generate_luma(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not self.luma_key:
            raise ValueError("LUMA_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            payload = {
                "prompt": request.prompt,
                "aspect_ratio": f"{request.width}:{request.height}",
                "duration": request.duration,
                "loop": False,
            }
            
            headers = {
                "Authorization": f"Bearer {self.luma_key}",
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                "https://api.lumalabs.ai/dream-machine/v1/generations",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            task = response.json()
            
            task_id = task["id"]
            while True:
                await asyncio.sleep(10)
                response = await client.get(
                    f"https://api.lumalabs.ai/dream-machine/v1/generations/{task_id}",
                    headers=headers,
                )
                task = response.json()
                if task["state"] in ("completed", "failed"):
                    break
            
            if task["state"] == "failed":
                raise RuntimeError(f"Luma generation failed: {task.get('failure_reason')}")
            
            return VideoGenerationResult(
                video_url=task["assets"]["video"] if task.get("assets") else "",
                model=request.model,
                prompt=request.prompt,
                duration=request.duration,
                width=request.width,
                height=request.height,
                generation_time_sec=time.time() - start_time,
                task_id=task_id,
            )
    
    async def _generate_pika(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not self.pika_key:
            raise ValueError("PIKA_API_KEY not set")
        
        # Pika API integration
        return VideoGenerationResult(
            video_url="",
            model=request.model,
            prompt=request.prompt,
            status="not_implemented",
        )
    
    async def _generate_replicate_video(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not self.replicate_key:
            raise ValueError("REPLICATE_API_TOKEN not set")
        
        model_map = {
            VideoModel.STABLE_VIDEO_DIFFUSION: "stability-ai/stable-video-diffusion",
            VideoModel.ZEROSCOPE: "anotherjesse/zeroscope-v2-xl",
        }
        
        model = model_map.get(request.model, "stability-ai/stable-video-diffusion")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            payload = {
                "input": {
                    "prompt": request.prompt,
                    "width": request.width,
                    "height": request.height,
                    "num_frames": request.duration * request.fps,
                    "fps": request.fps,
                }
            }
            
            if request.seed:
                payload["input"]["seed"] = request.seed
            
            headers = {
                "Authorization": f"Token {self.replicate_key}",
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            prediction = response.json()
            
            prediction_id = prediction["id"]
            while prediction["status"] not in ("succeeded", "failed", "canceled"):
                await asyncio.sleep(5)
                response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={
                        "Authorization": f"Token {self.replicate_key}",
                    },
                )
                prediction = response.json()
            
            if prediction["status"] == "failed":
                raise RuntimeError(f"Replicate prediction failed: {prediction.get('error')}")
            
            video_url = prediction["output"][0] if isinstance(prediction.get("output"), list) else prediction.get("output", "")
            
            return VideoGenerationResult(
                video_url=video_url,
                model=request.model,
                prompt=request.prompt,
                duration=request.duration,
                width=request.width,
                height=request.height,
                generation_time_sec=time.time() - start_time,
                task_id=prediction_id,
            )


class Translator:
    """Translates text using various models."""
    
    def __init__(self, provider: ProviderManager, config: Config):
        self.provider = provider
        self.config = config
        self.deepl_key = os.getenv("DEEPL_API_KEY", "")
        self.google_key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
    
    async def translate(self, request: TranslationRequest) -> TranslationResult:
        start_time = time.time()
        
        if request.model == TranslationModel.DEEPL:
            return await self._translate_deepl(request)
        elif request.model == TranslationModel.GOOGLE_TRANSLATE:
            return await self._translate_google(request)
        elif request.model == TranslationModel.LIBRETRANSLATE:
            return await self._translate_libretranslate(request)
        else:
            # Use LLM provider (Nemotron, GPT-4o, Claude)
            return await self._translate_llm(request)
    
    async def _translate_llm(self, request: TranslationRequest) -> TranslationResult:
        prompt = self._build_translation_prompt(request)
        
        response = await self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self.config.get_default_model(),
            provider=self.config.default_provider,
            temperature=0.1,
            max_tokens=4096,
        )
        
        translated = response.get("content", "").strip()
        
        return TranslationResult(
            translated_text=translated,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            model=request.model,
            tokens_used=response.get("usage", {}).get("total_tokens", 0),
            cost_usd=0.0,  # Included in LLM cost
            latency_ms=(time.time() - start_time) * 1000,
        )
    
    def _build_translation_prompt(self, request: TranslationRequest) -> str:
        parts = [
            f"Translate the following text from {request.source_lang} to {request.target_lang}.",
        ]
        
        if request.context:
            parts.append(f"\nContext: {request.context}")
        
        if request.glossary:
            parts.append("\nGlossary (must use these translations):")
            for term, trans in request.glossary.items():
                parts.append(f"  {term} → {trans}")
        
        if request.preserve_formatting:
            parts.append("\nPreserve all formatting (markdown, code blocks, whitespace, etc.)")
        
        parts.append(f"\nText to translate:\n{request.text}")
        parts.append("\nTranslation:")
        
        return "\n".join(parts)
    
    async def _translate_deepl(self, request: TranslationRequest) -> TranslationResult:
        if not self.deepl_key:
            raise ValueError("DEEPL_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "text": [request.text],
                "target_lang": request.target_lang.upper(),
            }
            
            if request.source_lang != "auto":
                payload["source_lang"] = request.source_lang.upper()
            
            if request.glossary:
                payload["glossary_id"] = request.glossary.get("glossary_id", "")
            
            headers = {
                "Authorization": f"DeepL-Auth-Key {self.deepl_key}",
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                "https://api-free.deepl.com/v2/translate",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            return TranslationResult(
                translated_text=data["translations"][0]["text"],
                source_lang=data["translations"][0].get("detected_source_language", request.source_lang).lower(),
                target_lang=request.target_lang,
                model=TranslationModel.DEEPL,
                latency_ms=(time.time() - start_time) * 1000,
            )
    
    async def _translate_google(self, request: TranslationRequest) -> TranslationResult:
        if not self.google_key:
            raise ValueError("GOOGLE_TRANSLATE_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "q": request.text,
                "target": request.target_lang,
            }
            
            if request.source_lang != "auto":
                payload["source"] = request.source_lang
            
            response = await client.post(
                f"https://translation.googleapis.com/language/translate/v2?key={self.google_key}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            translation = data["data"]["translations"][0]
            
            return TranslationResult(
                translated_text=translation["translatedText"],
                source_lang=translation.get("detectedSourceLanguage", request.source_lang),
                target_lang=request.target_lang,
                model=TranslationModel.GOOGLE_TRANSLATE,
                latency_ms=(time.time() - start_time) * 1000,
            )
    
    async def _translate_libretranslate(self, request: TranslationRequest) -> TranslationResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "q": request.text,
                "source": request.source_lang,
                "target": request.target_lang,
            }
            
            response = await client.post(
                "https://libretranslate.de/translate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            return TranslationResult(
                translated_text=data["translatedText"],
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                model=TranslationModel.LIBRETRANSLATE,
                latency_ms=(time.time() - start_time) * 1000,
            )


class MultiModalManager:
    """Unified manager for all multi-modal capabilities."""
    
    def __init__(self, config: Config, provider: ProviderManager):
        self.config = config
        self.provider = provider
        self.image_generator = ImageGenerator(provider, config)
        self.video_generator = VideoGenerator(config)
        self.translator = Translator(provider, config)
    
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        return await self.image_generator.generate(request)
    
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        return await self.video_generator.generate(request)
    
    async def translate(self, request: TranslationRequest) -> TranslationResult:
        return await self.translator.translate(request)
    
    async def batch_translate(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        model: TranslationModel = TranslationModel.NEMOTRON_3_ULTRA,
    ) -> list[TranslationResult]:
        """Batch translate multiple texts."""
        results = []
        for text in texts:
            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                model=model,
            )
            result = await self.translate(request)
            results.append(result)
        return results
    
    async def translate_file(
        self,
        file_path: str,
        target_lang: str,
        source_lang: str = "auto",
        model: TranslationModel = TranslationModel.NEMOTRON_3_ULTRA,
    ) -> str:
        """Translate a file preserving format."""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        
        # Preserve code blocks, frontmatter, etc.
        # For now, simple translation
        request = TranslationRequest(
            text=content,
            source_lang=source_lang,
            target_lang=target_lang,
            model=model,
            preserve_formatting=True,
        )
        
        result = await self.translate(request)
        return result.translated_text