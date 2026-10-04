"""Run the backend: python -m backend.server (host and port from HOST/PORT in .env)."""

import uvicorn

from backend.api import create_app
from backend.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
