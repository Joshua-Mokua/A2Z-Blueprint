# Apply guide — A2Z v10.142 → v10.152 consolidated bundle

This bundle consolidates 11 drops (v10.142 through v10.152) into a single archive. Apply once and you're at the same end-state as if you'd applied each individual zip in sequence.

**End-state after apply:**
- Phase 1E Product Module CLOSED (10/10 standards active: ENH-131..140)
- Phase 2 Treasury Refresh Plan opened (planning docs, no code changes)
- Audit: 148/148 gates PASS (gate count was 146; +G147 +G148 from this bundle)
- Total active standards: 147/264 (55.7%)
- 9th module closure in platform history

---

## What this bundle contains

### NEW files (12 in `utils/`, 1 in `pages/`, 6 in `data/`, 10 in `tests/`, 14 docs)

| Path | Source drop |
|---|---|
| `utils/product_pnl_intelligence.py` | v10.142 ENH-131 |
| `utils/product_lifecycle.py` | v10.143 ENH-132 |
| `utils/customer_needs_analyzer.py` | v10.144 ENH-133 |
| `utils/product_competitive_intel.py` | v10.145 ENH-134 |
| `utils/product_cvp_builder.py` | v10.146 ENH-135 |
| `utils/product_ranking.py` | v10.147 ENH-136 |
| `utils/dynamic_pricing.py` | v10.148 ENH-137 |
| `utils/product_recommendation.py` | v10.149 ENH-138 |
| `utils/product_bundling.py` | v10.150 ENH-139 |
| `utils/product_analytics_dashboard.py` | v10.151 ENH-140 |
| `utils/api_product.py` | v10.151 closure batch (FastAPI router) |
| `pages/16_product_arc_cockpit.py` | v10.151 closure batch |
| `data/cost_allocation_config.json` | v10.142 |
| `data/product_lifecycle.json` | v10.143 |
| `data/product_stagegate_config.json` | v10.143 |
| `data/customer_needs_registry.json` | v10.144 |
| `data/product_competitor_mapping.json` | v10.145 |
| `data/pricing_constraints_config.json` | v10.148 |
| `tests/test_product_v10_142.py` ... `test_product_v10_151.py` | one per drop |

### MODIFIED files (full replacement — overwrites whatever's there)

| Path | What changed across v10.142-v10.151 |
|---|---|
| `utils/standards_registry.py` | ENH-131..140 status flipped `planned` → `active`; `affected_engines` populated; `implementation_batch` set |
| `pages/7_admin.py` | Tier 4B "Product Intelligence" section extended with 10 new engine entries |
| `scripts/audit.py` | Added `gate_product_module_closed` (G147) + `gate_product_arc_ui_integrated` (G148) functions; both registered in GATES tuple |

### Documentation (root + `docs/`)

- `TREASURY_REFRESH_PLAN.md` — Phase 2 opening plan (v10.152, refresh trajectory for Treasury arc)
- `SCOPE_LEDGER.md` — full ledger including v10.142-v10.152 status blocks
- `docs/Master_Prompt_v3.45.md` — latest anti-drift sync
- `CHANGELOG_v10.142.md` ... `CHANGELOG_v10.152.md` — per-drop changelogs (11 files)

---

## What this bundle does NOT contain

Files I DID NOT create or modify and that should NOT be touched on apply:

