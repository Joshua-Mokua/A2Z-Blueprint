# A2Z MIS 360 — CHANGELOG v8.11

**v8.11 Living Documentation System planning doc — pure documentation batch, sets up v8.12-v8.14 sequence**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **37th consecutive clean**
**Strategic milestone:** **🎯 LIVING DOCUMENTATION SUB-CAMPAIGN PLANNED.** v8.11 ships the canonical plan; v8.12 → v8.14 (plus optional v8.15) ships the implementation. The campaign that built the platform now plans the discipline that documents it.

---

## What this batch is

**Pure documentation batch.** Zero code changes. Zero audit gate changes. Zero stock/loop/composite/UI changes.

**One thing shipped**: `docs/A2Z_LIVING_DOCS_PLAN.md` — a 588-line canonical plan for the next sub-campaign — a sales-grade rendering layer that produces PowerPoint brochures, PDF magazines, and security/compliance whitepapers directly from the tier 1-5 registries the v7.x and v8.x campaigns built.

This is the third planning-doc batch slot in the campaign — following the v7.0 charter (288 lines, opened the v7.x build campaign) and the v7.16 + v8.6 retrospectives (282 + 364 lines, closed the v7.x and v8.x main tracks). The convention is now established: significant sub-campaigns get a planning batch BEFORE the build batches.

---

## What changed

### `docs/A2Z_LIVING_DOCS_PLAN.md` — new 588-line plan

10 parts plus foreword and closing:

| Part | Title | Length | Purpose |
|---|---|---|---|
| Foreword | Why this matters for A2Z specifically | ~50 lines | Frames the doc as discipline, not marketing |
| Part 0 | Architectural Mapping | ~50 lines | Where Tier 6 (sales rendering) fits atop existing tiers 1-5 |
| Part 1 | Source of Truth (already built) | ~80 lines | 13 existing files the system reads from + 6 new sales-content JSONs needed |
| Part 2 | The Generation Engine | ~80 lines | 3 generators + shared rendering core + claim validator |
| Part 3 | The Generation Discipline | ~70 lines | 6 rules: no invented numbers, marked roadmap items, mandatory honest-scope, registry citations, canonical references, build-time honesty |
| Part 4 | The Outputs (Tier 6) | ~80 lines | 4 artifacts: Brochure (15 slides) + Magazine (~100 pages) + Security Whitepaper + Compliance Pack |
| Part 5 | Module Spread Template | ~50 lines | Enriched with Verification + Honest Scope panels |
| Part 6 | The Reconciled Numbers | ~50 lines | Single ground-truth table |
| Part 7 | Implementation Plan | ~80 lines | 4 batch sequence: v8.12 → v8.13 → v8.14 → optional v8.15 |
| Part 8 | Audit Perimeter Extension | ~30 lines | Proposed G110 makes 6-gate perimeter into 7 |
| Part 9 | Spirit Statements | ~40 lines | 10 principles including the meta-discipline |
| Part 10 | References | ~30 lines | Canonical Meadows + Evans + Nygard + Newman + CBK + IFRS + Basel + internal canon |

### Reconciled numbers (Part 6)

The original product-strategy draft cited "100+ modules" / "468 standards" — these did not match the registry. The plan's Part 6 is now the canonical ground-truth table:

| Metric | Value as of v8.10 | Source |
|---|---|---|
| Standards delivered | **116** | engine_registry |
| Standards in UI | **62** | page-level audit |
| Audit gates | **109** | scripts/audit.py |
| Defense-in-depth perimeter gates | **6** (G104-G109) | scripts/audit.py |
| System stocks | **6** | utils/system_stocks.py |
| Stocks WIRED | **6 / 6 (100%)** | utils/system_stocks.py |
| Feedback loops | **15** | utils/system_flows.py |
| Loops WIRED | **15 / 15 (100%)** | utils/system_flows.py |
| KPI library entries | **35** across 4 BSC pillars | data/kpi_library.json |
| Branches in simulation | **35** | data/staff_register.xlsx |
| Staff in simulation | **487** | data/staff_register.xlsx |
| Customers in CBS sim | **700,000** | cbs_data/customers.json |
| Consecutive clean-first-try | **36** at v8.10 (37 at v8.11) | scripts/audit.py + commit history |

