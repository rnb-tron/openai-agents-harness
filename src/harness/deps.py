"""已装配 Harness 的 FastAPI 依赖。"""

from __future__ import annotations

from fastapi import Request

from src.harness.builder import Harness


def get_harness(request: Request) -> Harness:
    harness = getattr(request.app.state, "harness", None)
    if harness is None:
        raise RuntimeError("Harness is not initialized")
    return harness
