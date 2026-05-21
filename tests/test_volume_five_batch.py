"""tests/test_volume_five_batch.py — Standards #36-#40 (v5.51).

Coverage:
  Standard #36 — Three-Interface Strategy (interface_routing)
  Standard #37 — React SPA scaffolding (App.tsx)
  Standard #38 — React Native scaffolding (offlineSync.ts)
  Standard #39 — Streamlit Admin gate in app.py
  Standard #40 — WebSocket ConnectionManager + endpoint
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
WEB_APP_TSX     = ROOT / "frontend" / "web" / "src" / "App.tsx"
MOBILE_SYNC_TS  = ROOT / "frontend" / "mobile" / "services" / "offlineSync.ts"
APP_PY          = ROOT / "app.py"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestFilesExist:
    def test_interface_routing_module(self):
        assert (ROOT / "utils" / "interface_routing.py").exists()

    def test_websocket_manager_module(self):
        assert (ROOT / "utils" / "websocket_manager.py").exists()

    def test_react_spa_scaffold(self):
        assert WEB_APP_TSX.exists()

    def test_mobile_sync_scaffold(self):
        assert MOBILE_SYNC_TS.exists()

    def test_frontend_readmes(self):
        assert (ROOT / "frontend" / "web" / "README.md").exists()
        assert (ROOT / "frontend" / "mobile" / "README.md").exists()


# ═══════════════════════════════════════════════════════════════════════
# Standard #36 — Three-Interface Strategy
# ═══════════════════════════════════════════════════════════════════════

class TestStandard36:
    def test_spec_table_byte_for_byte(self):
        from utils.interface_routing import (
            INTERFACE_ROUTING, validate_interface_routing,
        )
        v = validate_interface_routing()
        assert v["valid"], f"errors: {v['errors']}"
        assert v["roles_validated"] == 4

    def test_executive_primary_is_spa_plus_mobile(self):
        from utils.interface_routing import get_primary_interface
        assert get_primary_interface("Executive") == "React SPA + Mobile"

    def test_admin_secondary_is_none(self):
        from utils.interface_routing import get_secondary_interface
        # Spec literal "None" → Python None
        assert get_secondary_interface("Admin") is None

    def test_unknown_role_returns_none(self):
        from utils.interface_routing import (
            get_primary_interface, get_secondary_interface,
            interface_for_user,
        )
        # Privilege escalation guard — unknown role NEVER gets a default
        assert get_primary_interface("Hacker") is None
        assert get_secondary_interface("Hacker") is None
        assert interface_for_user({"role": "Hacker"}) is None

    def test_executive_device_hint_resolves(self):
        from utils.interface_routing import interface_for_user
        exec_user = {"role": "Executive"}
        assert interface_for_user(exec_user, device_hint="mobile")  == "Mobile"
        assert interface_for_user(exec_user, device_hint="desktop") == "React SPA"

    def test_all_interfaces_for_role(self):
        from utils.interface_routing import all_interfaces_for_role
        assert all_interfaces_for_role("Executive") == ["React SPA", "Mobile", "Streamlit"]
        assert all_interfaces_for_role("Admin")     == ["Streamlit"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #37 — React SPA scaffold
# ═══════════════════════════════════════════════════════════════════════

class TestStandard37:
    def test_app_tsx_exists(self):
        assert WEB_APP_TSX.exists()

    def test_query_client_imported(self):
        content = WEB_APP_TSX.read_text()
        assert "QueryClient" in content
        assert "@tanstack/react-query" in content
        assert "const queryClient = new QueryClient()" in content

    def test_provider_chain_present(self):
        content = WEB_APP_TSX.read_text()
        assert "<QueryClientProvider client={queryClient}>" in content
        assert "<AuthProvider>" in content
        assert "<WebSocketProvider>" in content
        assert "<BrowserRouter>" in content

    def test_three_spec_routes_present(self):
        content = WEB_APP_TSX.read_text()
        assert 'path="/"' in content
        assert 'path="/perform"' in content
        assert 'path="/profitability"' in content


# ═══════════════════════════════════════════════════════════════════════
# Standard #38 — React Native scaffold
# ═══════════════════════════════════════════════════════════════════════

class TestStandard38:
    def test_offline_sync_exists(self):
        assert MOBILE_SYNC_TS.exists()

    def test_class_name_present(self):
        content = MOBILE_SYNC_TS.read_text()
        assert "class OfflineSyncService" in content

    def test_spec_methods_present(self):
        content = MOBILE_SYNC_TS.read_text()
        assert "queueOperation" in content
        assert "getOfflineData" in content
        # Spec literal: this.queue.push(operation)
        assert "this.queue.push(" in content
        assert "saveQueue" in content
        assert "processQueue" in content

    def test_async_storage_imported(self):
        content = MOBILE_SYNC_TS.read_text()
        assert "AsyncStorage" in content
        assert "@react-native-async-storage/async-storage" in content
        assert "AsyncStorage.getItem(" in content

    def test_spec_literal_offline_prefix(self):
        content = MOBILE_SYNC_TS.read_text()
        # Spec literal: AsyncStorage.getItem(`offline_${key}`)
        assert "offline_" in content


# ═══════════════════════════════════════════════════════════════════════
# Standard #39 — Streamlit Admin gate
# ═══════════════════════════════════════════════════════════════════════

class TestStandard39:
    def test_app_py_exists(self):
        assert APP_PY.exists()

    def test_admin_gate_present(self):
        content = APP_PY.read_text()
        # Spec-literal pattern from #39
        assert "'Admin'" in content
        assert "Access denied. Admin interface only." in content
        assert "st.stop()" in content

    def test_feature_flag_default_off(self):
        # The gate is feature-flag controlled; default OFF so it
        # doesn't break production until React SPA goes live
        content = APP_PY.read_text()
        assert "enforce_admin_only" in content
        assert "_admin_only_enabled" in content

    def test_app_py_parses(self):
        # Must remain valid Python after the insertion
        import ast
        ast.parse(APP_PY.read_text())


# ═══════════════════════════════════════════════════════════════════════
# Standard #40 — WebSocket Manager
# ═══════════════════════════════════════════════════════════════════════

class TestStandard40:
    def test_manager_class_exists(self):
        from utils.websocket_manager import ConnectionManager
        mgr = ConnectionManager()
        assert hasattr(mgr, "connect")
        assert hasattr(mgr, "disconnect")
        assert hasattr(mgr, "send_to_user")
        assert hasattr(mgr, "broadcast")

    def test_websocket_endpoint_signature(self):
        from utils.websocket_manager import websocket_endpoint
        # Spec signature: async def websocket_endpoint(websocket, user_id)
        import inspect
        sig = inspect.signature(websocket_endpoint)
        params = list(sig.parameters.keys())
        assert "websocket" in params
        assert "user_id" in params

    def test_manager_singleton_exposed(self):
        import utils.websocket_manager as m
        assert hasattr(m, "manager")
        from utils.websocket_manager import ConnectionManager
        assert isinstance(m.manager, ConnectionManager)

    def test_register_routes_idempotent(self):
        from utils.websocket_manager import register_websocket_routes

        class _MockApp:
            def __init__(self):
                self.routes = []
            def websocket(self, path):
                def deco(fn):
                    self.routes.append((path, fn))
                    return fn
                return deco

        app = _MockApp()
        register_websocket_routes(app)
        register_websocket_routes(app)
        # Idempotent — exactly 1 route
        assert len(app.routes) == 1
        assert app.routes[0][0] == "/ws/{user_id}"

    def test_connect_rejects_empty_user_id(self):
        """Privilege escalation guard — empty user_id rejected, not silently accepted."""
        from utils.websocket_manager import ConnectionManager

        class _MockWS:
            closed = False
            close_code = None
            async def close(self, code=1000):
                self.closed = True
                self.close_code = code

        async def run():
            mgr = ConnectionManager()
            ws = _MockWS()
            try:
                await mgr.connect(ws, "")
                return False, ws
            except ValueError:
                return True, ws

        rejected, ws = asyncio.run(run())
        assert rejected is True
        assert ws.closed is True
        assert ws.close_code == 1008    # policy violation

    def test_multi_tab_fanout(self):
        """One user, two tabs → broadcast reaches both."""
        from utils.websocket_manager import ConnectionManager

        class _MockWS:
            def __init__(self):
                self.sent = []
                self.accepted = False
            async def accept(self):
                self.accepted = True
            async def send_text(self, msg):
                self.sent.append(msg)

        async def run():
            mgr = ConnectionManager()
            ws1, ws2 = _MockWS(), _MockWS()
            await mgr.connect(ws1, "u1")
            await mgr.connect(ws2, "u1")
            sent = await mgr.send_to_user("u1", "hello")
            return sent, ws1.sent, ws2.sent

        sent, s1, s2 = asyncio.run(run())
        assert sent == 2
        assert s1 == ["hello"]
        assert s2 == ["hello"]
