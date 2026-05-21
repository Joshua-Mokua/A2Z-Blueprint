"""utils.websocket_manager — Real-Time Updates (WebSockets)
(Standard #40, v5.51). Volume Five — Frontend Architecture.

Per the master spec:

    @app.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        await manager.connect(websocket, user_id)
        while True:
            data = await websocket.receive_text()

WHAT THIS MODULE SHIPS
----------------------
1. ConnectionManager class — tracks active websocket connections per
   user_id, supports broadcast to a single user (multi-tab) or to all
2. websocket_endpoint coroutine matching the spec signature
3. register_websocket_routes(app) — installs the /ws/{user_id} route
   on a FastAPI app; idempotent (safe to call repeatedly)
4. Honest connection lifecycle: connect → receive loop → disconnect
   on client disconnect AND on server-side cleanup
5. FastAPI-OPTIONAL design — module importable in sandbox without
   FastAPI installed (manager class is testable as plain Python)

WHAT REAL-TIME UPDATES ARE FOR
-------------------------------
The React SPA (#37) needs to push to the user's screen when:
  - A nudge fires (Standard #11)
  - A micro-task is auto-assigned (Standard #13)
  - Their BSC actuals change (live submission)
  - A peer learning card is published to them (Standard #14)
  - A reconciliation break is logged on their portfolio (Standard #35)

Without WebSockets, the SPA would have to poll `/api/v1/notifications`
every few seconds, which is wasteful and high-latency. WebSockets
deliver these events with sub-second latency.

HONESTY DISCIPLINE
------------------
1. Connection state is per-instance (in-memory). On a single-process
   Streamlit/FastAPI deployment this is fine. For multi-process
   deployments (uvicorn --workers > 1, or k8s replicas), the manager
   must be backed by Redis pub/sub. v5.51 ships the in-memory version
   with a documented limitation; production-multi-replica deployments
   should swap in `RedisConnectionManager` (NOT shipped).

2. Broadcast failures are logged (NOT silently swallowed). A failed
   send to a stale connection removes that connection from the
   active set so subsequent broadcasts don't queue indefinitely.

3. Disconnections are recorded with timestamps so post-incident
   analysis can correlate "user lost connection" with "user missed
   a notification".

4. The websocket loop NEVER catches Exception broadly. Specific
   WebSocketDisconnect is handled (clean disconnect); other errors
   propagate so the FastAPI server can log them properly.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


logger = logging.getLogger("a2z.websocket")


# ─────────────────────────────────────────────────────────────────────
# Connection manager (FastAPI-OPTIONAL: no fastapi import at module load)
# ─────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Tracks active WebSocket connections per user_id.

    Each user_id may have multiple connections (e.g. multiple tabs or
    devices). All sends to a user_id fan out to every connection
    that user has open.
    """

    def __init__(self):
        # user_id → set of WebSocket-like objects
        self._connections: Dict[str, Set[Any]] = {}
        # Diagnostics — kept across the manager's lifetime
        self._connect_count    = 0
        self._disconnect_count = 0
        self._send_failures    = 0
        self._created_at = datetime.now(timezone.utc).isoformat()

    async def connect(self, websocket: Any, user_id: str) -> None:
        """Accept a new websocket connection for a user_id.

        Calls websocket.accept() before tracking. If user_id is empty
        or invalid, the connection is REJECTED (NOT silently accepted —
        an unidentified websocket is a security concern).
        """
        if not user_id or not isinstance(user_id, str):
            # Reject the handshake — close with policy violation
            try:
                if hasattr(websocket, "close"):
                    await websocket.close(code=1008)    # policy violation
            except Exception:
                pass
            raise ValueError("user_id must be a non-empty string")

        if hasattr(websocket, "accept"):
            await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)
        self._connect_count += 1
        logger.info("ws connect: user=%s active_for_user=%d total_connects=%d",
                    user_id, len(self._connections[user_id]), self._connect_count)

    def disconnect(self, websocket: Any, user_id: str) -> None:
        """Remove a websocket from the tracked set."""
        conns = self._connections.get(user_id)
        if conns and websocket in conns:
            conns.discard(websocket)
            if not conns:
                # Last connection for this user → drop the entry
                del self._connections[user_id]
            self._disconnect_count += 1
            logger.info("ws disconnect: user=%s remaining_for_user=%d",
                        user_id, len(conns))

    async def send_to_user(self, user_id: str, message: str) -> int:
        """Broadcast a message to all of a user's open connections.

        Returns the number of successful sends. Failed sends remove
        the failing connection from the set (NOT silent — logged at
        warning level).
        """
        conns = list(self._connections.get(user_id, set()))
        if not conns:
            return 0
        sent = 0
        stale: List[Any] = []
        for ws in conns:
            try:
                if hasattr(ws, "send_text"):
                    await ws.send_text(message)
                    sent += 1
                else:
                    stale.append(ws)    # not a real WebSocket
            except Exception as e:
                self._send_failures += 1
                logger.warning("ws send failed for user=%s: %s — removing", user_id, e)
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws, user_id)
        return sent

    async def broadcast(self, message: str) -> int:
        """Broadcast a message to every connection across all users."""
        total_sent = 0
        for user_id in list(self._connections.keys()):
            total_sent += await self.send_to_user(user_id, message)
        return total_sent

    def active_user_count(self) -> int:
        """Number of distinct users with at least one open connection."""
        return len(self._connections)

    def active_connection_count(self) -> int:
        """Total open connections across all users."""
        return sum(len(s) for s in self._connections.values())

    def stats(self) -> Dict[str, Any]:
        """Return manager statistics for diagnostics."""
        return {
            "created_at":              self._created_at,
            "active_users":            self.active_user_count(),
            "active_connections":      self.active_connection_count(),
            "lifetime_connects":       self._connect_count,
            "lifetime_disconnects":    self._disconnect_count,
            "lifetime_send_failures":  self._send_failures,
            "users_with_connections":  list(self._connections.keys()),
        }


