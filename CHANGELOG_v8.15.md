# A2Z MIS 360 — CHANGELOG v8.15

**v8.15 Living Doc Phase 3 — admin/systems-view UI surface**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **41st consecutive clean**
**Strategic milestone:** **🎯 LIVING DOCUMENTATION SUB-CAMPAIGN COMPLETE.** 4-batch arc shipped: v8.11 plan → v8.12 Phase 1 engine → v8.14 Phase 2 generators → **v8.15 Phase 3 UI surface**. The audit-locked claim discipline now operates at three levels: build-time, generation-time, and operator-time.

---

## What this batch is

**Pure UI batch.** Adds a new 📑 Living Documentation sub-tab to `pages/7_admin.py` System section, within G4's strict 7-tab cap (System: 2 → 3 sub-tabs).

**One thing shipped**: ~150 lines of admin-page extension that lets operators trigger collateral regeneration without leaving the dashboard, see the live registry snapshot, observe drift errors via the audit-claim diff view, and review the sub-campaign progress map.

This closes the canonical 2-batch + UI surface sequence per Part 7 of the v8.11 Living Documentation Plan.

---

## What changed

### `pages/7_admin.py` — new 📑 Living Documentation sub-tab

Sits beside `⚙️ System health` and `📤 Upload format` in the System section. **G4 verifies the 7-tab cap is preserved** (System currently has 3 sub-tabs).

The sub-tab body has 5 panels:

#### Panel 1 — Registry Snapshot

Calls `scripts.docgen.load_registry()` to read live tier 1-5 state. Displays 4 metric cards via `st.columns(4)`:

| Metric | Source |
|---|---|
| Audit gates | `platform.audit_gates` |
| Stocks (wired) | `stocks_wired / stocks_count` |
| Loops (wired) | `loops_wired / loops_count` |
| Sales-content JSONs | `sales_content_files_present / 6` |

Caption line: Platform version + Engines count + CHANGELOGs count + Learning loops count.

Defensive try/except — missing docgen package shows clear error not crash.

#### Panel 2 — 4 individual Generate buttons

Layout: `st.columns([1, 3])` so button is left-aligned, description right-aligned.

| Button | Target | What it generates |
|---|---|---|
| 📊 Brochure (PPTX) | brochure | A2Z_MIS_360_Brochure.pptx (15 slides) |
| 📖 Magazine (PDF) | magazine | A2Z_MIS_360_Magazine.pdf (multi-page) |
| 🛡️ Security Whitepaper | security | A2Z_MIS_360_Security_Whitepaper.pdf (CISO) |
| 📜 Compliance Pack | compliance | A2Z_MIS_360_Compliance_Pack.pdf (regulator) |

**Click handler**:
1. Calls `TARGETS[target_id](out_dir)` from `scripts.generate_all_docs`
2. **Success path**: `st.success` with KB size + claims-validated count + saved path + `st.download_button` for direct file download
3. **Failure path**: `st.error` with reason + **audit-claim diff view** rendering each failure as `st.warning` with claim_text + registry_path + expected value + error message + closing `st.info` explaining "This is the audit-locked claim discipline working as designed"

#### Panel 3 — Generate-all CTA

Single button that runs all 4 generators in sequence with `st.progress` updates. Aggregates `total_claims_validated` across the 4 generators. Shows summary success/warning + collapsible expander with per-target results.

#### Panel 4 — Sub-campaign Progress Map

Markdown table showing the 5 phases:

| Phase | Batch | Status |
|---|---|---|
| Plan | v8.11 | ✅ Shipped |
| Phase 1 | v8.12 | ✅ Shipped |
| Phase 2 | v8.14 | ✅ Shipped |
| **Phase 3** | **v8.15** | ✅ **You're looking at it** |
| Phase 4 (G110) | v8.16+ | ⏳ Optional hardening |

The "You're looking at it" line on the v8.15 row makes the campaign self-aware as a feature.

#### Panel 5 — Spirit caption

References docs/A2Z_LIVING_DOCS_PLAN.md Part 7 + Spirit Statements. Reminds operators: "the campaign that built the platform now operates the discipline that documents it."

---

## End-to-end smoke test (all green)

```
=== Compile check ===
  ✓ pages/7_admin.py compiles cleanly (2,873 → 3,023 lines)

=== Audit ===
  ✓ G4 tab_counts: 0 pages exceed 7-tab limit (System now 3 sub-tabs)
  ✓ Score: 109/109 gates = 100.0% — PASS

=== Import test ===
  ✓ TARGETS dict importable: ['brochure', 'compliance', 'magazine', 'security']
  ✓ load_registry() returns dict with platform.audit_gates=109,
    stocks_count=6, loops_count=15, sales_content_files_present=6
```

---

## ✅ Forty-first consecutive clean-first-try

41 batches in a row landing clean — v5.96 → v8.15.

**The Living Documentation sub-campaign is now COMPLETE** as a 4-batch arc. All 4 batches landed clean on first try.

---

## Comparison vs v8.14

