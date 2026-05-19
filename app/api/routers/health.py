from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ok")
async def health() -> dict[str, str]:
    return {"code": "1", "msg": "ok"}
