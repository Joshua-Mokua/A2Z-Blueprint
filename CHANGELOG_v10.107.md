# CHANGELOG v10.107 — cascade↔library reconciliation + master prompt v3.1

**Status:** Phase 1D kickoff. Three deliverables: full master prompt update folding 27 versions of unrecorded closure into the canonical state-of-play; library reconciliation closing the 18-KPI gap between cascade and library; regression test locking the resolution contract.

**Audit:** 142/142 PASS in sandbox.
**Engine self-tests:** 152/152.
**Library KPI count:** 111 → 129 (+18).
**Cascade KPI resolution:** 3/21 → **21/21 (100%)**.

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.107 | After v10.107 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 | 51 / 163 | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| API endpoints | 147 / 136 (108.1%) | 147 / 136 (108.1%) | 0 (Phase 1B frozen) |
| Standard #4 spec targets PASS | 3 / 5 active + 2 aspirational | 3 / 5 active + 2 aspirational | 0 (Phase 1C frozen) |
| Library KPIs | 111 | **129** | +18 |
| Cascade KPIs resolving to library | 3 / 21 (14.3%) | **21 / 21 (100%)** | +18 |
| Master prompt version | v3.0 (line 108 = v10.80) | **v3.1 (line 108 = v10.107)** | +27 versions caught up |

---

## Why this drop matters

The original master prompt v3.0 explicitly identified the deferred Integration Layer at line 36674 of the continuation document:

> *"the CBS auto-load, target cascade, and KPI Library aren't wired to consume from tax_compliance.py, procurement_workflow.py, group_consolidation.py, etc. The 104 standards are a library that an integration layer would consume. That integration layer is the work we kept saying 'next: integration/orchestration layer' — and we kept deferring it for another volume of standards."*

Phase 1D ships that deferred Integration Layer. v10.107 is the precursor — before the autofit aggregator can route actuals to the right staff for cascade-allocated KPIs, those cascade KPIs need to actually exist in the library. Pre-v10.107, 18 of 21 cascade KPI names had no library entry. Post-v10.107, all 21 resolve cleanly.

Plus this drop closes a separate process gap: the master prompt had drifted 27 versions out of date (line 108 said v10.80; actual platform state was v10.106). Going forward, every closure drop ships an updated master prompt section. SCOPE_LEDGER and master prompt move in lockstep.

---

## Deliverable 1 — `docs/Master_Prompt_v3.1.md`

Full master prompt update. Three substantive changes from v3.0:

### Header
Line 1: `# A2Z MIS 360 — Master prompt (v3.1)` (was `v3.0`).

### Line 108 — `Current version` rolled up
Replaced the v10.80 narrative (trade_finance arc closure) with a v10.107 narrative folding 27 versions:

- **Phase 1A (v10.81-v10.91)** — PostgreSQL migration completion. 53/52 tables (101.9%). 28 newly-wired tables across 40 FLAT + 8 NESTED + 2 SPECIAL + 3 legacy patterns. v10.93 expanded TABLE_USE_DB to 79 entries.
- **Phase 1B (v10.92-v10.96)** — API endpoint coverage. 147/136 endpoints (108.1%). 19 direct decorators + 16 CRUD modules × 8 verbs = 128 CRUD endpoints. JWT-protected via Depends chain.
- **Phase 1C (v10.97-v10.106)** — Test coverage push. **3/3 active Standard #4 spec targets PASS** (core_kpi 100%, auth_jwt 95.0%, bsc_engine 98.9%) + 2 declared aspirational with explicit Joshua-decision rationale. 379 pytest cases. Closed two long-standing measurement bugs (G18 cobertura schema parser silent false-pass since v5.33; Windows cp1252 encoding crashes). Closed security-relevant bug (auth_jwt IndexError on Bearer-without-token leaked tracebacks via 500). Restored mlops_model_registry.py (was missing from local repo).
- **v10.107** — cascade↔library reconciliation. 18 new library entries + 3 alias entries. 21/21 cascade KPIs resolve.
- **Phase 1D scope (v10.108+)** — Integration Layer kickoff explicitly named per master prompt v3.0's deferred-work identification.
- **Anti-drift discipline going forward**: every closure drop updates the master prompt in lockstep.

