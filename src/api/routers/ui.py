"""Local browser UI for manually exercising the chat API."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["local-ui"])

_UI_FILE = Path(__file__).resolve().parent.parent / "static" / "chat.html"


@router.get("/ui", include_in_schema=False)
def chat_ui() -> FileResponse:
    """Serve the local chat test console."""
    return FileResponse(_UI_FILE, media_type="text/html")