Future batches that change registry counts must update Part 6 — same convention as charter §13.

### The audit-locked claims pattern

The campaign-defining idea: every numeric claim in rendered collateral must trace to a registry path. Build aborts if claim diverges from reality.

```python
class Claim:
    text: str
    numeric_value: any
    registry_path: str
    source_file: str

def validate(claim, registry_dict) -> bool:
    actual = _resolve_path(registry_dict, claim.registry_path)
    return actual == claim.numeric_value
```

**If validation fails, generation aborts.** Sales gets "Brochure.pptx claims X but registry says Y; rebuild after reconciling." Proposed G110 audit gate (v8.15) makes this a permanent invariant.

### The Honest Scope discipline

Every spread, slide deck, and whitepaper ends with a section titled "What this document does not claim." Mandatory. Never edited out.

This mirrors:
- The 12-item "Honest acknowledgements" section at the end of every CHANGELOG
- The "What v7.x didn't ship" / "What v8.x didn't ship" sections in the two retrospectives
- The 12 v8.6 retrospective acknowledgements being systematically burned down across v8.7-v8.10

### Roadmap markers

Three explicit visual markers in all rendered collateral:

| Marker | Meaning |
|---|---|
| ✅ Shipped | In the codebase, audit-verified, version-stamped |
| 🟡 Designed | In the charter; engine specified; not yet wired |
| ⏳ Roadmap | Not yet designed; planned for future |

Original draft conflated all three. The plan requires the distinction.

### Implementation as canonical 2-batch + UI surface sequence (Part 7)

| Batch | Type | Deliverables |
|---|---|---|
| **v8.12** | Engine | registry loader (~300 lines) + claim validator (~150 lines) + 6 sales-content JSON files |
| **v8.13** | Engine | 3 generators (PPT 400 + Magazine 600 + Whitepaper 250 lines) + shared rendering core |
| **v8.14** | UI surface | admin/systems-view section with 4 generate-buttons + status panel + audit-claim diff view |
| v8.15 (optional) | Audit | G110 gate 'collateral claims traceable to registries' (109 → 110 gates) |

Mirrors how v7.12/v7.13 closed L05 cards and v8.4/v8.5 closed L14 streaming.

---

## End-to-end smoke test (all green)

```
=== Planning doc ===
  ✓ docs/A2Z_LIVING_DOCS_PLAN.md (588 lines)
  ✓ Markdown well-formed (headers + tables + ASCII diagrams + prose)
  ✓ Cross-references valid (charter 288 lines + v7 retrospective 282 lines + v8 retrospective 364 lines)

=== Reconciled numbers cross-checked ===
  ✓ system_stocks.py shows 6 stocks
  ✓ system_flows.py shows 15 loops, all WIRED
  ✓ scripts/audit.py shows 109 gates
  ✓ data/kpi_library.json shows 35 KPIs
  ✓ 32 CHANGELOGs in repo root
  ✓ 36 consecutive clean v5.96 → v8.10 confirmed

=== FULL AUDIT ===
  Score: 109/109 gates = 100.0% — PASS
```

---

## ✅ Thirty-seventh consecutive clean-first-try

37 batches in a row landing clean — v5.96 → v8.11.

---

## Comparison vs v8.10

| | v8.10 | v8.11 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Standards in UI | 62 | 62 (unchanged) |
| **Documentation tiers** | **3** (CHANGELOGs + charter + 2 retrospectives) | **4** (+ Living Doc plan) ⭐ |
| **Sub-campaigns planned** | **0** | **1** (Living Doc, v8.12-v8.15) ⭐ |
| Clean-first-try streak | 36 | **37** |

---

## Strategic narrative — the planning-doc batch pattern

