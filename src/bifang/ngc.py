from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from .config import Config


class NGCFramework(Enum):
    TENSORRT = "tensorrt"
    TENSORRT_LLM = "tensorrt_llm"
    PYTORCH = "pytorch"
    ONNX = "onnx"
    SAVED_MODEL = "saved_model"


class NGCModelFormat(Enum):
    TENSORRT_ENGINE = "tensorrt_engine"
    TENSORRT_LLM_ENGINE = "tensorrt_llm_engine"
    ONNX = "onnx"
    PYTORCH = "pytorch"
    SAFETENSORS = "safetensors"


@dataclass
class NGCModel:
    """A model from NGC."""
    name: str
    org_name: str
    team_name: str
    display_name: str
    description: str
    framework: str
    model_format: str
    precision: str
    labels: list[str]
    latest_version: str
    size_bytes: int
    created_date: str
    updated_date: str
    tags: list[str]
    is_public: bool
    can_guest_download: bool


@dataclass
class NGCModelVersion:
    """A version of an NGC model."""
    version_id: str
    size_bytes: int
    created_date: str
    updated_date: str
    download_url: str | None = None


class NGCClient:
    """Client for NVIDIA GPU Cloud (NGC) API."""
    
    BASE_URL = "https://api.ngc.nvidia.com/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make an NGC API request."""
        url = f"{self.BASE_URL}{endpoint}"
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    async def list_models(
        self,
        page_size: int = 25,
        page: int = 0,
        filter_query: str | None = None,
        framework: str | None = None,
        labels: list[str] | None = None,
    ) -> list["NGCModel"]:
        """List models from NGC."""
        params = {"page_size": page_size, "page": page}
        if filter_query:
            params["filter"] = filter_query
        if framework:
            params["framework"] = framework
        if labels:
            params["labels"] = ",".join(labels)
        
        data = await self._request("GET", "/models", params=params)
        models = []
        for item in data.get("models", []):
            models.append(NGCModel(
                name=item["name"],
                org_name=item["orgName"],
                team_name=item["teamName"],
                display_name=item.get("displayName", item["name"]),
                description=item.get("shortDescription", ""),
                framework=item.get("framework", ""),
                model_format=item.get("modelFormat", ""),
                precision=item.get("precision", ""),
                labels=item.get("labels", []),
                latest_version=item.get("latestVersionIdStr", ""),
                size_bytes=item.get("latestVersionSizeInBytes", 0),
                created_date=item.get("createdDate", ""),
                updated_date=item.get("updatedDate", ""),
                tags=item.get("labels", []),
                is_public=item.get("isPublic", False),
                can_guest_download=item.get("canGuestDownload", False),
            ))
        return models
    
    async def get_model(self, org_name: str, team_name: str, model_name: str) -> "NGCModel":
        """Get a specific model by org/team/name."""
        models = await self.list_models(filter_query=f"name:{model_name}", labels=[f"org:{org_name}", f"team:{team_name}"])
        for model in models:
            if model.name == model_name and model.team_name == team_name:
                return model
        raise ValueError(f"Model not found: {org_name}/{team_name}/{model_name}")
    
    async def get_model_versions(self, org_name: str, team_name: str, model_name: str) -> list["NGCModelVersion"]:
        """Get all versions of a model."""
        model = await self.get_model(org_name, team_name, model_name)
        return [NGCModelVersion(
            version_id=model.latest_version,
            size_bytes=model.size_bytes,
            created_date=model.created_date,
            updated_date=model.updated_date,
        )]
    
    async def search_models(
        self,
        query: str,
        framework: str | None = None,
        model_format: str | None = None,
        precision: str | None = None,
    ) -> list["NGCModel"]:
        """Search models by query."""
        filters = []
        if framework:
            filters.append(f"framework:{framework}")
        if model_format:
            filters.append(f"model_format:{model_format}")
        if precision:
            filters.append(f"precision:{precision}")
        
        filter_query = " ".join(filters) if filters else ""
        return await self.list_models(filter_query=query, framework=framework)
    
class NGCModelRegistry:
    """Registry for NGC models with caching."""
    
    def __init__(self, client: NGCClient):
        self.client = client
        self._cache: dict[str, "NGCModel"] = {}
        self._last_refresh = 0
        self._cache_ttl = 3600
    
    async def refresh(self):
        models = await self.client.list_models(page_size=100)
        self._cache = {f"{m.org_name}/{m.team_name}/{m.name}": m for m in models}
        self._last_refresh = asyncio.get_event_loop().time()
    
    async def get_model(self, key: str) -> "NGCModel | None":
        if asyncio.get_event_loop().time() - self._last_refresh > self._cache_ttl:
            await self.refresh()
        return self._cache.get(key)
    
    async def find_tensorrt_llm_models(self) -> list[dict[str, Any]]:
        models = await self.client.list_models(
            framework="tensorrt",
            labels=["tensorrt_llm"],
            page_size=100,
        )
        return [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "size_bytes": m.size_bytes,
                "version": m.latest_version,
                "org": m.org_name,
                "team": m.team_name,
            }
            for m in models
        ]
    
    async def find_nemotron_models(self) -> list[dict[str, Any]]:
        models = await self.client.list_models(
            filter_query="nemotron",
            page_size=100,
        )
        return [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "precision": m.precision,
                "size_bytes": m.size_bytes,
                "version": m.latest_version,
                "org": m.org_name,
                "team": m.team_name,
                "framework": m.framework,
                "model_format": m.model_format,
                "precision": m.precision,
            }
            for m in models
        ]


async def create_ngc_client(config: Config) -> NGCClient:
    """Create NGC client from config."""
    api_key = os.getenv("NGC_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NGC_API_KEY or NVIDIA_API_KEY not set")
    return NGCClient(api_key)


async def create_ngc_registry(config: Config) -> NGCModelRegistry:
    """Create NGC model registry."""
    client = await create_ngc_client(config)
    return NGCModelRegistry(client)
