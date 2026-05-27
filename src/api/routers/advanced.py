"""Read-only Advanced Agent state for local acceptance checks."""

from fastapi import APIRouter, Depends

from src.harness.builder import Harness
from src.harness.deps import get_harness
from src.utils.response import create_success_response

router = APIRouter(prefix="/advanced", tags=["advanced"])


@router.get("/sessions/{session_id}")
async def advanced_session_state(
    session_id: str,
    harness: Harness = Depends(get_harness),
):
    """Expose approval, checkpoint, and handoff evidence for one session."""
    return create_success_response(data=harness.runtime.advanced_state(session_id))
