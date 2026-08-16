"""WebSocket endpoint for realtime notification delivery.

Browsers can't attach an Authorization header to a WebSocket handshake, so
the access token is passed as a query parameter instead
(`?token=<access_token>`), reusing the same JWT used for the REST API.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import AsyncSessionLocal
from app.services.realtime import connection_manager

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/notifications")
async def notifications_websocket(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        user_id = decode_access_token(token)
    except Exception:  # noqa: BLE001 - any decode failure is an auth failure
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        await websocket.close(code=4401)
        return

    await connection_manager.connect(user.id, websocket)
    try:
        while True:
            # This channel is push-only from the server; we still need to
            # await something so we notice a client disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(user.id, websocket)
