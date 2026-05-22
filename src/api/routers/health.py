from fastapi import APIRouter, Depends

from src.harness.builder import Harness
from src.harness.deps import get_harness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ok")
async def health() -> dict[str, str]:
    return {"code": "1", "msg": "ok"}


@router.get("/capabilities")
async def capabilities(harness: Harness = Depends(get_harness)) -> dict:
    return harness.context.capability_snapshot()
