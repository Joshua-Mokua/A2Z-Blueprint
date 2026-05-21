# CHANGELOG v10.153.1 — Product Cockpit Hotfix

**Status:** Tiny hotfix on top of v10.153. Two signature bugs in `pages/16_product_arc_cockpit.py` that crashed the page on click. No engine, registry, or audit changes.

**Audit:** `Score: 149/149 gates = 100.0% — PASS` (unchanged).

---

## What was wrong

User applied v10.153, the cockpit became visible in sidebar (nav hotfix worked), they clicked it and got:

```
TypeError: require_access() got an unexpected keyword argument 'roles'
File "pages/16_product_arc_cockpit.py", line 85, in <module>
    require_access("Product Arc Cockpit", roles=("admin", "product"))
```

I'd invented a `require_access(name, roles=...)` signature that doesn't exist. Real signature is `require_access(module: str, silent: bool = False)` — a single module-id string.

While diagnosing, I also caught a second bug in the same file: my `audit_log()` call used `actor=` and `payload=` kwargs, but the real signature is `audit_log(action, username, detail, module, before, after)`. That call was wrapped in try/except so it didn't crash — it just silently failed every time, meaning audit logging from the cockpit was never working.

Cross-checked the other 8 cockpits already in the repo to make sure they don't have the same pattern. They don't:

| Cockpit | require_access call |
|---|---|
| 15_strategy_arc_cockpit.py | `require_access("strategic_initiatives")` |
| 93_risk_arc_cockpit.py | `require_access("perform")` |
| 94..98 (Credit/Finance/Trade/ML cockpits) | `require_access("perform")` |
| 99_integration_cockpit.py | `require_access("integration_cockpit", silent=True)` |
| **16_product_arc_cockpit.py (this drop)** | **`require_access("products")` (FIXED)** |

The bug was Product-cockpit-specific because only that cockpit was new code I wrote.

---

## What this drop ships

| File | Change |
|---|---|
| `pages/16_product_arc_cockpit.py` | 3 small edits (require_access call, audit_log call, fallback stubs) |
| `CHANGELOG_v10.153.1.md` | this file |

---

## The 3 specific edits in `pages/16_product_arc_cockpit.py`

### 1. Line ~85: `require_access` call

```diff
-    require_access("Product Arc Cockpit", roles=("admin", "product"))
+    require_access("products")
```

`"products"` is an existing module-id in `MODULE_ACCESS` (in `utils/core.py`) — the cockpit inherits the same RBAC as the basic Products page (`pages/5_products.py`): Admin, Managing Director, Director Commercial Banking, Head Of Corporate, Head Of SME, Chief Finance Officer, Director Retail Banking. Same convention Strategy cockpit uses with `require_access("strategic_initiatives")`.

If you want a SEPARATE RBAC for the cockpit (different role set than the operational Products page), add a new `"product_arc"` entry to `MODULE_ACCESS` in `utils/core.py` and change the call to `require_access("product_arc")`. Out of scope for this hotfix.

### 2. Line ~450: `audit_log` call

```diff
-    audit_log(
-        action="product_arc_cockpit.view",
-        actor=(st.session_state.get("user", {}).get("username")
-                if hasattr(st, "session_state") else "anonymous"),
-        payload={"page": "16_product_arc_cockpit",
-                   "viewed_at": datetime.now(
-                       timezone.utc).isoformat()})
+    _user = st.session_state.get("user_data", {}) if hasattr(st, "session_state") else {}
+    audit_log(
+        action="product_arc_cockpit.view",
+        username=_user.get("username", "anonymous"),
+        detail=f"viewed_at={datetime.now(timezone.utc).isoformat()}",
+        module="products")
```

Matches real signature: `audit_log(action, username, detail, module, before, after)`. Also reads from `user_data` (the real session key your codebase uses) instead of `user`.

### 3. Lines ~67-69: fallback stub signatures

The `try/except ImportError` block at the top of the file had stubs with `*args, **kwargs` signatures that would silently mask future signature mismatches. Updated the stubs to declare the real signatures:

```diff
-    def require_access(*args, **kwargs):
+    def require_access(module: str, silent: bool = False):
         return True
-    def audit_log(*args, **kwargs):
+    def audit_log(action: str, username: str, detail: str = "",
+                    module: str = "", before: str = "", after: str = ""):
         pass
```

This means if someone later writes `require_access(name, roles=...)` again by accident, even the fallback path will fail loudly instead of silently returning `True`. Defensive, not load-bearing.

---

## Apply

```
1. pages/16_product_arc_cockpit.py    → pages/   (replace)
2. CHANGELOG_v10.153.1.md             → root
```

Restart Streamlit. Click "Product Arc Cockpit" in the sidebar. The 7 thematic tabs should render: Dashboard, Profitability & Ranking, Lifecycle, Customers & CVPs, Competitive & Pricing, Recommendations, Bundling.

If anything else errors on click, send the traceback — different bug, different fix.

---

## Why no audit gate change

The audit suite verifies engine integrity, gate counts, registry consistency, syntax — but not function-signature compatibility between callers and callees. Adding such verification (e.g., parse all `require_access(...)` calls in `pages/*.py`, check signatures match) would be a worthwhile broader project but well beyond a hotfix scope. Out-of-scope; G149 already enforces nav registration which is the more impactful structural check.

The honest takeaway: my cockpit code went through audit + tests + my own self-tests in the sandbox without catching this because the sandbox doesn't have Streamlit installed (so the cockpit's import fallback path masked any signature checks). The bug only surfaced when you actually loaded the page in real Streamlit. **User testing was the discipline that surfaced it; G149 only covered the nav-registration angle, not the runtime call angle.** Worth flagging because the same gap could recur in the v10.155 Treasury cockpit if I'm not careful — I'll be more careful with require_access + audit_log signatures going forward.
