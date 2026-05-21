# v10.495 — utils/api.py patch

Your `utils/api.py` is large (~75 KB, hundreds of endpoints). Rather
than ship a full replacement (risky — your file has 28+ batches of
cumulative wiring), we make **one tiny 2-line addition**.

## The change

In `utils/api.py`, find this existing block (around line 137-141):

```python
try:
    from utils.api_capacity_feedback import router as _capacity_router
    app.include_router(_capacity_router)
    logger.info("A2Z API — capacity router mounted at /api/cascade/capacity-feedback")
except Exception as _exc:  # noqa: BLE001
    logger.warning(f"Capacity router not loaded: {_exc}")
```

**Immediately after that block** (before the comment block about
"Helper: emit an audit_log entry..."), paste:

```python


# v10.495 — Branding API for React SPA enablement
# Public endpoint (no JWT) exposing tenant identity + brand colors
# + IP notice. Consumed by frontend/web/ React app's
# BrandingProvider. See utils/api_branding.py.
try:
    from utils.api_branding import router as _branding_router
    app.include_router(_branding_router)
    logger.info("A2Z API — branding router mounted at /api/branding")
except Exception as _exc:  # noqa: BLE001
    logger.warning(f"Branding router not loaded: {_exc}")
```

## How to do it in VS Code (60 seconds)

1. Open `utils/api.py`
2. Press `Ctrl+F`, search for: `capacity router mounted`
3. You'll land on the line `logger.info("A2Z API — capacity router mounted...`
4. Scroll down one line to the closing `logger.warning(f"Capacity router not loaded: {_exc}")`
5. Place cursor at the end of that line, press Enter twice
6. Paste the block above
7. Save with `Ctrl+S`

## Verify it worked

```
cd C:\Users\Joshua\Desktop\A2Z Blue Print\a2z
python -c "import utils.api; print('OK')"
```

Should print `OK` with no errors.

If you see `ImportError: cannot import name 'brand_primary_hex' from
'utils.config'`, you skipped the config.py step. Go back and append
`utils/config_v10495_append.py` contents to `utils/config.py`.

## Why we don't ship a full replacement

Your `utils/api.py` has 28+ batches of cumulative wiring (cascade,
capacity, strategy, cockpit, CRUD modules ×16, HR engines, vitals,
BSC audit, etc.). Replacing it would risk losing one of those
silently. Two-line additive edit is safer.

You can delete this `utils/api_patch_instructions.md` file once the
edit is done.
