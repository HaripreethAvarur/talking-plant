"""Compatibility entrypoint: UI, speech routes and sensor API now share one backend."""

from backend import config
from backend.api import create_app

app = create_app()
hub = app.state.ui

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)
