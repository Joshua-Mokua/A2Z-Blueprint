# Recommendations on the v10.380 Part 9 Decisions

**Version anchor:** v10.381 (May 2026)
**Per:** Joshua's directive — *"on the questions requiring my decision, i would welcome your recommendation on what decision will make the body function better as one"*
**Lens:** Constitution §12 (Flow Principle) + body-system framing (organs in harmony) + Donella Meadows systems-thinking (no single-variable optimization)

Eight decisions queued by v10.380's deep review. For each, I argue the case from the **"body functioning as one"** lens — what makes the organs serve the whole.

---

## Decision 1 — Class B KPI definitions (15 orphans)

### My recommendation: **TIERED ADD — 9 new KPIs, 1 alias, 4 deferred, 1 verify**

The body cannot regulate what it cannot measure. The MD literally cannot see Net Interest Margin (the most fundamental banking metric) on her own BSC today. That's a body without a pulse-sensor.

### Tier 1 — MUST ADD (5 KPIs, all Tier-1 banking benchmarks)

| KPI | Why this organ matters |
|---|---|
| `NIM` (Net Interest Margin %) | The bank's earning-asset productivity. Without it, MD can't tell if the loan book is generating enough interest margin. **Non-negotiable for Financial pillar completeness.** |
| `CIR` (Cost-to-Income Ratio %) | Operating efficiency. Tier-1 benchmark for every bank. Without it, MD can't see if costs are eating margin. |
| `ROE` (Return on Equity %) | Shareholder-return metric. Defines whether the bank is creating value vs destroying it. |
| `NPS` (Net Promoter Score) | Customer Focus pillar is incomplete without it. CX Score (existing) measures operational satisfaction; NPS measures advocacy/loyalty. Two organs, both needed. |
| `DEP_GROWTH` (Total Deposit Growth %) | Aggregate of Retail+Commercial. Currently only sub-segments are measured. The MD needs the aggregate to talk about bank-wide deposit story. |

### Tier 2 — SHOULD ADD (4 KPIs, role-specific completeness)

| KPI | Reasoning |
|---|---|
| `DIGITAL_ACT` (Digital Activation Rate %) | Digital banking dimension of Customer Focus. Becoming Tier-1 as channels shift. |
| 5 LEGAL_* (Chief Legal Officer SLAs) | The Chief Legal Officer literally has no measurable BSC without these. Niche but necessary. |

### Tier 3 — RECLASSIFY AS ALIAS (1 KPI)

| KPI | Action |
|---|---|
| `NEW_CUST` | Library has `NEW_CUSTOMERS_ACQUIRED` (same concept). **Move to KPI_ALIASES** — no new definition needed. Promotes from Class B to Class A. |

### Tier 4 — DEFER WITH RATIONALE (4 KPIs)

| KPI | Why defer |
|---|---|
| `FEES_COMM` | `TOTAL_NFI` already exists and supersets it. Adding `FEES_COMM` separately creates double-counting risk. If you want to measure fees alone, decompose `TOTAL_NFI` into sub-components rather than parallel KPIs. |
| `ACTIVE_ACCTS` | Derived from `ACCOUNT_DORMANCY` (inverse). Compute on demand rather than store as separate KPI. |
| `TRANSACTIONS` | Ambiguous — digital? total? per customer? Per period? Needs scope definition before adding. |
| `PAR` | Library actually HAS `PAR` per my v10.380 search. The role_kpis orphan flag may be a coverage-scanner false positive. **Action: verify in v10.381 zip; if PAR resolves, remove from Class B.** |

### Why this tiered approach makes the body function better as one

A complete Financial pillar (NIM, CIR, ROE alongside existing PBT, NPL_RATIO) gives the MD's brain a full vital-signs panel. NPS plus existing CX Score gives the Customer Focus organ both sides of the customer relationship (operations + loyalty). The body becomes self-aware in the dimensions Donella Meadows would call **"feedback loops to the leverage points."**

Adding everything indiscriminately would bloat the BSC and dilute attention. Tiered addition keeps signal-to-noise high.

---

## Decision 2 — Pillar weights (40/25/25/10 vs 68/14/6/12)

### My recommendation: **40/25/25/10 — return to balanced**

68/14/6/12 means Financial = 68% of the score. The other three pillars contribute 32% combined. That isn't a "Balanced" Scorecard — it's a financial scorecard with token mentions of the other pillars.

### Why this matters for the body

When the body optimizes for one organ (Financial), the others atrophy:
- Customer attrition rises (Customer Focus undervalued)
- Operational defects compound (Op Excellence undervalued)
- Staff turnover increases (People & Learning undervalued)

