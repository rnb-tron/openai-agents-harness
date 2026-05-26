from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.harness.builder import Harness
from src.harness.deps import get_harness

router = APIRouter(prefix="/health", tags=["health"])


class CapabilitySelectionRequest(BaseModel):
    selected: list[str] = Field(
        default_factory=list,
        description="平台选择的能力名称列表",
    )


@router.get("/ok")
async def health() -> dict[str, str]:
    return {"code": "1", "msg": "ok"}


@router.get("/capabilities")
async def capabilities(harness: Harness = Depends(get_harness)) -> dict:
    return harness.context.capability_snapshot()


@router.get("/capability-catalog")
async def capability_catalog(harness: Harness = Depends(get_harness)) -> dict:
    return harness.context.capability_catalog()


@router.post("/capability-selection/validate")
async def validate_capability_selection(
    request: CapabilitySelectionRequest,
    harness: Harness = Depends(get_harness),
) -> dict:
    return harness.context.validate_capability_selection(request.selected)
