# Cockpit Absorption Patterns

Documents the 6 cockpit pattern variants encountered during the
v10.202–v10.212 absorption sub-campaign (13 cockpits absorbed across
11 batches). Companion to `scripts/absorb_cockpit.py`.

The campaign objective was to fold standalone `*_cockpit.py` pages
(single-purpose UI surfaces for closed engine arcs) into their
primary department's parent page as nested sub-tabs. Each absorption
removed one page from the manifest while preserving all engine
functionality and audit-gate invariants.

---

## The 6 variants

### 1. Hand-paste

**Example:** v10.202 Treasury Arc → 25_treasury.py
**When used:** First absorption of the campaign. No automation yet.
**Mechanics:** Read cockpit body, copy-paste into target, manually
re-indent. ~30 minutes per cockpit.
**Notes:** Worked but error-prone. Subsequent variants automated this.

### 2. Named descriptive

**Example:** v10.203 Strategy Arc → 83_strategy.py
**Cockpit shape:**
```python
tab_form, tab_cascade, tab_health, ... = st.tabs([...])

with tab_form:
    # body at col 4
    ...

with tab_cascade:
    ...
```
**Tab block detection:** regex `^with (tab_\w+):\s*$`, map var name
to index via dict.
**Body indentation transform:** col 4 → col 12 (+8 spaces) when
nested inside `with tabs[N]: if _AVAILABLE: with arc_tabs[M]:`.

### 3. Indexed inline

**Examples:** v10.204 Product, v10.205 Compliance, v10.210 Revenue
Assurance
**Cockpit shape:**
```python
tabs = st.tabs([...])

with tabs[0]:
    # body at col 4
    ...

with tabs[1]:
    ...
```

OR (when wrapped in `if STREAMLIT_AVAILABLE:`):
```python
if STREAMLIT_AVAILABLE:
    tabs = st.tabs([...])

    with tabs[0]:
        # body at col 8 (nested one level)
        ...
```
**Tab block detection:** regex `^with tabs\[(\d+)\]:\s*$` or
`^    with tabs\[(\d+)\]:\s*$` for the nested form.
**Body indentation transform:** col 4 → col 12 (+8) for module-level,
or col 8 → col 12 (+4) for nested-in-if-block.

### 4. Numbered named

**Examples:** v10.206 Legal, v10.212 ML Governance + Integration
**Cockpit shape:**
```python
def render():  # Legal cockpit wraps in render() function
    tab1, tab2, ... tab7 = st.tabs([...])

    with tab1:
        # body at col 8 (inside def + with-block)
        ...
```

OR module-level:
```python
tab_registry, tab_adj, ... = st.tabs([...])

with tab_registry:
    # body at col 4
    ...
```
**Tab block detection:** regex `^    with (tab\d+):\s*$` (for
render()-wrapped form) or `^with (\w+):\s*$` matched against
explicit var-to-idx dict (for module-level form).
**Body indentation transform:** Variable. col 4 → col 12 (+8) for
module-level; col 8 → col 12 (+4) for render()-wrapped.

### 5. Render-funcs-per-tab

**Example:** v10.207 Resource Optimization
**Cockpit shape:**
```python
def render_executive_tab(engines):
    # body at col 4 (function body)
    st.subheader("Executive Dashboard")
    ...

def render_work_mode_tab(engines):
    ...

# Later:
def main():
    tabs = st.tabs([...])
    with tabs[0]:
        render_executive_tab(engines)
    with tabs[1]:
        render_work_mode_tab(engines)
    ...
```
**Cleaner design than inline body** — functions stay as functions in
the absorbed section, defined inside the new outer block scope.
Helper: `extract_render_functions()` captures each function as a
list of lines including the `def` line.
**Body indentation transform:** col 0 → col 8 (+8) for the function
defs themselves (so they live inside `with tabs[N]: if _AVAILABLE:`).
The function bodies (col 4 internally) remain unchanged relative
to their enclosing `def`.

