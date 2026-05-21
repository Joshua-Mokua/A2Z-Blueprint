# CHANGELOG v10.53 — revenue_assurance arc · ENH-244 Partner & Supplier Reconciliation

**Status:** revenue_assurance arc 4/8+1 batches (4 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (318 modules · 795 imports · 3 HARD baseline)
**Active standards:** 122 → **123** / 260 · **Scenario library:** 66 → **70** (4 PSR-* added)

## What this batch does

Extends ENH-241's two-source reconciliation pattern (CBS vs GL within
the bank) to **multi-party** cases. Two capability blocks in one
engine:

- **Partner revenue share** — agreement-driven `expected_share = Σ(gross × share_pct)` per period, compared to actual settlements with mixed-tolerance check (max of KES 100 absolute or 1% of expected).
- **Supplier 3-way match** — chain `PO → GRN → Invoice → Payment` with KES 100 tolerance per step. Multiple GRNs per PO sum (real-world partial deliveries). Six discrepancy types covering the four common control gaps plus timing + authorisation issues.

The new module is what ENH-241's `reconcile_sources` is structurally
*not* — that one pairwise-matches arbitrary `CrossSourceTotal`
records; this one understands the structured semantics of agreement
share calculations and 3-way procurement matching.

## New module

- `utils/partner_supplier_recon.py` (~1140 lines · 20 self-tests) —
  pure stdlib (`Decimal` + frozen dataclasses + enums). Single
  public engine `PartnerSupplierReconciliationEngine` exposing
  `validate_partner_share`, `match_supplier_three_way`,
  `reconcile_all` orchestrator.

## Architecture

### Discrepancy taxonomy (9 types)

**Partner side (3 types):**

| Type | Severity | Trigger |
| ---- | -------- | ------- |
| `SHARE_UNDERPAID` | MEDIUM | settled < expected − tolerance |
| `SHARE_OVERPAID` | MEDIUM | settled > expected + tolerance |
| `SHARE_MISSING` | HIGH | revenue ≥ min_settlement_kes but no settlement |

**Supplier side (6 types):**

| Type | Severity | Trigger |
| ---- | -------- | ------- |
| `PO_GRN_MISMATCH` | MEDIUM | Σ(GRN) ≠ PO ordered |
| `GRN_INVOICE_MISMATCH` | HIGH | Σ(invoice) ≠ Σ(GRN) — overbilling concern |
| `INVOICE_PAYMENT_MISMATCH` | HIGH if overpaid, MEDIUM otherwise | paid ≠ invoiced |
| `PO_WITHOUT_INVOICE` | MEDIUM | GRN exists, no invoice (unrecognised liability) |
| `INVOICE_WITHOUT_PO` | MEDIUM | invoice has `po_id=None` (authorisation chain gap) |
| `INVOICE_BEFORE_DELIVERY` | MEDIUM | `invoice_date < earliest_grn_date` (premature billing) |

### Key design decisions

- **Multiple GRNs per PO sum.** Partial deliveries are normal in
  procurement; the engine aggregates GRNs by `po_id` rather than
  requiring 1:1 matching. The earliest GRN date is used for the
  invoice-before-delivery check.
- **Below `min_settlement_kes` → carried-forward, not flagged.**
  Many partner agreements have minimum settlement floors — small
  amounts roll into the next period rather than being paid out.
  Flagging these as `SHARE_MISSING` would be noise.
- **Zero-paid invoices not flagged as mismatch.** An invoice booked
  but unpaid may simply not be due yet; the engine only flags
  *clear* discrepancies (paid > 0 but ≠ invoiced). Days-since-due
  tracking belongs to a future AP-aging engine, not here.
- **`ValidationSeverity` reused from ENH-241.** Single severity
  vocabulary across all four revenue_assurance engines so the
  ENH-243 orchestrator can route findings from any of them
  uniformly. The orchestrator's existing `family_or_category`
  routing field accepts any string — `DiscrepancyType.value` slots
  in cleanly when callers wrap ReconciliationFinding into their
  workflow.

## Rule 1 / Rule 7 alignment

- All 9 dataclasses frozen: `PartnerAgreement`,
  `PartnerRevenueRecord`, `PartnerSettlement`, `PurchaseOrder`,
  `GoodsReceiptNote`, `SupplierInvoice`, `SupplierPayment`,
  `ReconciliationFinding`, `ReconciliationReport`.
- Every `ReconciliationFinding` surfaces: `finding_id`,
  `discrepancy_type`, `party_side`, `party_id`, `severity`,
  `related_ids` (tuple of every record ID involved — agreement,
  settlement, PO, invoice as relevant), `expected`, `observed`,
  `variance_kes` (None when not amount-applicable, e.g.
  invoice-before-delivery), `description`, `framework_refs`,
  `notes`. Caller can reproduce from finding alone.
