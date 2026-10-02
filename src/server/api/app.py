"""The web application: static client, sprites, and the WebSocket the client talks to."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ..engine.rules.loader import DEFAULT_RESOURCES_DIR, PROJECT_ROOT, load_rules
from . import serialize
from .session import Session

CLIENT_DIR = PROJECT_ROOT / "src" / "client"


def create_app(config_dir: Path | None = None, saves_dir: Path | None = None) -> FastAPI:
    rules = load_rules(config_dir)          # fails here, with a clear message, on a bad config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.session = Session(rules, saves_dir)
        task = asyncio.create_task(app.state.session.run())
        yield
        task.cancel()

    app = FastAPI(title="Civilization", lifespan=lifespan)

    @app.get("/api/rules")
    async def get_rules() -> dict:
        return serialize.rules_payload(rules)

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        session: Session = app.state.session
        await socket.accept()
        session.clients[socket] = None
        try:
            await socket.send_json(session.init_message(None))
            while True:
                message = await socket.receive_json()
                if isinstance(message, dict):
                    await session.handle(socket, message)
        except WebSocketDisconnect:
            pass
        finally:
            session.clients.pop(socket, None)

    app.mount("/resources", StaticFiles(directory=DEFAULT_RESOURCES_DIR), name="resources")
    app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")
    return app
