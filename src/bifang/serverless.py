from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .config import Config


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Types of serverless jobs."""
    CODE_EXECUTION = "code_execution"
    TEST_RUNNER = "test_runner"
    BUILD = "build"
    LINT = "lint"
    TYPE_CHECK = "type_check"
    CUSTOM = "custom"


@dataclass
class JobConfig:
    """Configuration for a serverless job."""
    job_type: JobType = JobType.CODE_EXECUTION
    image: str = "python:3.11-slim"  # Container image
    command: str = ""  # Command to execute
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    timeout: int = 300  # seconds
    cpu: str = "1"  # CPU cores
    memory: str = "2Gi"  # Memory limit
    gpu: bool = False  # Whether to request GPU
    gpu_type: str = ""  # GPU type if needed
    artifacts: list[str] = field(default_factory=list)  # Output artifacts to collect
    secrets: list[str] = field(default_factory=list)  # Secret names to mount


@dataclass
class JobResult:
    """Result of a job execution."""
    job_id: str
    status: JobStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)  # path -> content
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration: float = 0.0
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Job:
    """A serverless job."""
    id: str
    config: JobConfig
    status: JobStatus = JobStatus.PENDING
    result: JobResult | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    nebius_job_id: str | None = None  # Nebius job ID if submitted


class NebiusClient:
    """Client for Nebius Serverless API."""
    
    def __init__(self, api_key: str, endpoint: str = "https://api.nebius.ai"):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def submit_job(self, config: JobConfig) -> str:
        """Submit a job to Nebius Serverless Jobs. Returns job ID."""
        payload = {
            "name": f"bifang-job-{uuid.uuid4().hex[:8]}",
            "image": config.image,
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "working_dir": config.working_dir,
            "resources": {
                "cpu": config.cpu,
                "memory": config.memory,
            },
            "timeout": config.timeout,
        }
        
        if config.gpu:
            payload["resources"]["gpu"] = config.gpu_type or "nvidia.com/gpu=1"
        
        if config.secrets:
            payload["secrets"] = config.secrets
        
        response = await self.client.post(
            f"{self.endpoint}/v1/jobs",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["job_id"]
    
    async def get_job_status(self, job_id: str) -> dict:
        """Get job status from Nebius."""
        response = await self.client.get(f"{self.endpoint}/v1/jobs/{job_id}")
        response.raise_for_status()
        return response.json()
    
    async def get_job_logs(self, job_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Stream job logs."""
        params = {"follow": "true"} if follow else {}
        async with self.client.stream(
            "GET",
            f"{self.endpoint}/v1/jobs/{job_id}/logs",
            params=params,
            timeout=None,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line
    
    async def get_job_artifacts(self, job_id: str) -> dict[str, str]:
        """Download job artifacts."""
        response = await self.client.get(f"{self.endpoint}/v1/jobs/{job_id}/artifacts")
        response.raise_for_status()
        return response.json()
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        response = await self.client.post(f"{self.endpoint}/v1/jobs/{job_id}/cancel")
        return response.status_code == 200


class ServerlessJobManager:
    """Manages serverless job execution with polling and UI updates."""
    
    def __init__(
        self,
        config: Config,
        on_status_update: Callable[[Job], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_complete: Callable[[Job], None] | None = None,
    ):
        self.config = config
        self.on_status_update = on_status_update
        self.on_log = on_log
        self.on_complete = on_complete
        
        self.jobs: dict[str, Job] = {}
        self.client: NebiusClient | None = None
        self._polling_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        
        # Initialize Nebius client if API key available
        nebius_key = os.getenv("NEBIUS_API_KEY")
        if nebius_key:
            self.client = NebiusClient(nebius_key)
    
    async def start(self):
        """Start the job manager."""
        self._running = True
        if self.client:
            # Verify connection
            try:
                await self.client.client.get(f"{self.client.endpoint}/v1/health")
            except Exception:
                self.client = None
    
    async def stop(self):
        """Stop the job manager and cancel all jobs."""
        self._running = False
        for task in self._polling_tasks.values():
            task.cancel()
        await asyncio.gather(*self._polling_tasks.values(), return_exceptions=True)
        
        if self.client:
            await self.client.close()
    
    def _emit_status(self, job: Job):
        """Emit status update."""
        job.updated_at = datetime.now()
        if self.on_status_update:
            self.on_status_update(job)
    
    def _emit_log(self, job_id: str, log: str):
        """Emit log line."""
        if self.on_log:
            self.on_log(log)
    
    def _emit_complete(self, job: Job):
        """Emit completion."""
        if self.on_complete:
            self.on_complete(job)
    
    async def submit_job(self, config: JobConfig) -> Job:
        """Submit a new job."""
        if not self.client:
            raise RuntimeError("Nebius client not configured. Set NEBIUS_API_KEY.")
        
        job_id = f"bifang-{uuid.uuid4().hex[:12]}"
        job = Job(id=job_id, config=config)
        self.jobs[job_id] = job
        
        try:
            job.status = JobStatus.QUEUED
            self._emit_status(job)
            
            nebius_job_id = await self.client.submit_job(config)
            job.nebius_job_id = nebius_job_id
            job.status = JobStatus.RUNNING
            job.result = JobResult(
                job_id=job_id,
                status=JobStatus.RUNNING,
                started_at=datetime.now(),
            )
            self._emit_status(job)
            
            # Start polling task
            self._polling_tasks[job_id] = asyncio.create_task(self._poll_job(job))
            
        except Exception as e:
            job.status = JobStatus.FAILED
            job.result = JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error=str(e),
                completed_at=datetime.now(),
            )
            self._emit_status(job)
            raise
        
        return job
    
    async def _poll_job(self, job: Job):
        """Poll job status until completion."""
        if not job.nebius_job_id or not self.client:
            return
        
        try:
            while self._running:
                await asyncio.sleep(2)  # Poll every 2 seconds
                
                status_data = await self.client.get_job_status(job.nebius_job_id)
                status = status_data.get("status", "unknown")
                
                # Update job status
                old_status = job.status
                job.status = JobStatus(status.upper()) if status.upper() in JobStatus.__members__ else JobStatus.RUNNING
                
                if job.result:
                    job.result.status = job.status
                
                if old_status != job.status:
                    self._emit_status(job)
                
                # Stream logs if running
                if job.status == JobStatus.RUNNING:
                    async for log_line in self.client.get_job_logs(job.nebius_job_id):
                        if not self._running:
                            break
                        self._emit_log(job.id, log_line)
                
                # Check for completion
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    if job.result:
                        job.result.completed_at = datetime.now()
                        if job.result.started_at:
                            job.result.duration = (job.result.completed_at - job.result.started_at).total_seconds()
                        job.result.status = job.status
                    
                    # Fetch artifacts if completed
                    if job.status == JobStatus.COMPLETED and job.config.artifacts:
                        artifacts = await self.client.get_job_artifacts(job.nebius_job_id)
                        if job.result:
                            job.result.artifacts = artifacts
                    
                    self._emit_complete(job)
                    
                    # Clean up polling task
                    self._polling_tasks.pop(job.id, None)
                    break
                    
        except asyncio.CancelledError:
            # Job was cancelled
            job.status = JobStatus.CANCELLED
            if job.result:
                job.result.status = JobStatus.CANCELLED
                job.result.completed_at = datetime.now()
            self._emit_complete(job)
            raise
        except Exception as e:
            job.status = JobStatus.FAILED
            if job.result:
                job.result.status = JobStatus.FAILED
                job.result.error = str(e)
                job.result.completed_at = datetime.now()
            self._emit_complete(job)
        finally:
            self._polling_tasks.pop(job.id, None)
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        job = self.jobs.get(job_id)
        if not job or not job.nebius_job_id or not self.client:
            return False
        
        success = await self.client.cancel_job(job.nebius_job_id)
        if success:
            job.status = JobStatus.CANCELLED
            if job.result:
                job.result.status = JobStatus.CANCELLED
                job.result.completed_at = datetime.now()
            self._emit_status(job)
        return success
    
    async def get_job_result(self, job_id: str) -> JobResult | None:
        """Get job result."""
        job = self.jobs.get(job_id)
        return job.result if job else None
    
    async def wait_for_job(self, job_id: str, timeout: float = 300) -> JobResult:
        """Wait for job completion with timeout."""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        start = time.time()
        while job.status in (JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RUNNING):
            if time.time() - start > timeout:
                raise TimeoutError(f"Job {job_id} timed out after {timeout}s")
            await asyncio.sleep(1)
        
        return job.result
    
    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> list[Job]:
        return list(self.jobs.values())


# Predefined job templates for common tasks
class JobTemplates:
    """Predefined job templates for common development tasks."""
    
    @staticmethod
    def python_test_runner(
        test_path: str = ".",
        test_args: list[str] | None = None,
        coverage: bool = True,
    ) -> JobConfig:
        args = ["-m", "pytest", test_path]
        if test_args:
            args.extend(test_args)
        if coverage:
            args.extend(["--cov", "--cov-report=term-missing"])
        
        return JobConfig(
            job_type=JobType.TEST_RUNNER,
            image="python:3.11-slim",
            command="python",
            args=args,
            working_dir="/workspace",
            artifacts=["htmlcov/", ".coverage", "test-results.xml"],
        )
    
    @staticmethod
    def python_linter(
        lint_path: str = ".",
        tools: list[str] | None = None,
    ) -> JobConfig:
        tools = tools or ["ruff", "mypy", "bandit"]
        return JobConfig(
            job_type=JobType.LINT,
            image="python:3.11-slim",
            command="sh",
            args=["-c", " && ".join([
                f"{tool} ." if tool != "bandit" else "bandit -r ."
                for tool in tools
            ])],
            working_dir="/workspace",
        )
    
    @staticmethod
    def code_executor(
        code: str,
        language: str = "python",
        timeout: int = 60,
    ) -> JobConfig:
        """Execute arbitrary code in a sandbox."""
        if language == "python":
            return JobConfig(
                job_type=JobType.CODE_EXECUTION,
                image="python:3.11-slim",
                command="python",
                args=["-c", code],
                timeout=timeout,
            )
        elif language == "javascript":
            return JobConfig(
                job_type=JobType.CODE_EXECUTION,
                image="node:20-slim",
                command="node",
                args=["-e", code],
                timeout=timeout,
            )
        elif language == "bash":
            return JobConfig(
                job_type=JobType.CODE_EXECUTION,
                image="ubuntu:22.04",
                command="bash",
                args=["-c", code],
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    @staticmethod
    def build_project(
        build_command: str = "make",
        dockerfile: str = "Dockerfile",
    ) -> JobConfig:
        return JobConfig(
            job_type=JobType.BUILD,
            image="docker:24-dind",
            command="sh",
            args=["-c", f"docker build -f {dockerfile} -t bifang-build . && {build_command}"],
            working_dir="/workspace",
            timeout=600,
        )


async def create_job_manager(config: Config) -> ServerlessJobManager:
    """Create and initialize a job manager."""
    manager = ServerlessJobManager(config)
    await manager.start()
    return manager