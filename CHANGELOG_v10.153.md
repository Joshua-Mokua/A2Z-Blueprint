# CHANGELOG v10.153 — Navigation Hotfix (closes the v10.46+ visibility gap)

**Status:** **NAVIGATION HOTFIX — 9 closure cockpits registered in app.py.** This drop replaces the originally-planned v10.153 (Treasury FastAPI router, which moves to v10.154) because of a higher-priority issue surfaced during user testing: every cockpit shipped since the v10.46 protocol amendment was sitting on disk but never visible in Streamlit.

**Audit:** `Score: 149/149 gates = 100.0% — PASS` (gate count 148 → 149 with new G149). Engine self-tests unchanged. v10.153 navigation tests 12/12 pass.

---

## What was wrong (the actual diagnosis)

Your `app.py` uses Streamlit's `st.navigation()` API — the **explicit registration model**, not auto-discovery. Pages in the `pages/` directory are NOT shown in the sidebar unless explicitly listed in one of `app.py`'s nav groups via `_pg("pages/X.py", ...)`.

Across v10.46+ closures, every closure batch shipped a cockpit page (`pages/X_*_cockpit.py`) but no closure batch updated `app.py`'s navigation. The cockpits exist on disk, the audit gates pass, the FastAPI routers work — but the Streamlit sidebar only shows pages that were registered before v10.46. Result: every closure since Risk Arc has been invisible to users, even though the underlying engines + audit + tests all worked.

This was a systemic gap, not a Product-specific or Strategy-specific issue. **Nine cockpit pages were unregistered:**

```
pages/15_strategy_arc_cockpit.py
pages/16_product_arc_cockpit.py
pages/93_risk_arc_cockpit.py
pages/94_credit_governance_cockpit.py
pages/95_revenue_assurance_cockpit.py
pages/96_finance_arc_cockpit.py
pages/97_trade_finance_arc_cockpit.py
pages/98_ml_governance_arc_cockpit.py
pages/99_integration_cockpit.py
```

The diagnosis emerged from your specific user-testing observation: "the same problem is with the strategy one and the ones we have done previously." That pattern flipped the diagnosis — the issue couldn't be Product-specific because Strategy and earlier closures had it too. Searching `cockpit` in `app.py` returned zero matches; the gap became obvious.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `app.py` | +12 lines | NEW `_pg()` registrations across 6 nav groups (`_exec_grp`, `_retail_grp`, `_comm_grp`, `_finance_grp`, `_risk_grp`, `_admin_grp`) plus existing groups already containing close engines (`_credit_grp`, `_tf_grp`) |
| `scripts/audit.py` | +90 lines | NEW G149 `gate_cockpits_registered_in_app` audit gate |
| `tests/test_navigation_v10_153.py` | ~120 | NEW. 12 tests across 4 classes |
| `docs/Master_Prompt_v3.46.md` | ~1100 | Anti-drift sync v3.45 → v3.46 |
| `SCOPE_LEDGER.md` | updated | v10.153 row + status block |
| `CHANGELOG_v10.153.md` | this file | This document |

---

## The cockpit-to-group mapping (what each cockpit registers under)

| Cockpit | Registered in nav group(s) | Display label |
|---|---|---|
| `15_strategy_arc_cockpit.py` | `_exec_grp` | 🎯 Strategy Arc Cockpit |
| `16_product_arc_cockpit.py` | `_exec_grp`, `_retail_grp`, `_comm_grp` | 📦 Product Arc Cockpit |
| `93_risk_arc_cockpit.py` | `_risk_grp` | 🛡️ Risk Arc Cockpit |
| `94_credit_governance_cockpit.py` | `_credit_grp` | 📋 Credit Governance Cockpit |
| `95_revenue_assurance_cockpit.py` | `_finance_grp` | 💰 Revenue Assurance Cockpit |
| `96_finance_arc_cockpit.py` | `_finance_grp` | 💎 Finance Arc Cockpit |
| `97_trade_finance_arc_cockpit.py` | `_tf_grp` | 🚢 Trade Finance Arc Cockpit |
| `98_ml_governance_arc_cockpit.py` | `_admin_grp` | 🤖 ML Governance Cockpit |
| `99_integration_cockpit.py` | `_admin_grp` | 🔗 Integration Cockpit |

Product Arc Cockpit appears in three groups because product strategy spans executive + retail + commercial views — operators landing in any of those navigation contexts can reach it. The deduplication block already in `app.py` (lines ~1220+ via `_clean_sections`) ensures the page only renders once even though it's registered three times — that's the existing belt-and-suspenders pattern your code already uses for shared pages like `1_perform.py`.

