# A2Z Admin Conventions
## How to add new modules, configs, and admin features without scattering

> **Status:** Active convention from v5.12 onwards
> **Owner:** A2Z Platform Engineering
> **Last review:** v5.12

---

## 1. The Architecture

The admin page (`pages/7_admin.py`) has **6 top-level sections**, each with its own sub-tabs:

| # | Section | What goes here |
|---|---------|----------------|
| 0 | 👥 People & Org | Users, permissions, departments, branches, roles, org structure |
| 1 | 📊 Performance | KPI library, BSC settings, performance reviews, target cascade |
| 2 | 🧩 Modules | Module assignment, module configs (via Centre), nav, thresholds |
| 3 | 🔌 Data & Integration | PostgreSQL, ETL, reconciliation, FLEXCUBE cutover |
| 4 | 🩺 System | Health checks, environment, upload formats, background jobs |
| 5 | 🛡️ Security | Audit log, sessions, password policy, access reviews |

**Do not add new top-level sections** unless the concern is genuinely new (not a module config). The 6 sections are stable.

---

## 2. Adding a New Module Config

When a new module needs admin-configurable settings (thresholds, lists, rates, etc.), **never add a new tab to `7_admin.py`**. Instead, register a config spec.

### Step 1 — Add a registration in `pages/_admin_module_specs.py`

```python
register_module_config({
    "module_id":   "my_module",          # Unique slug
    "title":       "My Module",          # Display title
    "icon":        "🎯",                 # Single emoji
    "category":    "operations",         # See CATEGORIES in admin_registry.py
    "config_path": "proposition_config.json",  # JSON file under data/
    "config_key":  "my_module_config",   # Key inside that JSON
    "page_link":   "65_my_module.py",    # Operational page (optional)
    "tabs": [
        {
            "name": "Settings",
            "fields": [
                {"type":"text_area_list", "key":"items", "label":"Items"},
                {"type":"number_input",   "key":"threshold", "label":"Threshold (KES)",
                 "cast":int, "step":1000, "min":0},
            ],
            "save_label":   "💾 Save",
            "audit_action": "MY_MODULE_UPDATED",
        },
    ],
    "hardcoded_caption": "**Hardcoded:** core algorithm, audit trail.",
})
```

### Step 2 — That's it.

The Module Config Centre will pick up your spec automatically. No tab to add, no UI code to write, no save handler to wire up.

---

## 3. Available Field Types

All field types live in `utils/admin_registry.py` (see `FIELD_TYPES` dict):

| Type | Stores | Renders as |
|------|--------|------------|
| `text_input` | string | Single-line text box |
| `text_area` | string | Multi-line text box |
| `text_area_list` | list of strings | Multi-line text, split on newlines |
| `number_input` | int or float | Numeric input |
| `multiselect` | list | Pick multiple from `options` |
| `selectbox` | scalar | Pick one from `options` |
| `checkbox` | bool | Toggle |
| `dict_editor` | dict[str, number] | Grid of label→number inputs |
| `readonly_table` | list of dicts | Read-only DataFrame |
| `bullet_list` | list | Read-only bullet list |
| `rich_caption` | — | Static markdown caption |

If you need a field type that doesn't exist, **add it to the renderer** (`pages/_admin_module_renderer.py`) before using it. Don't work around it.

---

## 4. Where to Add What

| Concern | Where it goes |
|---------|---------------|
| New module's admin config | `pages/_admin_module_specs.py` (registry) |
| New module's operational UI | New numbered page (`pages/N_module_name.py`) |
| Cross-cutting admin feature (e.g. password policy) | New file under `pages/_admin_<thing>.py`, plus a sub-tab in the relevant section of `7_admin.py` |
| New field type for module configs | Extend `pages/_admin_module_renderer.py` |
| New module category | Add to `CATEGORIES` dict in `utils/admin_registry.py` |

---

## 5. Which Section to Use

Cross-cutting admin features go to a section based on **who needs it**, not what the technical category is:

- **People & Org** — anything an HR admin or Org admin manages (users, departments, structure)
- **Performance** — anything a Performance Manager or HR Lead manages (KPIs, scorecards, reviews)
- **Modules** — anything a System Admin manages module-by-module (config, assignment, sprints)
- **Data & Integration** — anything a DBA or Integration Engineer manages (DB, ETL, recon, external systems)
- **System** — anything an Ops Engineer manages (health, performance, jobs)
- **Security** — anything a CISO or Audit team manages (audit, access, sessions)

---

## 6. Anti-Patterns (Do Not Do)

❌ **Don't add a new top-level section** unless a new role of admin user is needed. The 6 sections are stable.

❌ **Don't add a new sub-tab to `7_admin.py` for a single module's config.** Use the registry.

❌ **Don't put module config UI inside the module's own operational page.** Admin and operational concerns belong in different places.

❌ **Don't bypass the renderer** by writing custom Streamlit forms for module configs. If the renderer can't do what you need, extend it (Section 3).

❌ **Don't mix categories within a single registration.** A module is in ONE category. If it spans multiple, register multiple specs (e.g. `treasury_fx` and `treasury_ifrs9`).

---

## 7. Migration Status (v5.12)

These 10 modules have been migrated to the registry pattern:

- 🔄 RMS · 📁 EDMS · 💹 Treasury · 🧾 Statement Analyzer
- 💼 Pipeline & CRM · ⚖️ LMS · 🎯 Propositions · 📊 Risk Analytics
- 🏖️ Leave · 💰 Revenue Assurance

The 20 modules in `data/module_config.json` (Phase 0/1/2/3 + Benchmarking + FLEXCUBE) use the existing **module governance** view (top of Module Config Centre), which is read-mostly. They will migrate to the registry pattern when their admin UIs are next touched.

---

## 8. Testing a New Spec

After adding a registration, restart the app and check:

1. **Module Config Centre → ⚙️ Module configs (registered)** tab — your module appears under its category
2. **Edit a field, click Save** — values persist; audit log shows your `audit_action`
3. **Reload the page** — values you saved are still there
4. **Restart the app** — values still there (no in-memory caching of registry forms)

If any of those fail, the spec is wrong. Common bugs:
- `config_path` doesn't exist → file gets created on first save (usually fine, but check)
- `config_key` typo → reads/writes the wrong sub-dict
- Missing `save_label` → save button doesn't appear (use empty string `""` if you want a read-only tab)
- Wrong `cast` for `number_input` (used `int` but values are floats) → saves crash

---

*Convention version 1.0 (v5.12). Update this doc when patterns change.*
