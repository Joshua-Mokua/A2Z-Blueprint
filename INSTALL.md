# v10.496 — Installation Guide

Extract this zip on top of your A2Z root:
`C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`

## What's in this zip

```
frontend/web/src/
  lib/
    cn.ts                ← NEW — Tailwind class-joiner utility
    tokens.ts            ← NEW — Canonical design tokens
  types/
    components.ts        ← NEW — Shared component prop types
  components/            ← ALL NEW (8 primitive files)
    Button.tsx
    Card.tsx
    Input.tsx
    Stat.tsx
    Badge.tsx
    Toast.tsx
    Skeleton.tsx
    Table.tsx
  pages/
    Showcase.tsx         ← NEW — Kitchen-sink at /components
    Dashboard.tsx        ← REPLACES — refactored to use primitives
  App.tsx                ← REPLACES — adds /components route + ToastProvider

scripts/audit.py         ← REPLACES — G382 added (413/413 gates)
tests/integration/
  test_v10496_design_system.py   ← NEW (22 tests)
docs/Master_Prompt_v5.40.md      ← NEW
CHANGELOG_v10.496.md             ← NEW
INSTALL.md                       ← (this file)
```

**Good news:** v10.496 has **zero backend changes**. Pure frontend.
No `utils/config.py` to edit. No `utils/api.py` to patch. No new
Python deps. No new npm deps.

## Three-step install (10 minutes)

### Step 1 — Extract on top of your A2Z root

In Windows Explorer:
1. Find the downloaded `a2z_v10496_patch.zip`
2. Right-click → **Extract All...**
3. Choose destination: `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`
4. Confirm overwriting when prompted:
   - `frontend/web/src/App.tsx` — yes, overwrite (we add the new route)
   - `frontend/web/src/pages/Dashboard.tsx` — yes, overwrite (refactor)
   - `scripts/audit.py` — yes, overwrite (G382 added)

### Step 2 — Reload the React app

You may already have the React dev server (Vite) running from v10.495.

**If `pnpm dev` is still running in a Command Prompt:**
Vite will hot-reload automatically. Just refresh your browser tab.

**If it's not running:**
Open a Command Prompt and run:
```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\frontend\web
pnpm dev
```

(No need to start the Python backend; v10.496 doesn't add new endpoints.)

### Step 3 — Take the tour

Open two URLs:

**1. Dashboard — refactored, same look:**
```
http://localhost:5173/
```

The MD Cockpit shell should still render identically to v10.495 — but
under the hood it now uses `<Stat>`, `<Card>`, `<Card.Header>`,
`<Card.Body>`, `<Badge>` primitives instead of inline `style={{}}`.

**2. Showcase — the kitchen sink:**
```
http://localhost:5173/components
```

Every primitive in every state. Try clicking the four "Fire toast"
buttons. Try the "Toggle loading" button on the table. Type in the
inputs. Watch what happens.

## Verify it worked (3 commands)

In a Command Prompt with the venv active (`.venv\Scripts\activate`):

### Audit gate

```
python scripts\audit.py
```

Should show **413/413 gates passing** including G381 and G382.

### Integration tests

```
python -m pytest tests\integration\test_v10496_design_system.py -v
```

Should show **22 passed**.

### Optional: TypeScript compile check

In `frontend\web`:

```
pnpm exec tsc --noEmit
```

Should print nothing (no output = no errors).

## If anything is off

- **Blank page or red error overlay at `/components`** → screenshot
  the browser console (`F12` → Console tab) and paste it. Most
  likely cause: typo in an import path.
- **`pnpm dev` errors** → paste the error.
- **`python scripts\audit.py` errors** → paste it. Most likely a
  v10.495 file wasn't extracted properly.

## What's next

After verification, tell me **"v10.496 live"** and we proceed to
**v10.497 — JWT auth + login page**.

That batch is bigger emotionally (your first real auth flow) but
mechanically similar: backend wire-up (login endpoint already exists
at `/api/auth/login`), one new React provider, one new page, one
protected-route wrapper. ~12 files. Same zip pattern.
