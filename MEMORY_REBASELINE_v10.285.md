# Memory rebaseline — v10.285

This file is the canonical "userMemories block" payload to copy into
the operator's memory at the start of Phase 2B. It supersedes the
running summary in conversation context which had drifted by v10.282.

---

## Work context

Joshua Mokua works as a business analyst at a bank in Kenya, with
responsibilities spanning productivity analysis, business cases,
industry analysis, ad hoc reporting, and quarterly performance
reporting. He is also the builder of A2Z MIS 360, a world-class
bank-wide Management Intelligence Platform targeting Ecobank Kenya
(Oracle FLEXCUBE v12) as the active client. The platform is built on
Python, Streamlit, PostgreSQL, and FastAPI with FLEXCUBE integration.

## Personal context

Joshua is based in Kenya and has entrepreneurial interests beyond
banking, including Golden Field Farm (a large-scale tomato, onion, and
livestock operation) and a planned grocery business targeting financial
independence. He has a young child being introduced to computer
lessons.

## Top of mind (as of Phase 2A close, v10.285)

A2Z MIS 360 is in steady-state Phase 2A close-out. 308 of 330
standards active. 177 audit gates all green. 104 cockpit pages live.
Phase 2A delivered 16 cluster closures plus the SWIFT lone-standard
hardening (v10.283) plus a runtime hotfix (v10.284) that introduced
G177 import-integrity gate and closed the fictitious-module bug class.

Phase 2A retrospective is shipped (v10.285); Phase 2B is queued.