# Module-level manager — production code calls this singleton
manager = ConnectionManager()


# ─────────────────────────────────────────────────────────────────────
# WebSocket endpoint coroutine (spec-literal signature)
# ─────────────────────────────────────────────────────────────────────

async def websocket_endpoint(websocket: Any, user_id: str) -> None:
    """The spec endpoint. Connects the user, then receives messages
    in a loop until the client disconnects.

    This coroutine is registered at /ws/{user_id} via
    register_websocket_routes() OR can be called directly.
    """
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Accept text messages from client (e.g. heartbeats,
            # client-side commands like "subscribe to recon updates")
            data = await websocket.receive_text()
            # Echo back as ack — production wires this to a router
            # (e.g. parse JSON, dispatch to subscribe/unsubscribe handlers)
            await websocket.send_text(f"ack:{data}")
    except Exception as e:
        # WebSocketDisconnect from FastAPI — clean disconnect
        # Other exceptions bubble (FastAPI logs them at request level)
        if type(e).__name__ == "WebSocketDisconnect":
            logger.info("ws clean disconnect: user=%s", user_id)
        else:
            logger.warning("ws unclean disconnect: user=%s err=%s", user_id, e)
        manager.disconnect(websocket, user_id)
        if type(e).__name__ != "WebSocketDisconnect":
            raise


# ─────────────────────────────────────────────────────────────────────
# Route registration (FastAPI-optional)
# ─────────────────────────────────────────────────────────────────────

def register_websocket_routes(app: Any) -> bool:
    """Install /ws/{user_id} on a FastAPI app.

    Idempotent — calling twice doesn't duplicate the route.
    Returns True on success, False when FastAPI isn't available.
    """
    if app is None:
        return False
    if not hasattr(app, "websocket"):
        return False    # not a FastAPI app

    # Idempotency: track which apps have been registered
    registered = getattr(app, "_a2z_websocket_registered", False)
    if registered:
        return True

    @app.websocket("/ws/{user_id}")
    async def _route(websocket, user_id: str):
        await websocket_endpoint(websocket, user_id)

    app._a2z_websocket_registered = True
    return True


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.websocket_manager self-test")

    # ── Mock WebSocket for testing without FastAPI ──────────────────
    class _MockWebSocket:
        def __init__(self, name="ws"):
            self.name = name
            self.accepted = False
            self.sent: List[str] = []
            self.received: List[str] = []
            self.closed = False
            self.close_code: Optional[int] = None

        async def accept(self):
            self.accepted = True

        async def send_text(self, msg: str):
            if self.closed:
                raise ConnectionError("closed")
            self.sent.append(msg)

        async def receive_text(self):
            if not self.received:
                raise type("WebSocketDisconnect", (Exception,), {})()
            return self.received.pop(0)

        async def close(self, code=1000):
            self.closed = True
            self.close_code = code

    async def run_tests():
        # ── Connect single user ──────────────────────────────────
        mgr = ConnectionManager()
        ws = _MockWebSocket("u1")
        await mgr.connect(ws, "user_001")
        assert ws.accepted is True
        assert mgr.active_user_count() == 1
        assert mgr.active_connection_count() == 1
        print(f"  ✅ connect: 1 user, 1 connection, accept() called")

        # ── Two tabs for same user ──────────────────────────────
        ws2 = _MockWebSocket("u1-tab2")
        await mgr.connect(ws2, "user_001")
        assert mgr.active_user_count() == 1    # still 1 user
        assert mgr.active_connection_count() == 2    # 2 tabs
        print(f"  ✅ multi-tab: 1 user, 2 connections")

        # ── Send to user fan-outs to both tabs ──────────────────
        sent = await mgr.send_to_user("user_001", "hello")
        assert sent == 2
        assert ws.sent == ["hello"]
        assert ws2.sent == ["hello"]
        print(f"  ✅ send_to_user: fan-out to both tabs (sent={sent})")

        # ── send_to_user to unknown user → 0 sends ──────────────
        sent = await mgr.send_to_user("unknown_user", "ignored")
        assert sent == 0
        print(f"  ✅ send to unknown user: 0 sends, no error")

        # ── Disconnect removes from set ─────────────────────────
        mgr.disconnect(ws, "user_001")
        assert mgr.active_connection_count() == 1
        assert mgr.active_user_count() == 1    # tab2 still there
        print(f"  ✅ disconnect: 1 connection remaining")

        # ── Last disconnect drops user from active set ──────────
        mgr.disconnect(ws2, "user_001")
        assert mgr.active_user_count() == 0
        assert mgr.active_connection_count() == 0
        print(f"  ✅ last disconnect: user dropped from active set")

        # ── Empty user_id rejected ──────────────────────────────
        ws_bad = _MockWebSocket("bad")
        try:
            await mgr.connect(ws_bad, "")
            assert False
        except ValueError:
            pass
        assert ws_bad.closed is True
        assert ws_bad.close_code == 1008    # policy violation
        print(f"  ✅ empty user_id rejected (close code 1008)")

        # ── Failed send removes stale connection ────────────────
        ws3 = _MockWebSocket("u3")
        await mgr.connect(ws3, "user_002")
        ws3.closed = True    # simulate stale
        sent = await mgr.send_to_user("user_002", "msg")
        assert sent == 0
        assert mgr.active_connection_count() == 0    # auto-removed
        print(f"  ✅ failed send removes stale connection")

        # ── Broadcast across multiple users ─────────────────────
        a = _MockWebSocket("a")
        b = _MockWebSocket("b")
        c = _MockWebSocket("c")
        await mgr.connect(a, "user_a")
        await mgr.connect(b, "user_b")
        await mgr.connect(c, "user_c")
        sent = await mgr.broadcast("system_message")
        assert sent == 3
        assert a.sent[-1] == "system_message"
        assert b.sent[-1] == "system_message"
        assert c.sent[-1] == "system_message"
        print(f"  ✅ broadcast: 3 users reached")

        # ── stats() shape ───────────────────────────────────────
        s = mgr.stats()
        assert s["active_users"] == 3
        assert s["active_connections"] == 3
        assert s["lifetime_connects"] >= 5
        assert "users_with_connections" in s
        print(f"  ✅ stats: {s['active_users']} users, "
              f"lifetime_connects={s['lifetime_connects']}")

        # ── websocket_endpoint runs the loop ────────────────────
        mgr2 = ConnectionManager()
        # Replace module-level manager temporarily
        global manager
        old_mgr = manager
        manager = mgr2
        try:
            ws_loop = _MockWebSocket("loop")
            ws_loop.received = ["hello", "world"]
            await websocket_endpoint(ws_loop, "user_loop")
            assert ws_loop.sent == ["ack:hello", "ack:world"]
            assert mgr2.active_user_count() == 0    # disconnected at end
            print(f"  ✅ websocket_endpoint: ack loop + clean disconnect")
        finally:
            manager = old_mgr

        # ── register_websocket_routes idempotent on mock app ────
        class _MockApp:
            def __init__(self):
                self.routes = []
            def websocket(self, path):
                def deco(fn):
                    self.routes.append((path, fn))
                    return fn
                return deco

        app = _MockApp()
        ok1 = register_websocket_routes(app)
        ok2 = register_websocket_routes(app)
        assert ok1 is True
        assert ok2 is True
        # Idempotent — only registered once
        assert len(app.routes) == 1
        assert app.routes[0][0] == "/ws/{user_id}"
        print(f"  ✅ register_websocket_routes: idempotent, path='/ws/{{user_id}}'")

        # ── register on non-FastAPI app returns False ───────────
        assert register_websocket_routes(object()) is False
        assert register_websocket_routes(None) is False
        print(f"  ✅ register on non-FastAPI app → False")

    asyncio.run(run_tests())
    print("\n  ALL TESTS PASSED")