| Batch | Doc | Lines | Role |
|---|---|---|---|
| v7.0 | A2Z_SYSTEMS_CHARTER.md | 288 | Opened v7.x build campaign |
| v7.16 | A2Z_V7_RETROSPECTIVE.md | 282 | Closed v7.x build campaign |
| v8.6 | A2Z_V8_RETROSPECTIVE.md | 364 | Closed v8.x main track |
| **v8.11** | **A2Z_LIVING_DOCS_PLAN.md** | **588** | **Opens Living Doc sub-campaign** ⭐ |

The convention is now explicit: significant sub-campaigns get a planning batch BEFORE the build batches. This:
- Forces the architecture to be specified before code is written
- Provides a stable reference future engineers can review without reading code
- Lets the 12 honest acknowledgements pattern propagate into planning artifacts
- Makes the campaign's design discipline as visible as its build discipline

The Living Documentation System is the next horizon — once shipped (v8.14), every batch will trigger automatic regeneration of audit-locked sales collateral. **Sales claims will fail the build if they diverge from registry truth. The same `scripts/audit.py` that proves engineering integrity will prove marketing accuracy.**

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — pure documentation batch; nothing to deploy.
2. **The plan is opinionated** — claims like 'Build the thing that fails the build when it lies' represent a cultural commitment future engineers may diverge from with reason.
3. **The 6 sales-content JSON files are not yet built** — gap_analysis, security_architecture, integrations_roadmap, case_studies, pricing_models, competitive_positioning are listed as v8.12 deliverables.
4. **The plan assumes WeasyPrint + python-pptx work in production** — v8.13 batch will need to verify with the campaign's standard self_test() pattern.
5. **G110 is proposed not shipped** — Part 8 describes the audit gate but it ships in v8.15 as the optional hardening batch.
6. **The reconciled numbers in Part 6 are accurate as of v8.10** — future batches that change registry counts need a corresponding update to Part 6.
7. **Reference customer commitments are not yet signed** — the plan says 'Bank logos appear only with signed reference agreements'; A2Z does not have signed reference agreements at v8.11 ship time.
8. **External case studies are cited research, not A2Z deployments** — Zanifu / C2FO / National Capital Bank from the original draft are placed in 'cited industry research' sections.
9. **The rendered outputs are not yet generated** — the plan describes 4 artifacts; v8.13 ships the generators; actual artifacts get rendered in v8.14 (or a v8.16 'first generation' batch).
10. **The plan inherits the campaign's 12-acknowledgements convention** — Part 9 and Part 7 include scope acknowledgements directly; honesty discipline propagates.
11. **No new audit gate in v8.11** — planning batch only; G110 is a v8.15 candidate.
12. **The 37-batch clean streak now includes a planning-doc batch** alongside engine batches, audit-hardening batches, infrastructure batches, retrospectives, and tactical-hardening batches.

---

## Next batch options

The v8.12 build sequence is now well-defined; ranked by canonical order:

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.12 Build registry loader + claim validator + 6 sales-content JSON files** | Phase 1 of Living Doc sub-campaign per Part 7 |
| (2) | v8.13 Build three generators (PPT + Magazine + Whitepaper) | Phase 2; produces rendered artifacts |
| (3) | v8.14 Surface docgen on admin/systems-view | Phase 3; completes 2-batch + UI surface sequence |
| (4) | v8.15 (optional) Add G110 audit gate | Final hardening; 109 → 110 gates |
| (5) | Diverge to a v8.6 retrospective ack | Interrupts Living Doc sub-campaign; not recommended |

**Strong recommendation: v8.12 = Build registry loader + claim validator + 6 sales-content JSON files** — the canonical Phase 1 per Part 7 of the plan; ~450 lines including loader (300) + validator (150) + 6 JSON content files; sets up v8.13's rendering layer; 38th-clean candidate.

The Living Doc sub-campaign now has 4 ordered batches (v8.12 + v8.13 + v8.14 + v8.15) ready to ship in sequence.

---

🎯 **Living Documentation sub-campaign planned — 588 lines establishing the canonical 4-batch build sequence (v8.12 → v8.15).**

⭐ **37th consecutive clean-first-try. The campaign that built the platform now plans the discipline that documents it.**
