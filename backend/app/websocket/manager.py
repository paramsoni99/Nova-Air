"""WebSocketManager: Real-time event broadcasting for Nova Air operations center."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Set
from fastapi import WebSocket


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts live operational events."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an incoming WebSocket connection and register it."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast structured event to all connected clients."""
        if not self.active_connections:
            return

        message = {
            "event": event_type,
            "timestamp_utc": int(time.time()),
            "data": payload,
        }
        await self.broadcast_json(message)

    async def broadcast_json(self, message: Dict[str, Any]) -> None:
        """Send JSON message to all active WebSockets, pruning dead connections."""
        dead_connections: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# Global instance
ws_manager = WebSocketManager()