Eventually the Financial organ ITSELF degrades because the other organs aren't sustaining it. This is the **Donella Meadows feedback-loop failure** — single-variable optimization destroys complex systems.

Kaplan & Norton designed the BSC at 40/25/25/10 precisely because organs sustain each other.

### Suggested action

In `kpi_library.json`:
1. Make `pillars[].weight` (which has 0.40/0.25/0.25/0.10) the canonical source of truth
2. Delete the `pillar_weights` field (which has 0.68/0.14/0.06/0.12) OR set it to match `pillars[]`
3. Update `bsc_score_computation.py` to read from `pillars[].weight` only

### Counter-argument (in honesty)

68/14/6/12 may reflect **current crisis posture** — when NPL is 11.1% and PBT is negative, focusing on Financial recovery makes sense. If that's the deliberate choice, document it explicitly with a return-to-balance date (e.g. "review weights Q2 2027 when NPL <8%").

---

## Decision 3 — K-code retirement

### My recommendation: **Phased retirement — alias first, deactivate second, remove third**

K-codes are dead organs that the body keeps preserved. They duplicate modern equivalents (K001 = "Loans Disbursed", LOAN_DISB alias also maps to K001 in our v10.380 setup).

### Three-phase migration

| Phase | Action | Risk |
|---|---|---|
| v10.382 | Add K-code → SCREAMING_SNAKE aliases in `KPI_ALIASES` so existing consumers redirect | Low (additive only) |
| v10.383 | Set `active: false` on all K-code library entries | Low (consumers fall back to aliases) |
| v10.385+ | Remove K-code entries entirely | Medium (need to verify no consumers reference K-codes) |

### Why this makes the body function better as one

Duplicate organs split the immune system. When two KPIs name the same metric, the body wastes effort tracking both. K001 + LOAN_DISB + "Loans Disbursed (KES M)" + (alias) = three references for one truth. Pick one (SCREAMING_SNAKE), redirect the others.

---

## Decision 4 — Cascade `deadline|*` cleanup

### My recommendation: **Move to top-level `cascade_meta` field + keep defensive filter**

Mixing metadata with cascade entries is a category error. A consumer iterating `for key in cascade.keys()` should see only cascade entries. Today, the `deadline|*` corruption forces every consumer to defensively filter.

### Suggested structure

```json
{
  "cascade_meta": {
    "300001|2026": {
      "targets_locked": true,
      "locked_at": "2026-04-15T18:14:31",
      "confirm_by": "2026-05-25",
      "cascade_by": "2026-05-09"
    }
  },
  "300001|PBT|2026": { "from_code": "300001", ... },
  "300001|NPL Ratio|2026": { ... }
}
```

The migration is a one-time `target_cascade.json` rewrite. After it, `clean_cascade_dict` from v10.380 still works (defense-in-depth).

### Why this makes the body function better as one

Each organ should know its role. The cascade dict is for transactional data; metadata about the cascade process is a different concern. Single Responsibility Principle for data structures.

---

## Decision 5 — Active KPI count (active=null normalization)

### My recommendation: **Normalize `active=null` → `active=false` (treat as retired)**

Ambiguity in active state means different consumers compute different counts. Some treat null as active, others as inactive. **Silent inconsistency** per constitution §5.4 (no silent failures).

The few KPIs with `active=null` (e.g. K084) are old K-codes that should retire anyway (Decision 3).

### Why this matters for the body

A clear alive/dead distinction for each organ enables the rest of the system to reason about it. Schrödinger's-KPI breaks audit trails.

One-line migration: `for kpi in kpis: kpi['active'] = bool(kpi.get('active', False))`.

---

## Decision 6 — role_kpis (227) vs taxonomy (126) reconciliation

### My recommendation: **Add `role_status` metadata; keep both**

The 101 extra role_kpis entries are likely a mix of:
- Aspirational roles (planned but no current staff)
- Legacy roles being phased out
- Variants of existing roles

Wholesale deletion is risky. Marking each role's status preserves history while making the gap explicit.

### Suggested schema

```json
{
  "role_kpis": {
    "Managing Director": {
      "kpis": ["PBT", "NPL_RATIO", "NIM", "CIR", "ROE", ...],
      "role_status": "active",        // matches taxonomy
      "role_taxonomy_id": "MD"
    },
    "Future Chief AI Officer": {
      "kpis": ["AI_PROJECTS_DELIVERED", "MODEL_GOVERNANCE_SCORE"],
      "role_status": "aspirational",  // planned, no staff
      "role_taxonomy_id": null
    }
  }
}
```