### Verified gaps section — 5 new entries
Four strikethrough closures (Phase 1A, Phase 1B, Phase 1C, cascade↔library reconciliation) and one open entry (Phase 1D in progress).

### Footer
Added v3.1 update notice explaining the drift catch-up.

---

## Deliverable 2 — `data/kpi_library.json` reconciliation

### 18 new entries

The cascade uses the cascade name as both `id` and `name` so cascade lookups resolve directly. The `code` field stores the actuals_engine ID_MAP key (which is what the engine already uses to map CBS aggregations to KPI submissions). 15 of 18 already have wired CBS aggregations — autofitting via existing pathway.

| Cascade name | Engine code | Source | Pillar | Weight | Direction |
|---|---|---|---|---|---|
| Account Dormancy | ACCOUNT_DORMANCY | cbs_accounts | Operational Excellence | 0.05 | lower |
| Audit Score | AUDIT_SCORE | audit_reviews | Operational Excellence | 0.05 | higher |
| CASA Ratio | CASA_RATIO | cbs_deposits | Financial | 0.10 | higher |
| CX Score | CX_SCORE | nps | Customer Focus | 0.10 | higher |
| Channel Dormancy | CHANNEL_DORMANCY | digital_channels | Operational Excellence | 0.05 | lower |
| Collection Throughput | COLLECTION_THROUGHPUT | debt_recovery | Financial | 0.05 | higher |
| Commercial Deposit Growth | COMMERCIAL_DEPOSIT | cbs_deposits | Financial | 0.10 | higher |
| Disbursements Corporate Loans | DISB_CORPORATE | cbs_loans | Financial | 0.08 | higher |
| Disbursements MSME Loans | DISB_MSME | cbs_loans | Financial | 0.08 | higher |
| Disbursements Retail Loans | DISB_RETAIL | cbs_loans | Financial | 0.08 | higher |
| Loan Book Growth | LOAN_GROWTH | cbs_loans | Financial | 0.12 | higher |
| Number of Business Borrowers | BUSINESS_BORROWERS | cbs_loans | Customer Focus | 0.05 | higher |
| PAR | PAR | cbs_loans | Financial | 0.10 | lower |
| PBT | PBT | management_accounts | Financial | 0.20 | higher |
| Retail & MSME Deposit Growth | RETAIL_MSME_DEPOSIT | cbs_deposits | Financial | 0.10 | higher |
| Staff Productivity | STAFF_PRODUCTIVITY | hr | People & Learning | 0.10 | higher |
| Top 100 Customers Deposit | TOP100_CUSTOMERS | cbs_deposits | Customer Focus | 0.05 | higher |
| Total NFI | TOTAL_NFI | cbs_fees | Financial | 0.15 | higher |

3 sources need future operational connectors (audit_reviews, nps, hr) — these are human-judgement KPIs from periodic surveys/reviews, not transactional data. They'll be picked up later once Phase 1D completes the operational-table tributary.

### 3 alias additions

Existing library entries fuzzy-matched the cascade names. Aliases declared explicitly:

| Existing library entry | Alias added |
|---|---|
| K004 (NPL Ratio (%)) | NPL Ratio |
| K006 (New Accounts Opened) | New Accounts |
| K014 (AML/CFT Compliance Score) | Compliance Score |

---

## Deliverable 3 — `utils/bsc_engine.py` patch

`_load_kpi_index` patched to also index by the `aliases` field. Cascade entries can now reference KPIs through any of: id, code, name, alias.

```python
# v10.107: alias support — cascade entries refer to KPIs by short
# names (e.g. "NPL Ratio" for the library's "NPL Ratio (%)") that
# don't match id/code/name exactly. The library's `aliases` list
# provides the resolution.
for alias in kpi.get("aliases", []) or []:
    if str(alias) not in idx:
        idx[str(alias)] = kpi
```

---

## Deliverable 4 — `tests/test_cascade_library_reconciliation.py`

5 regression tests:

1. **`test_cascade_has_at_least_v10_107_floor`** — cascade references ≥21 distinct KPIs (locks v10.107 baseline; if drops, deletion was unintentional).
2. **`test_every_cascade_kpi_resolves_to_library`** — the contract: every cascade KPI name must resolve via library lookup. A failure here means autofit pipeline can't route actuals for that KPI.
3. **`test_library_entries_for_v10_107_additions_are_well_formed`** — all 18 new entries have required fields (id, name, pillar, weight, unit, direction, active, description, source); pillar in valid_pillars; direction in (higher, lower); weight in (0, 1].
4. **`test_aliases_resolve_correctly`** — the 3 v10.107 aliases resolve to K004, K006, K014.
5. **`test_library_kpi_count_floor`** — library has ≥129 KPIs (111 pre-v10.107 + 18 added).

---

## Deliverable 5 — SCOPE_LEDGER.md update

- Last updated: v10.106 → v10.107.
- Phase 1C status block updated: bsc_engine 98.9% (closed v10.106 with 8 surgical tests).
- Phase 1D status: KICKOFF — cascade↔library reconciliation closed. Detailed deliverable list (master prompt v3.1, library +18, alias +3, bsc_engine alias-indexing patch, 5-test regression file).
- Phase 1D code (v10.108): NOT STARTED. Detailed scope: kpi_ownership, kpi_aggregation_rules, compute_actuals_from_operational_tables, staff_field_resolver, G143.

---

## What v10.107 doesn't ship

**Integration Layer code itself.** That's v10.108. v10.107 is the precursor — library reconciliation + master prompt update + anti-drift restoration. Code work begins next.

**Strict enforcement of cascade lock.** The cascade lock signal (`deadline|<staff>|<period>` records with `targets_locked: true`) is in the data model but not yet consumed by the autofit pipeline. v10.108's `kpi_ownership.py` will check this.

**Audit gate G143.** Not added in v10.107. Comes with v10.108 alongside `kpi_aggregation_rules.py`.

---

## Anti-drift commitments going forward

Joshua flagged the 26-version master-prompt drift (v10.81-v10.106 not reflected in master prompt) as the gap being closed by v10.107. The commitment going forward:

1. **Every closure drop ships an updated master prompt section.** Either a new strikethrough in Verified Gaps, or an update to the Current version line, or both.
2. **SCOPE_LEDGER and master prompt move in lockstep.** A drop that updates one without the other fails self-review.
3. **Master prompt version bumps each closure.** v3.1 → v3.2 at v10.108 closure, etc.
4. **Master prompt is the cross-chat contract.** Any future chat reading the latest master prompt should know exactly where the platform is. No information lives only in chat history.

---

## Verification

```
$ python scripts/audit.py
  Score: 142/142 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines

$ python -c "
import json
with open('data/target_cascade.json') as f: cascade = json.load(f)
with open('data/kpi_library.json') as f: lib = json.load(f)
idx = {}
for k in lib['kpis']:
    for fld in ('id','code','name'): idx.setdefault(str(k.get(fld)), k)
    for a in k.get('aliases', []): idx.setdefault(str(a), k)
names = {v['kpi'] for v in cascade.values() if isinstance(v,dict) and 'kpi' in v}
print(f'Resolved: {sum(1 for n in names if n in idx)}/{len(names)}')
"
  Resolved: 21/21
```

---

## Files in this drop

```
docs/Master_Prompt_v3.1.md                        # NEW (1002 lines)
data/kpi_library.json                             # MODIFIED (+18 entries, +3 aliases)
utils/bsc_engine.py                               # MODIFIED (_load_kpi_index alias indexing)
tests/test_cascade_library_reconciliation.py      # NEW (5 tests)
SCOPE_LEDGER.md                                   # MODIFIED (v10.107 status)
CHANGELOG_v10.107.md                              # this file
```

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                          # → 142/142 PASS
$ pytest tests/test_cascade_library_reconciliation.py -v
  ... 5 passed
```

Next: v10.108 — Integration Layer code (kpi_ownership.py, kpi_aggregation_rules.py, compute_actuals_from_operational_tables, staff_field_resolver.py, G143).
