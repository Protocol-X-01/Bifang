from __future__ import annotations

import asyncio

import httpx

from .remote_coding import CodingJobs, snapshot_digest
from .remote_jobs import JobConflict


class CodingCheckWorker:
    def __init__(self, jobs: CodingJobs, runner, *, poll_seconds=0.5):
        self.jobs, self.runner, self.poll_seconds = jobs, runner, poll_seconds

    async def once(self):
        claimed = await asyncio.to_thread(self.jobs.claim_coding, "check")
        if claimed is None:
            return False
        identity, lease = claimed["id"], claimed["lease"]
        request = claimed["request"]
        task = None
        try:
            if snapshot_digest(claimed["candidate"]) != claimed["candidate_sha256"]:
                raise ValueError("Stored candidate does not match its approved hash")
            task = asyncio.create_task(self.runner(claimed["candidate"], request["check_command"], request["check_timeout"]))
            async with asyncio.timeout(request["check_timeout"] + 10):
                while not task.done():
                    await asyncio.wait({task}, timeout=self.poll_seconds)
                    if not await asyncio.to_thread(self.jobs.coding_lease_active, identity, lease):
                        return True
                receipt = await task
            if snapshot_digest(claimed["candidate"]) != claimed["candidate_sha256"]:
                raise ValueError("Check runner changed the approved snapshot")
            if not isinstance(receipt, dict) or set(receipt) != {"candidate_sha256", "command", "exit_code", "timed_out", "output_sha256"}:
                raise ValueError("Require a bounded independent execution receipt")
            await asyncio.to_thread(self.jobs.finish_check, identity, lease, **receipt)
        except asyncio.CancelledError:
            await asyncio.to_thread(self.jobs.fail_coding, identity, lease, "worker_interrupted")
            raise
        except (TimeoutError, ValueError, RuntimeError, TypeError, LookupError, OSError, JobConflict, httpx.HTTPError):
            await asyncio.to_thread(self.jobs.fail_coding, identity, lease, "check_unavailable")
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return True

    async def run(self):
        while True:
            if not await self.once():
                await asyncio.sleep(self.poll_seconds)
