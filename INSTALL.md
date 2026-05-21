# v10.495 — Installation Guide

Extract this zip on top of your A2Z root:
`C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`

The zip contains:
```
utils/
  config_v10495_append.py      ← block to APPEND to existing config.py
  api_branding.py              ← new file (no existing version)
  api_patch_instructions.md    ← 2-line edit to existing api.py
frontend/web/
  index.html                   ← new
  vite.config.ts               ← new
  tsconfig.json                ← new
  tsconfig.node.json           ← new
  tailwind.config.js           ← new
  postcss.config.js            ← new
  src/
    App.tsx                    ← REPLACES the existing 2358-byte App.tsx
                                  (contract literals preserved + BrandingProvider added)
    main.tsx                   ← new
    index.css                  ← new
    types/branding.ts          ← new
    lib/api.ts                 ← new
    hooks/useBranding.ts       ← new
    providers/
      BrandingProvider.tsx     ← new
      AuthProvider.tsx         ← new (placeholder satisfying contract)
      WebSocketProvider.tsx    ← new (placeholder satisfying contract)
    pages/
      Dashboard.tsx            ← new
      Perform.tsx              ← new
      Profitability.tsx        ← new
scripts/audit.py               ← REPLACES existing — G381 added
docs/Master_Prompt_v5.39.md    ← new version doc
tests/integration/
  test_v10495_branding_api.py  ← new
CHANGELOG_v10.495.md           ← new
```

## Step-by-step installation (15 minutes)

### Step 1 — Extract on top of A2Z root

In Windows Explorer:
1. Find the downloaded zip
2. Right-click → **Extract All...**
3. Choose destination: `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`
4. Confirm overwriting existing files (App.tsx, scripts/audit.py)

### Step 2 — Append the config helpers

The `utils/config_v10495_append.py` file is **not** a replacement; it's
a snippet to add to your existing `utils/config.py`.

1. Open `utils/config.py` in VS Code
2. Press `Ctrl+End` to jump to the bottom of the file
3. Open `utils/config_v10495_append.py` in another tab
4. Copy everything from the line `# ──────...` (line 21) to the end of file
5. Paste at the bottom of `utils/config.py`
6. Save (`Ctrl+S`)
7. Delete `utils/config_v10495_append.py` (no longer needed)

Verify:
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
python -c "from utils.config import brand_primary_hex, ip_notice; print(brand_primary_hex()); print(ip_notice()[:50])"
```

Expected output:
```
#1797ce
Confidential · Authorised users only · All session
```

### Step 3 — Edit utils/api.py (2 lines)

Open `utils/api_patch_instructions.md` and follow it.

Quick version: in `utils/api.py`, find the existing block:
```python
try:
    from utils.api_capacity_feedback import router as _capacity_router
    app.include_router(_capacity_router)
    ...
except Exception as _exc:
    logger.warning(f"Capacity router not loaded: {_exc}")
```

Add right after it:
```python


# v10.495 — Branding API for React SPA enablement
try:
    from utils.api_branding import router as _branding_router
    app.include_router(_branding_router)
    logger.info("A2Z API — branding router mounted at /api/branding")
except Exception as _exc:  # noqa: BLE001
    logger.warning(f"Branding router not loaded: {_exc}")
```

Save. Delete `utils/api_patch_instructions.md` (no longer needed).

### Step 4 — Run two terminals

**Terminal 1 (FastAPI backend):**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
python -m utils.api
```

You should see `Uvicorn running on http://0.0.0.0:8502` and somewhere
in the log: `A2Z API — branding router mounted at /api/branding`.

Test the new endpoint:
```
curl http://localhost:8502/api/branding
```

You should see JSON with bank_name=Ecobank Kenya, app_name=A2Z Blueprint,
brand.primary=#1797ce, etc.

**Terminal 2 (React frontend):**
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\frontend\web
pnpm dev
```

You should see:
```
  VITE v5.x.x  ready in ~800 ms
  ➜  Local:   http://localhost:5173/
```

### Step 5 — Open browser

Go to `http://localhost:5173/`

You should see:
- **Deep navy header** with "ECOBANK KENYA" uppercase
- Title: "A2Z Blueprint MIS 360 — MD Command Centre"
- Right side: "Central Bank of Kenya" / "Oracle FLEXCUBE v12"
- **Three KPI cards** with cyan-blue (#1797ce) top borders
- **Status panel** explaining v10.495
- **IP notice footer** with the verbatim text from `_login.py`

### Step 6 — Run the audit gate

```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
python scripts/audit.py
```

Should show **412/412 gates passing** including new G381.

### Step 7 — Run the verifier

```
python scripts/verify_local_state.py
```

Should still pass (verifier doesn't check React files but does check
that audit.py contains G381).

## If something doesn't work

- **Browser shows "Branding API unavailable, using fallback" in console**
  → FastAPI isn't running. Start Terminal 1. The fallback colors still
  show (Ecobank defaults baked into BrandingProvider).
- **Blank white page** → check browser console (F12). Most likely a
  TypeScript error. Paste the error and we'll fix.
- **`pnpm dev` errors with module not found** → run `pnpm install`
  again in `frontend/web/` to be safe.
- **`python -m utils.api` errors with ImportError for brand_primary_hex**
  → you forgot Step 2 (append config helpers).

## What's next

After this works, tell me "v10.495 live" and we proceed to v10.496:
**Design System + shadcn/ui components**. Real component library,
Button/Card/Input/Stat/Badge primitives in Ecobank brand, browseable
on a kitchen-sink page.
