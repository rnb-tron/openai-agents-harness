"""ASGI 入口。"""

from src.api.app import create_app
from src.core.config import current_settings

app = create_app(current_settings)
