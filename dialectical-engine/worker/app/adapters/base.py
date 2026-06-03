from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class ModelClient(Protocol):
    model_id: str
    role_pool: set[str]

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        ...

    async def health_check(self) -> bool:
        ...

