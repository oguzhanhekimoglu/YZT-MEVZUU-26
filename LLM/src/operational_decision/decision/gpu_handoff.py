"""GPU release gate and in-process sequential batch coordination."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from operational_decision.contracts.request import GPUHandoff


class GPUHandoffGate:
    """Refuse local LLM startup until upstream explicitly releases the GPU."""

    @staticmethod
    def is_released(handoff: GPUHandoff) -> bool:
        """Return true only for the exact binding release signal."""
        return (
            handoff.visual_pipeline_status == "COMPLETED"
            and handoff.gpu_release_status == "RELEASED"
        )


class BatchCoordinator:
    """Serialize same-video events and all local LLM inference in one process."""

    def __init__(self) -> None:
        """Create independent video and global inference locks."""
        self._video_locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    async def _video_lock(self, video_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            return self._video_locks.setdefault(video_id, asyncio.Lock())

    @asynccontextmanager
    async def video_batch(self, video_id: str) -> AsyncIterator[None]:
        """Serialize the complete lifecycle for one video identifier."""
        lock = await self._video_lock(video_id)
        async with lock:
            yield

    @asynccontextmanager
    async def llm_inference(self) -> AsyncIterator[None]:
        """Prevent concurrent Decision LLM inference across all videos."""
        async with self._inference_lock:
            yield