### 6. Indexed multi-line strings

**Examples:** v10.211 Finance + Trade Finance, v10.212 Integration
**Cockpit shape:**
```python
with tabs[6]:
    st.subheader("Arc Summary")
    st.markdown("""
**Bullet 1** — content at column 0 (string content, not code)

**Bullet 2** — also column 0

More paragraphs...
""")  # closing TRIPLE-paren at column 0
```

**The bug variants 1–5 had:** Naive extraction terminated at the
first col-0 non-empty line, treating string content as "outside the
with-block". Body was cut off; closing `"""` was lost; absorbed
output was an unterminated string literal → SyntaxError.

**The fix:** Track triple-quote toggle state during extraction.
Lines BEGINNING inside a multi-line string are always included,
regardless of their indentation.

**Naive re-indentation also broke:** Adding leading spaces to string
content lines changes the rendered markdown (bullet → code-block).

**The fix:** Track triple-quote state during reindentation too.
Lines that begin inside a string are emitted as-is (no prepend);
only lines that begin outside a string get re-indented.

**Helpers:** Both `extract_tab_blocks_indexed()` and `reindent()` are
**string-aware by default** — variants 1–5 work fine because they
have no triple-quoted content; variant 6 also works because the
helpers detect and preserve string content correctly.

---

## Closure gate refactor — two variants

After absorption, the closure-arc-UI gate (which originally checked
the cockpit file's existence + content) must be refactored to be
**manifest-aware behavior-based** instead of location-locked. The
gate searches the canonical department's pages instead of one
specific file.

### Simple variant (8 gates: G149, G151, G159, G148, G153, G155, G157, G140)

Checks:
- All required imports present somewhere in dept text
- All engine constructors present (e.g. `EngineX()`)
- `require_access(` present somewhere
- `audit_log(` present somewhere

### Strict variant (5 gates: G130, G132, G134, G136, G138)

Adds: each engine must also have at least one of its named methods
invoked somewhere (e.g. `compute(`, `forecast(`, `validate_all(`).

This stricter check enforces that engines are **interactively used**,
not just descriptively imported. Original v10.46 design intent.

### Helper

`build_manifest_aware_gate(gate_id, gate_name, department,
expected_imports, expected_constructors, ...)` generates either
variant. The function inspects `expected_constructors` — if any
entry has a methods list, generates strict variant; otherwise
simple. See helper docstring for full API.

---

## Manifest as canonical source

Throughout the campaign, one principle held:

> **Closure gates follow the page, not the original cockpit name.**

The gate's logic is "find the canonical page that hosts these
engines, search its current department". If the page moves between
departments via manifest edit (as in v10.210 with SBU + Revenue
Assurance moving from sales/operations → finance), the gate
follows automatically. No code change needed for editorial
reassignments.

This decoupling is what made the v10.210 combined editorial
reassignment + cockpit absorption possible in one batch — the gate
refactor was the same code regardless of which department the
target page now belonged to.

---

## When to use this helper

Future use cases:
- Page consolidations (merge 2+ pages into one)
- Cockpit-style deprecations (single-purpose page → tab on parent)
- Department reorganization (move pages, refactor gates to follow)

When NOT to use:
- One-off page edits where the patterns don't apply
- New page creation (no existing cockpit to extract from)
- Cross-department engine relocations (the helper assumes engines
  stay within one department's purview)

---

## Numbers from the campaign (for reference)

| Metric | Value |
|---|---|
| Cockpits absorbed | 13 |
| Batches | 11 (some doubled up) |
| Code reduction | -1378 lines cumulative |
| Pages on disk pre-campaign | 124 |
| Pages on disk post-campaign | 95 |
| Manifest entries pre-campaign (v10.197) | 108 |
| Manifest entries post-campaign | 95 |
| Closure gates refactored | 13 (8 simple + 5 strict) |
| Audit baseline | 160/160 PASS throughout (zero regressions) |
| Pattern variants observed | 6 |