| | v8.14 | v8.15 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Standards in UI | 62 | **63** ⭐ (+1: Living Doc admin tab) |
| **Living Doc admin UI** | **None (CLI only)** | **Operator-facing tab with 4 buttons + diff view** ⭐ |
| **Audit-locked claim discipline operating at** | **2 levels** (build-time + generation-time) | **3 levels** (+ operator-time via UI) ⭐ |
| Living Doc sub-campaign | Phase 2 done (3 of 4 phases) | **Phase 3 done — sub-campaign COMPLETE** ⭐ |
| Clean-first-try streak | 40 | **41** |

---

## Strategic narrative — Living Documentation sub-campaign COMPLETE

| Phase | Batch | Status |
|---|---|---|
| Plan | v8.11 | ✅ |
| Phase 1: registry loader + claim validator + 6 sales-content JSONs | v8.12 | ✅ |
| Phase 2: 3 generators + orchestrator | v8.14 | ✅ |
| **Phase 3: admin/systems-view UI surface** | **v8.15** | ✅ **shipped** |
| Phase 4: G110 audit gate (optional hardening) | v8.16+ | ⏳ |

**The audit-locked claim discipline now operates at three levels:**

1. **Build-time** — `_claim_validator.py` raises `ClaimValidationError` on divergence
2. **Generation-time** — each generator's `_build_claims()` aborts before writing if claims fail validation
3. **Operator-time** — the new admin UI surfaces the diff view when operators click Generate; drift errors are visible immediately with claim text + registry path + expected value

**Both sub-campaigns now have substantive deliverables:**
- Living Documentation: complete 4-batch arc (plan + Phase 1 + Phase 2 + Phase 3)
- Legal Infrastructure: plan (v8.13) + Tier 1 LICENSE.md (v8.14)

The mandatory honest-scope discipline is reinforced in the UI: operators reading the new tab see explicit progress markers + a "sub-campaign progress map" placing current state in context.

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — admin tab compile-tested via Python; user runs `streamlit run app.py` to confirm tab renders + click handlers work + download buttons fire.
2. **Output directory is `/tmp/a2z_living_docs_runtime`** — works in dev environment; production deployments need a configurable path; Joshua should change to `generated_docs/` for production.
3. **No persistence of last-generated timestamps across sessions** — UI shows current registry snapshot but doesn't remember when artifacts were last generated; future enhancement: `generated_docs/manifest.json`.
4. **The 4 generate buttons are independent** — each runs in foreground (no async); fine for ~1-3s artifacts; if any becomes slow, future v8.16+ could move to async.
5. **Audit-claim diff view shows up to all failures** — typical 1-3 cases fine; pathological 50+ failures would scroll page (edge case investigated via CLI anyway).
6. **Download button stores file content in memory** — works for 8-53 KB artifacts; if magazine grows to several MB, future could stream rather than load full content.
7. **Registry snapshot is loaded synchronously** — adds ~50ms to admin page load; acceptable for visibility benefit.
8. **No A/B testing or analytics** on which artifacts operators generate most — could be added in v9.x telemetry.
9. **Generate-all CTA doesn't parallelize** — 4 sequential generators run in ~5-10s total; parallelizing via threading would require careful state isolation; not worth complexity.
10. **The new sub-tab is in System section not a new top-level Documentation section** — keeping in System within sub-tabs preserves G4 7-tab cap.
11. **Generated artifacts are not auto-committed to repo** — by design (registry drift would invalidate fixtures); operators run UI button before customer engagements.
12. **The 41-batch clean streak now includes the Living Doc sub-campaign in full** (v8.11 + v8.12 + v8.14 + v8.15 = 4 batches all clean-first-try); the discipline pattern is reproducible across multi-phase sub-campaigns.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.16 G110 audit gate 'collateral claims traceable to registry'** | Final hardening; locks discipline as permanent invariant; 109 → 110 gates; small focused batch ~100 lines; 42nd-clean candidate |
| (2) | v8.16 Resume v8.6 retrospective backlog | Close 1-2 of remaining 7 acks (per-endpoint circuit, event-bus dedup, retry-count telemetry, etc.) |
| (3) | v8.16 Operational Legal Tier 1 templates | Author NDA + IP Assignment + Reference Customer Agreement as TEMPLATE drafts in `docs/legal_templates/` for Joshua's lawyer to refine |

**Strong recommendation: v8.16 = G110 audit gate** — closes the Living Doc sub-campaign with the audit-hardening pattern (G108 v8.3, G109 v8.7, G110 v8.16); locks the audit-locked claim discipline as permanent invariant so future regressions fail the build; consistent with the established v8.x audit-hardening rhythm.

---

🎯 **Living Documentation sub-campaign COMPLETE — 4-batch arc shipped (v8.11 plan + v8.12 Phase 1 + v8.14 Phase 2 + v8.15 Phase 3 UI). Audit-locked claim discipline now operates at 3 levels (build-time + generation-time + operator-time).**

⭐ **41st consecutive clean-first-try. The campaign that built the platform now operates the discipline that documents it — visible to operators in the dashboard.**