- Engine never:
  - auto-creates settlements (won't generate the missing payment)
  - auto-issues payment instructions to suppliers
  - auto-reverses invoices
  - auto-resolves discrepancies (they stay until human action)
  - mutates source records (frozen guarantees)

## Validation envelope

Construction-time checks via `__post_init__` on every dataclass:

- `PartnerAgreement` rejects empty `agreement_id`, `share_pct`
  outside `[0, 1]`, `effective_to < effective_from`, negative
  `min_settlement_kes`.
- `PartnerRevenueRecord` rejects empty `record_id`, negative
  `gross_revenue_kes`.
- `PartnerSettlement` rejects empty `settlement_id`, negative
  `settled_kes`.
- All four supplier dataclasses reject empty primary IDs and
  negative monetary values.

## Standards registry

- **ENH-244** activated: `status: planned → active`,
  `implementation_batch: v10.40+ → v10.53`,
  `affected_engines: ("revenue_assurance", "reconciliation") → ("partner_supplier_recon",)`.
  Description rewritten with the full 9-type taxonomy, the
  partner-share calculation, the 3-way match chain semantics, the
  partial-delivery aggregation behaviour, the carried-forward
  treatment of below-min settlements, and the Rule 1 / Rule 7
  contracts.
- Registry self-test PASS · total 260 · active **122 → 123**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **PSR-01 Partner share underpaid** — MTN earns KES 3m gross at
  30% = KES 900k expected; settled KES 800k → SHARE_UNDERPAID
  with variance −100k. PARTNER party_side surfaced. 4 assertions.
- **PSR-02 Missing settlement above floor** — SAFCOM earns KES
  500k at 25% = KES 125k expected (above min 10k floor); no
  settlement → SHARE_MISSING HIGH severity. 3 assertions.
- **PSR-03 Supplier GRN-invoice mismatch** — ACME-IT PO 500k, GRN
  500k, invoice 600k → GRN_INVOICE_MISMATCH HIGH, variance
  +100k; payment matches invoice so no INV-PAY finding. 4
  assertions.
- **PSR-04 reconcile_all orchestrator** — VISA missing settlement
  + VENDOR-X invoice before GRN + VENDOR-Y invoice without PO →
  3 distinct discrepancy types across both PartySides; aggregates
  populated; framework refs cite both blocks. 4 assertions.

End-to-end runner: PSR-01..PSR-04 all PASS · **15/15 assertions**.
Scenario library 66 → **70**.

## Self-tests

- `python3 -m utils.partner_supplier_recon` → ✓ 20 tests covering
  validation envelope (3 dataclass post_init checks), partner
  share (clean / underpaid / overpaid / missing / below-min /
  within-tolerance), supplier 3-way (clean / each of 6 discrepancy
  types / partial GRN aggregation / zero-payment-not-flagged),
  orchestrator, full provenance.
- All upstream modules: revenue_orchestrator 23/23 ✓,
  revenue_anomaly_patterns 21/21 ✓, revenue_validation 19/19 ✓,
  scenario_simulator 18/18 ✓, standards_registry ✓. **No
  regression**.

## Gate verification

- `python3 scripts/audit.py` → **Score: 132/132 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (318 modules · 795 imports · 62 findings
  · HARD=3). Module +1 (partner_supplier_recon), imports +2
  (`ValidationSeverity` reuse from ENH-241).

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-244) ✅
- ~1140 line module (test count drove size — 20 tests covering 9
  discrepancy types × edge cases like partial GRNs and below-min
  carried-forwards)
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure ✅
- Audit + G128 + scenario library extension SHIPPED ✅
- Per Rule 1 every ReconciliationFinding surfaces full provenance ✅
- Per Rule 7 engine diagnostic only — no auto-create / auto-issue /
  auto-reverse / auto-resolve ✅

## Files changed

- **NEW** `utils/partner_supplier_recon.py` (~1140 lines, 20 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-244 activated, ~45 line
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 PSR-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.53.md`

## Honest scope notes

1. **No exchange-rate handling.** Partner agreements with foreign
   counterparties (e.g., a USD-denominated VISA agreement) settle
   in KES after FX conversion; the engine compares KES amounts
   directly without a rate-locked layer. Production deployments
   convert to KES at the agreed FX rate before feeding the
   engine — out of scope here.

2. **No partial-delivery date semantics.** When multiple GRNs
   span weeks for one PO, the invoice-before-delivery check uses
   the *earliest* GRN date as the threshold. A real procurement
   system might instead want to require the *full* delivery be
   complete before invoicing. Configurable in a future revision;
   current behaviour is the more lenient interpretation.

3. **No tax/withholding component.** Partner settlements often
   carry withholding tax and the gross/net distinction matters
   (engine compares to gross expected; if `settled_kes` is net of
   WHT, comparison fails). Production extracts must populate
   gross-equivalent settled amounts. Flagged in honest scope
   because it's a common production gotcha.

4. **No multi-period aggregation.** Each finding scopes to one
   `(agreement, period)` pair. If a partner has been chronically
   underpaid for 6 months in a row, the engine produces 6
   findings, not one trend finding. Trend analysis belongs to the
   ENH-243 orchestrator's age-decay scoring + the closure cockpit
   visualisation, not here.

5. **No blanket / framework PO support.** The engine assumes one
   PO = one ordered amount. Real procurement uses blanket POs
   with rolling consumption ("draw down KES 50k at a time against
   a KES 5m blanket"). Future enhancement could add a
   `BlanketPO` dataclass with consumption tracking; current
   design only supports atomic POs.

## Next batch — roadmap

- **v10.54** — ENH-245 Revenue Assurance Dashboard. Per the v10.46
  amendment that consolidated dashboards into closure cockpits, the
  honest move is to **collapse ENH-245 into the v10.58 closure
  cockpit** rather than ship a freestanding "dashboard" engine. I'll
  flag this explicitly in the v10.54 batch and either: (a) implement
  it as a minimal data-aggregation helper that the closure cockpit
  consumes, or (b) note in the registry that ENH-245 is deferred to
  closure and skip a freestanding batch.
- **v10.54..v10.57** — ENH-245..ENH-248 sequentially.
- **v10.58** — revenue_assurance arc closure under v10.46 protocol:
  G133 ratchet + G134 UI ratchet + Tier 26 + Master Prompt +
  `pages/95_revenue_assurance_cockpit.py` wiring all engines.

**135 consecutive clean batches.** 11 closed arcs holding;
revenue_assurance arc at 4/8 + closure pending.