- Your existing `pages/25_treasury.py`, `pages/81_alm.py` and every other page outside `pages/16_product_arc_cockpit.py` and `pages/7_admin.py`
- Your existing `utils/product_profitability.py` (Standard #47, pre-existing) — separate from `utils/product_pnl_intelligence.py` (my new file for ENH-131)
- Your existing `utils/product_raroc.py` (Standard #90, pre-existing)
- Any other engines, pages, or scripts in your repo

The bundle only contains my work plus the three modified files. **Anything in your repo that isn't in this bundle is untouched.**

---

## Apply steps

```bash
# 1. From your A2Z-Blueprint repo root, save current state first
cd /path/to/your/A2Z-Blueprint
git status                          # Make sure you're on a clean working tree
git checkout -b apply/v10.142_to_v10.152

# 2. Extract the bundle into a staging directory
unzip a2z_v10.142_to_v10.152_consolidated.zip -d /tmp/a2z_bundle

# 3. Copy files into your repo
#    -a preserves attributes; the trailing slash on source matters
cp -av /tmp/a2z_bundle/utils/.        utils/
cp -av /tmp/a2z_bundle/pages/.        pages/
cp -av /tmp/a2z_bundle/scripts/.      scripts/
cp -av /tmp/a2z_bundle/data/.         data/
cp -av /tmp/a2z_bundle/tests/.        tests/
cp -av /tmp/a2z_bundle/docs/.         docs/
cp -v /tmp/a2z_bundle/TREASURY_REFRESH_PLAN.md  ./
cp -v /tmp/a2z_bundle/SCOPE_LEDGER.md           ./
cp -v /tmp/a2z_bundle/CHANGELOG_v10.*.md        ./

# 4. Verify the audit passes — this is the canonical check
python scripts/audit.py | tail -3
# Expected: Score: 148/148 gates = 100.0% — PASS

# 5. Mount the FastAPI router (one-line addition to your main API file)
#    Add the following to wherever you assemble the parent FastAPI app
#    (typically utils/api.py or a similar module):
#
#       from utils.api_product import router as product_router
#       app.include_router(product_router)
#
#    If you don't run the FastAPI side currently, skip this — Streamlit
#    works without it.

# 6. Restart Streamlit
#    Stop the running streamlit server (Ctrl+C in its terminal),
#    then start it again:
streamlit run [your_main_streamlit_file].py

# 7. Commit when satisfied
git add -A
git commit -m "Apply v10.142-v10.152 — Phase 1E Product Module closure + Phase 2 Treasury plan"
```

---

## Verification — what you should see after applying

### From the audit (canonical)

```
$ python scripts/audit.py | tail -3
------------------------------------------------------------------------
  Score: 148/148 gates = 100.0% — PASS
========================================================================
```

If you get anything other than 148/148 PASS, something didn't apply correctly. Look at the failed gate's detail line — it'll tell you which file is missing or wrong.

### From Streamlit (visual)

After restart, your sidebar should show a new entry: **"Product Arc Cockpit"** (alongside your existing 16_commission "Commission" entry — both share the `16_` prefix per the same convention you have for `15_` pages).

Click it. You should see 7 thematic tabs:

1. 📊 Dashboard
2. 💰 Profitability & Ranking
3. 🔄 Lifecycle
4. 🎯 Customers & CVPs
5. 🏆 Competitive & Pricing
6. 🎁 Recommendations
7. 🔗 Bundling

The Dashboard tab top KPIs should show: 16 products, ~45% portfolio margin, 10 loss-making products, 56% competitive leadership rate, 1 actionable pricing recommendation.

### From admin (Tier 4B)

Navigate to Tier 4B "Product Intelligence" in your admin page (`pages/7_admin.py`). You should see all 10 engines listed there: product_pnl_intelligence, product_lifecycle, customer_needs_analyzer, product_competitive_intel, product_cvp_builder, product_ranking, dynamic_pricing, product_recommendation, product_bundling, product_analytics_dashboard.

---

## Troubleshooting

### "Score: 147/148 gates" or similar

Compare which gate failed against `scripts/audit.py` output. Most common: a copied file landed in the wrong place. Re-verify the `cp -av /tmp/a2z_bundle/utils/. utils/` paths — the trailing `.` after the source directory and trailing `/` after the destination matter.

### "ModuleNotFoundError: No module named 'utils.product_X'"

The cockpit imports all 10 engines at module load. If any engine file is missing, the whole page fails. Check that `utils/` contains all 12 of: product_pnl_intelligence.py, product_lifecycle.py, customer_needs_analyzer.py, product_competitive_intel.py, product_cvp_builder.py, product_ranking.py, dynamic_pricing.py, product_recommendation.py, product_bundling.py, product_analytics_dashboard.py, api_product.py, **and your existing standards_registry.py was overwritten**.

### "Streamlit runs but the new page doesn't appear in sidebar"

Restart streamlit (full Ctrl+C + relaunch, not just a refresh). Streamlit only scans the `pages/` directory at startup.

### "New page appears but throws on click"

Read the streamlit terminal output — there'll be a Python traceback. The traceback will name the exact file and line. 99% of the time it's a missing engine file from step 3.

### "git status shows files I didn't expect to be modified"

`git diff` them. The expected modifications are: `utils/standards_registry.py` (10 status flips), `pages/7_admin.py` (Tier 4B section extended), `scripts/audit.py` (G147 + G148 added at end). If anything else is modified, tell me — that would indicate a mis-application.

---

## What's after applying

Once you're at 148/148 PASS and the cockpit renders, we're aligned and v10.153 (Treasury FastAPI router) can resume. Per the v10.152 plan, v10.153's first action is verifying the 8 cross-cutting engines exist, then building `utils/api_treasury.py`.

If verification surfaces issues, send me whatever Streamlit terminal output or audit failure line you see — I can troubleshoot from there.
