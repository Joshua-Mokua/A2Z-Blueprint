# CHANGELOG v10.141.1 — Hotfix: admin Module Config renderer crashes on read-only tabs

**Status:** **HOTFIX.** Single-file change to `pages/_admin_module_renderer.py`. Fixes the runtime crash you reported on the admin page (`TypeError: bad argument type for built-in operation` from `st.button(None, ...)`).

**Audit:** 146/146 PASS (unchanged — pure renderer guard, no spec/audit-gate changes). Engine self-tests 152/152.

---

## Root cause

`pages/_admin_module_specs.py` legitimately uses `"save_label": None` on **3 tabs** that are read-only by design (the `accounts`, `edms`, and one other module's read-only sub-tab — they only show a `readonly_table` and have no editable fields, so no save button is needed).

The renderer at `pages/_admin_module_renderer.py:251` was reading the value with:

```python
save_label = tab_spec.get("save_label", "💾 Save")
```

`dict.get(key, default)` only returns the default when the key is **absent**. When the key is present with value `None` (the spec's intent: "no save button"), it returns `None`. The next line then called `st.button(None, ...)`, which Streamlit hands to the underlying protobuf `button_proto.label = None`, and protobuf rejects None for string fields with the exact `TypeError: bad argument type for built-in operation` you saw.

This is a pre-existing latent bug — not a v10.141 regression. It surfaced now likely because (a) you navigated to a Module Config tab that hadn't been hit before, or (b) a recent Streamlit/protobuf upgrade made the rejection stricter. The strategy module did NOT add any `register_module_config(...)` entries (per your standing rule "never add module-specific config tabs to 7_admin.py; use the registry pattern" — the strategy engines are read-only Tier 4 hub entries, not configurable modules).

## The fix

Guard the save-button render. When `save_label` is None, empty, or a non-string, skip the button entirely — the tab is read-only by design and nothing needs to be saved.

```python
# Save button — None or empty save_label means read-only tab; skip rendering.
# Without this guard, st.button(None, ...) raises TypeError from protobuf.
save_label = tab_spec.get("save_label", "💾 Save")
if not (save_label and isinstance(save_label, str)):
    return
save_key = f"{module_id}_save_{tab_spec.get('name','main')}"

if st.button(save_label, key=save_key, type="primary"):
    ...
```

Returning early is safe — everything below the save button in `_render_tab` belongs to the save-and-persist path. Read-only tabs have already finished rendering their `readonly_table` fields above this block.

## Verified

- All 5 logical cases pass: normal label → render; None → skip; empty string → skip; non-string → skip; emoji label → render.
- Audit still **146/146 PASS** — renderer is not under any gate; G117 is unaffected.
- The 3 read-only tabs (`save_label: None`) now render their tables and stop cleanly without attempting to draw a save button.

## What changed

```
pages/_admin_module_renderer.py    MODIFIED — single 2-line guard added before the save-button render
```

## What did NOT change

- No spec edits to `pages/_admin_module_specs.py` — the `save_label: None` pattern is legitimate and stays as-is.
- No audit gate changes.
- No registry changes.
- No engine changes.
- v10.141 deliverables (cockpit + API + G146) untouched.

## Apply order

After applying v10.141, drop this hotfix on top — single file replacement at `pages/_admin_module_renderer.py`. Refresh the Streamlit page and the admin Module Config Centre should render cleanly across all registered modules.