You may want to adjust module-IDs (the 4th argument to `_pg()`) based on your RBAC needs. I used: `strategy_arc`, `product_arc`, `risk_arc`, `credit_governance`, `revenue_assurance` (matches existing), `finance_arc`, `trade_finance_arc`, `ml_governance_arc`, `integration_arc`. If a cockpit should inherit permissions from an existing page (e.g., Strategy Arc Cockpit using the same permission set as `1_perform.py`'s `"perform"` module-ID), edit the relevant `_pg()` call.

---

## G149 — the audit gate that prevents recurrence

`gate_cockpits_registered_in_app` in `scripts/audit.py`:

1. Globs `pages/*_cockpit.py` to find every cockpit on disk
2. For each, checks `app.py` contains a `pages/<filename>` reference
3. Passes if all cockpits are registered; fails listing the unregistered ones

This means: any future closure batch that ships a `*_cockpit.py` MUST also update `app.py` or the audit will fail. The lesson is now codified into the audit suite — same pattern you've used throughout the build (every closure adds gates that prevent regression of that closure's invariants).

For the v10.155 Treasury closure, when `pages/26_treasury_arc_cockpit.py` is built, the closure batch will need to register it in `_treasury_grp` or G149 will fail. That's intended — it forces the registration step explicitly into the closure checklist.

---

## Tests — `tests/test_navigation_v10_153.py`

12 tests across 4 classes:

- **TestAppParses** (1) — app.py parses cleanly after edits
- **TestCockpitsRegistered** (3) — each of 9 cockpits referenced; Strategy in _exec_grp; Product in both _retail_grp + _comm_grp
- **TestG149Gate** (4) — function exists / registered in GATES / passes / returns proper shape
- **TestNoRegression** (4) — G147 + G148 still pass / total gate count = 149 / existing pages still referenced (sanity check we didn't accidentally remove anything)

All 12 pass via inline runner.

---

## Apply order

After v10.152 (or after the consolidated bundle):

```
1. app.py                                    → root      (MODIFIED)
2. scripts/audit.py                          → scripts/  (MODIFIED — G149 added)
3. tests/test_navigation_v10_153.py          → tests/
4. docs/Master_Prompt_v3.46.md               → docs/
5. SCOPE_LEDGER.md                           → root
6. CHANGELOG_v10.153.md                      → root
```

`git add -A && git commit -m "v10.153 Navigation Hotfix — register 9 cockpits + G149 ratchet"`. Then `python scripts/audit.py` should print `Score: 149/149 gates = 100.0% — PASS`.

**Critical apply step:** **restart Streamlit** after applying. Streamlit only re-reads `app.py` and the navigation registration on process restart. Browser refresh alone won't show the new sidebar entries.

---

## What you should see after applying + restarting Streamlit

Your sidebar (depending on your department/role + RBAC) will show new cockpit entries within their respective navigation sections:

- **Executive** section: Strategy Arc Cockpit, Product Arc Cockpit
- **Retail Banking** section: Product Arc Cockpit
- **Commercial/Corp** section: Product Arc Cockpit
- **Credit** section: Credit Governance Cockpit
- **Finance** section: Revenue Assurance Cockpit, Finance Arc Cockpit
- **Risk & Compliance** section: Risk Arc Cockpit
- **Trade Finance** section: Trade Finance Arc Cockpit
- **Admin** section: ML Governance Cockpit, Integration Cockpit

Click any cockpit entry. The page should render. If it errors instead, the Streamlit terminal will show a Python traceback — most likely cause is a missing engine import (the cockpit imports companion engines at module load; if the engines aren't all present, the page crashes on click).

---

## Why this took priority over Treasury API (v10.153 → v10.154)

The originally-planned v10.153 was Treasury FastAPI router (`utils/api_treasury.py`). That work is still queued as v10.154. But shipping more closure infrastructure while every existing closure cockpit was invisible would just compound the problem — every new module would close, but you'd still see nothing. Fixing the visibility gap first means: (a) you can verify everything we've done since v10.46 actually works in your hands, (b) the v10.155 Treasury closure will have a clean path because G149 will catch any future cockpit registration omission automatically.

---

## What this drop does NOT change

- Engines: zero engine modifications
- Standards registry: no flips, no edits
- Existing pages: zero changes to existing `pages/*.py` files
- Tests for previous closures: unchanged
- FastAPI routers: unchanged
- Any pre-v10.46 navigation entries in `app.py`: unchanged (sanity-checked by `TestNoRegression.test_existing_pages_still_referenced`)

The only files modified are `app.py` (12 lines added across nav groups) and `scripts/audit.py` (G149 function + 1 line in GATES list).

---

## v10.154 next-up — Treasury FastAPI router

Resuming the Phase 2 Treasury refresh per the v10.152 plan:

1. Verify 20 affected_engines exist in `utils/` (per the v10.152 plan §3.2)
2. Build `utils/api_treasury.py` FastAPI router
3. Per the v10.155 closure plan, the cockpit will go in `pages/26_treasury_arc_cockpit.py` and will need a `_pg()` registration in `_treasury_grp` — which G149 will now enforce automatically

---

## Summary

The reason your Streamlit sidebar didn't show the new closure cockpits is that `app.py` uses explicit `st.navigation()` registration, not auto-discovery. Nine closure cockpits since v10.46 were on disk but unregistered. v10.153 registers all nine in their appropriate nav groups and adds G149 to the audit suite to prevent this gap from happening again. Every future cockpit ships with both engine + cockpit + nav registration as a single closure invariant.

**Quoting the audit script directly:** `Score: 149/149 gates = 100.0% — PASS`. v10.153 tests `12/12 pass`.