22 standards still planned: CIMS arc (15, #166–#180), Analytics Hub
extensions (5, #286–#290), Trade Finance Mobile (1, #279), Compliance
Dashboard (1, #200). Phase 2B suggested batching: v10.286 (Analytics
Workbench + Scheduled Reports), v10.287 (NLQ + Anomaly + Export),
v10.288 (Compliance Dashboard lone), v10.289 (Trade Finance Mobile
lone), v10.290–v10.293 (CIMS arc, 4 batches), interspersed with
backfill batches for credit, treasury, trade-finance pt2, and
resource optimisation arcs.

Other deferred items: PG migration (19/52 tables), API endpoints
(22/136), test coverage (~45%), FATCA/CRS XML, 3/8 CBK reports
(NSFR drill-down, FX risk by counterparty, consolidated supervisory
schedule), React SPA (#37), React Native (#38).

Ecobank engagement support: v10.284 QA Map document
(`a2z_v10.284_qa_map_ecobank.docx`) is the canonical Q&A reference
for the panel discussion.

## Brief history

### Phase 2A (v10.270 → v10.285, ~6 weeks)

16 cluster closures: SLA Tracker (#379–#388, v10.271), Specialized
Segments (#359–#368, v10.272), Partnerships (#369–#378, v10.273),
Bancassurance (#301–#310, v10.274), Customer Behavioural pt1
(#337–#345, v10.275 — introduced 7 utility modules including
interaction_capture), Customer Behavioural pt2 (#346–#348, v10.276),
Propositions (#349–#358, v10.277), Competitor Intel (#327–#336,
v10.278), Campaigns Management (#389–#398, v10.279), Command Centre
(#311–#320, v10.280), IT/Digital pt1 (#291–#295, v10.281), IT/Digital
pt2 (#296–#300, v10.282).

Plus SWIFT lone-standard hardening (#272 cockpit + G176, v10.283),
Ecobank QA Map (v10.284), runtime hotfix (v10.284), retrospective
(v10.285).

### Phase 1 and earlier

All 468 standards in scope completed at code level; 308 active in
runtime. Standards #14–#20 (Peer Learning through Amplification API)
locked at v10.46 under audit gates G25–G31. Phase 1D Integration
Layer closed (G143 at 75.6% STRICT-READY). Foundational standards
include Dormancy Intelligence (#41), EDMS Intelligence (#42),
CRM/Credit/Products/Strategy/Resource Optimization/CIMS/RMS/CMS/Audit/
Risk/Legal/Treasury/Revenue Assurance/Finance/Credit Governance/Trade
Finance/Analytics Hub/IT & Digital/Bancassurance/Command Centre/
Operating Leverage/Competitor Intel/Customer Behavioural Intelligence/
Propositions/Specialized Segments/Partnerships/SLA Tracker/Campaigns
Management/Data Protection & Consent/Target Cascade Enhancement/Cards/
Retailer Financing/Value Chain/Deal Room/VDR.

## Long-term background

Enterprise-grade, automation-first system design with strong BSC
linkage across all modules. Golden Field Farm represents a parallel
entrepreneurial track. The A2Z MIS 360 vision — a fully integrated,
CBK-compliant bank-wide intelligence platform — has been the
consistent north star.

---

## Operating rules (CANONICAL — never deviate)

### Canonical imports

```python
from utils.core_audit import audit_log
from pages._access import require_access
```

There is **no** `utils.audit_log`, **no** `utils.access_helpers`.
G177 enforces.

### audit_log signature

```python
audit_log(
    action="register_X",
    username=actor,           # NOT "actor"
    detail="optional context",
    module="page_module_key",
)
```

Never use `actor=`, `target=`, `entity=`, `outcome=`, `metadata=`.

### require_access argument

Pass the manifest's `module_path` verbatim, e.g.:

```python
require_access("shared.command_centre")
require_access("it_platform.it_digital_pt1")
require_access("trade_finance.swift_cockpit")
```

Match must be exact against `pages/_manifest.json`.

### Manifest entry required fields

Every page entry in `pages/_manifest.json` must declare all of:

- `department_primary`
- `module_path`
- `secondary_visibility` (list)
- `title`
- `icon`
- `current_module_key`
- `description`

G160 enforces.

### Cluster batch protocol

Every cluster ships in one zip:

1. One utility engine per standard in `utils/`
2. One cockpit page in `pages/` (G4-compliant ≤7 tabs, audit_log on
   every write surface)
3. One closing audit gate (locks every enum byte-for-byte)
4. Standards flipped active in `utils/standards_registry.py`
5. Tier registered in `pages/7_admin.py`
6. Manifest entry with all 7 required fields
7. Audit run before and after; G162 rebase if regulatory tokens moved
8. Changelog
9. Zip stage to `/mnt/user-data/outputs/`

### Cockpit tab budget

≤7 tabs hard limit (G4). For 5+ standards in a cluster, plan tab
layout BEFORE writing the page. Default pattern: one tab per major
capability, with related state-transition forms folded into expanders
inside their primary register tabs.

### Legacy-data tolerance

Every list/iterate over engine output must filter records that don't
match the expected shape. Surface a banner reporting how many legacy
records were skipped. Never hard-key `c["x"]` on engine output without
a guard.

### Gate-ID counter

Linear, never reuse. Before adding a new gate, grep for the highest
existing G-number and increment exactly.

### G162 rebase pattern

1. Run `gate_tenant_identity_hardcoding` to get authoritative per-token
   deltas.
2. Update `data/audit_baselines.json` `g162_tenant_hardcoding`:
   per_token (replacement, not delta), total, established_in.
3. Append scope_history entry: version, date, from_total, to_total,
   delta, rationale, tokens_changed.

### Memory cadence

Update userMemories at every cluster closure, not at end-of-phase.

---

## Other instructions (preserved from prior memory)

- Use `fast #X` mode for implementing standards — code only, no
  explanatory prose unless asked.
- Never combine multiple standards into one ZIP file; deliver one
  standard per ZIP for engine drops, cluster batches consolidated.
- Include `audit_log()` after every write operation.
- All API endpoints must have JWT auth (`Depends(get_current_user)`).
- Batch imports at the top of each file.
- Return only changed files — not full repository dumps.
- Never self-grade; quote the audit script's score only.
- Always run `python scripts/audit.py` before and after changes.
- Never add module-specific config tabs to `7_admin.py`; use the
  registry pattern.
- Never write directly to `performance.*` tables; use the central
  BSC integration engine.
- Prefer extending existing patterns over inventing new ones.
- Avoid patronizing or sycophantic language; provide critical analysis
  where needed.
- Push back against harmful or incorrect ideas; keep Joshua grounded
  in rational thought.
- Avoid clipped, list-heavy responses; prefer short paragraphs with
  varied sentence structure.
- Do not use phrases like "let's pause," "let's take a breath," or
  "let's take a step back."
- Use writing blocks only for emails, chat messages, or social posts.
- Ask follow-up questions only when appropriate; avoid repeating the
  same emoji.
