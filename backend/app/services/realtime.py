"""In-memory WebSocket connection registry for realtime notification
delivery.

Single-process only: connections are held in a dict on this module, so this
does not fan out across multiple app instances. That's an acceptable
starting point (matches the rest of this app's single-process SLA
scheduler); a multi-instance deployment would need to swap this for a
pub/sub broker (Redis, etc.) without changing the dispatch call site in
app/services/notification_engine.py.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: UUID, payload: dict) -> bool:
        """Best-effort push to every open socket for `user_id`. Returns True
        if at least one socket received it; False if the user has no live
        connection (not an error -- just means they're offline right now)."""
        sockets = list(self._connections.get(user_id, ()))
        if not sockets:
            return False
        delivered = False
        for socket in sockets:
            try:
                await socket.send_json(payload)
                delivered = True
            except Exception:  # noqa: BLE001 - a dead socket shouldn't break the loop
                logger.info("Dropping dead websocket for user %s", user_id)
                self.disconnect(user_id, socket)
        return delivered


connection_manager = ConnectionManager()