### Why this makes the body function better as one

The body should know which organs exist vs which are planned vs which are vestigial. Status tagging makes the body's self-knowledge explicit. Donella Meadows: **"reality is exposed by being modeled."**

---

## Decision 7 — `cbk_ref` population

### My recommendation: **YES, populate for the ~10-12 regulatory KPIs only**

For KPIs with actual CBK regulatory anchor, populate `cbk_ref` with the specific guideline. For KPIs without CBK anchor (Staff Productivity, CX Score), leave empty — fabricating refs is worse than leaving blank.

### Suggested priority order

| KPI | Suggested cbk_ref |
|---|---|
| `NPL_RATIO` | CBK Prudential Guidelines CBK/PG/04 — Risk Classification |
| `COMPLIANCE_SCORE` | CBK Banking Act §32 + AML Reg 2013 |
| `AUDIT_SCORE` | CBK PG/02 — Audit & Internal Controls |
| `PAR` | IFRS 9 + CBK PG/04 |
| `CASA Ratio` | CBK PG/15 — Liquidity Risk Management |
| `Compliance Score` | CBK PG/03 — KYC/AML |
| New: `NIM` | CBK Annual Bank Supervision Report disclosure standard |
| New: `CIR` | CBK Annual Bank Supervision Report disclosure standard |
| New: `ROE` | CBK Annual Bank Supervision Report disclosure standard |

### Why this makes the body function better as one

When the regulator audits the bank, each KPI shows its regulatory provenance directly. The body's regulatory pulse is traceable without manual lookup. This is the **§8.1 audit traceability** mandate from the constitution.

---

## Decision 8 — ID convention going forward

### My recommendation: **SCREAMING_SNAKE_CASE wins (it's already 91% dominant — make it canonical)**

Today 169/185 library IDs are SCREAMING_SNAKE. It's the de facto standard. The 14 Title Case entries (where id == name like "CASA Ratio") are odd edge cases — using strings with spaces as IDs is fragile in URL/CSV/code contexts. The 18 K-codes are opaque.

### Three-step plan

| Step | Action |
|---|---|
| v10.382 | Add Title Case → SCREAMING_SNAKE aliases (e.g. `"CASA Ratio" → "CASA_RATIO"`); set duplicate Title Case entries to `active: false` |
| v10.382 | New canonical ID for each duplicate (e.g. add `CASA_RATIO` if not exists) |
| v10.383 | Migrate cascade keys from name-based to ID-based (`'300001\|CASA Ratio\|2026'` → `'300001\|CASA_RATIO\|2026'`) — one-time cascade rewrite |

### Why this makes the body function better as one

When every organ has one canonical name across all consumers (bsc_engine, target_cascade, role_kpis, bsc_actuals), the integration friction drops to zero. The v10.380 alias resolver currently bridges the drift — eventually the drift should disappear.

Per constitution §5.1 (Universal BSC Data Contract): KPI references should be unambiguous. SCREAMING_SNAKE is the unambiguous form.

---

## How these recommendations compose

If you accept the recommendations (or your own variants):

| v10.382 | Add 9 new KPIs (NIM, CIR, ROE, NPS, DEP_GROWTH, DIGITAL_ACT, 5 LEGAL_*) with cbk_ref where applicable + alias NEW_CUST → NEW_CUSTOMERS_ACQUIRED + verify PAR + normalize pillar_weights to 40/25/25/10 + active=null → false |
| v10.383 | Add K-code → SCREAMING_SNAKE aliases; set K-codes active=false; add Title Case → SCREAMING_SNAKE aliases for duplicates |
| v10.384 | Add `cascade_meta` field; migrate `deadline|*` keys; add `role_status` metadata to role_kpis |
| v10.385 | Migrate cascade keys from name-based to ID-based; verify nothing breaks; remove deprecated K-code entries |

Four batches to close all 8 decisions, with each one keeping Rule N2 single-concern discipline.

---

## Honest acknowledgement

These are my recommendations based on the deep review (v10.380) and the body-system framing. **They are not authoritative until you approve them.** Some of these decisions have downstream consequences I can't fully predict (e.g. which BSC consumers actually use Title Case vs SCREAMING_SNAKE today). The recommendations document is meant to **inform your decisions**, not replace them.

The most important recommendation, if you only had time for one: **Add NIM, CIR, ROE, NPS as KPIs.** Without these, the MD's BSC cannot present a complete banking story. Every other recommendation is process improvement; these four are about the body being able to know itself.
