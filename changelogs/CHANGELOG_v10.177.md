# CHANGELOG v10.177 — ENH-229 Legal Document Management

**Status:** ENH-229 active. 8 of 9 Legal arc standards complete. Audit 153/153 PASS unchanged. 34/34 tests pass.

## What this drop ships

`utils/legal_document_management.py` (~530 LOC) — two-entity engine for legal artifacts (agreements, court filings, regulatory submissions, policies, legal opinions, corporate records, IP documents, correspondence, litigation pleadings). **Distinct from `utils/document_management.py`** which handles KYC/loan documents (national IDs, passports, payslips, bank statements). Different problem domain, different lifecycle, different retention rules — the two engines coexist and do not overlap.

### Two-entity design

**LegalDocument lifecycle** (5 states with reverse-loop):
```
DRAFT ─→ UNDER_REVIEW ─→ APPROVED ─→ ARCHIVED ─→ PURGED
          │
          └─→ DRAFT  (rejected back for revision, requires reason)
```

PURGED is terminal; only valid after the retention window has elapsed (REJECTED_RETENTION_NOT_DUE gate).

**DiscoveryRequest lifecycle** (4 states with early-close escape):
```
REQUESTED ─→ IN_PROGRESS ─→ FULFILLED ─→ CLOSED
                              └─→ CLOSED  (closed without fulfillment)
```

Early CLOSED (from REQUESTED or IN_PROGRESS) requires a reason; CLOSED from FULFILLED does not.

### Kenya statutory retention classes

| Class            | Window     | Basis                                  |
|------------------|------------|----------------------------------------|
| INDEFINITE       | never      | corporate records (CR12, certificates) |
| LITIGATION_HOLD  | hold-gated | preserved while any active hold refs   |
| SEVEN_YEAR       | 7 years    | Companies Act §147 + Tax Procedures Act §59 default |
| TEN_YEAR         | 10 years   | Banking Act §17 records                |
| TWENTY_YEAR      | 20 years   | Limitations of Actions Act (land/title)|

Engine computes `purgeable_after` ISO date at registration. `purgeable_now()` query returns docs that are ARCHIVED **and** past their retention window. The engine never auto-purges — operator decides.

### Cross-engine linkage (recorded but not validated)

- `matter_id` → ENH-223 LegalCaseManagementEngine
- `hold_ids` (tuple) → ENH-227 LegalHoldManagementEngine, idempotent linking via `link_to_hold()`
- `contract_review_id` → ENH-221 (META_ONLY since ENH-221 itself is META_ONLY)

The engine stores references; resolution is the cockpit/dashboard's job.

### E-discovery scoping

`create_discovery_request()` requires at least one scope filter (matter_id, hold_id, or date range). Engine snapshots matched docs at request time. Engine answers "which docs match" but does NOT generate the export bundle — packaging + redaction is operator-side.

### Confidentiality classifications

PUBLIC / INTERNAL / CONFIDENTIAL / **PRIVILEGED** (attorney-client / work product). Engine tags but does NOT enforce — access control lives at the cockpit via `require_access()`.

## Honest deferrals (named in board_summary)

- **ACTUAL_BLOB_STORAGE** — filesystem/S3 operator-side
- **VERSION_CONTROL_BINARY_DIFF** — engine tracks scalar `version_no` only
- **AUTOMATED_RETENTION_PURGE** — engine flags eligibility, operator decides
- **FULL_TEXT_SEARCH_INDEX** — needs OCR + index infrastructure
- **E_DISCOVERY_BUNDLE_EXPORT** — packaging operator-side
- **ACCESS_CONTROL_ENFORCEMENT** — META_ONLY (cockpit-side)
- **ENH-221 CONTRACT_REVIEW LINKAGE** — META_ONLY

## Tests — 34 across 11 classes

- TestModuleShape (7) — 6 enums + dataclass exports + counts
- TestRegistry (1) — ENH-229 active
- TestHubIntegration (1) — Tier 31 entry
- TestRegisterDocument (4) — DRAFT default, INDEFINITE no-purge-date, dup ID, empty title
- TestLifecycle (4) — full path, reverse-loop reason, retention gate, invalid jump
- TestVersionBump (2) — DRAFT-only invariant
- TestQueries (3) — by matter, by kind, privileged
- TestHoldLinkage (2) — idempotent + reverse query
- TestDiscovery (4) — scope match, empty-scope reject, lifecycle, early-close reason
- TestHonestDeferrals (1) — all 7 deferral surfaces named
- TestPortfolioSummary (2) — engine name + breakdowns
- TestNoRegression (3) — KYC engine + ENH-228 + ENH-227 untouched

## Apply order

1. `utils/legal_document_management.py` → `utils/`
2. `utils/standards_registry.py` (ENH-229 activation)
3. `pages/7_admin.py` (Tier 31 hub entry)
4. `tests/test_legal_document_management_v10_177.py` → `tests/`
5. `CHANGELOG_v10.177.md` → root

`python scripts/audit.py` reports `Score: 153/153 gates = 100.0% — PASS`.

## Next

**v10.178 ENH-230 Legal Analytics & Reporting** — analytics on matter outcomes, settlement trends, regulatory enforcement patterns, opposing counsel patterns. Cross-engine analytics rollup. After that: **v10.179 LEGAL MODULE CLOSURE CEREMONY** — G154 (`legal_module_closed`) + G155 (`legal_arc_ui_integrated`) audit gates locking the 9-standard arc, mirroring the AML/Compliance closure pattern (v10.169).
