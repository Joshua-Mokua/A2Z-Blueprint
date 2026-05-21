# CHANGELOG v10.52 — revenue_assurance arc · ENH-243 Revenue Agentic Orchestrator

**Status:** revenue_assurance arc 3/8+1 batches (5 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (317 modules · 793 imports · 3 HARD baseline)
**Active standards:** 121 → **122** / 260 · **Scenario library:** 62 → **66** (4 ORC-* added)

## What this batch does

Composes the two upstream engines (ENH-241 data integrity + ENH-242
pattern detection) into a single `WorkItem` stream with deterministic
priority + routing + SLA aging. Where the standard's name says
"Agentic Orchestrator" and the description says "auto-prioritises +
auto-assigns + tracks remediation", the implementation rewrites
those verbs to fit Rule 7: the engine **computes** priority
deterministically, **computes** the team that should investigate,
**computes** SLA state — but never tracks state internally, never
auto-transitions, never sends notifications. Caller workflow owns
all side-effects.

## New module

- `utils/revenue_orchestrator.py` (~750 lines · 23 self-tests) —
  stateless composition + prioritisation + routing engine. Pure
  stdlib. Single public engine `RevenueOrchestrator` exposing
  `orchestrate(findings, raised_dates, as_of, current_states,
  monetary_impacts) → TriageReport`.

## Architecture

### Heterogeneous input → unified output
- Type alias `SourceFinding = Union[ValidationFinding, PatternFinding]`
- `_extract_family` and `_extract_record_ids` handle the shape
  difference internally — `ValidationFinding.category.value` and
  `PatternFinding.family.value` both feed the same routing table
- Output is uniformly `Tuple[WorkItem, ...]`; downstream consumes
  one shape regardless of upstream

### Six investigator teams
`InvestigatorTeam` enum — `REVENUE_RECOVERY`, `OPERATIONS`,
`COMPLIANCE`, `HR_PAYROLL`, `DATA_QUALITY`, `FINANCE`. Maps to the
bank's actual org structure in the caller's translation layer.

### Six-state lifecycle
`WorkItemState` enum — `RAISED`, `ACKNOWLEDGED`, `IN_PROGRESS`,
`RESOLVED`, `DISMISSED`, `ESCALATED`. The engine reads these from
the caller's state map but never writes them; ORC-04 scenario
verifies the engine doesn't memoise state across calls.

### Deterministic priority

Score = `(severity_weight × family_weight) + age_contribution + impact_contribution`

| Component | Source | Default |
| --------- | ------ | ------- |
| severity_weight | `SEVERITY_WEIGHTS` map | CRITICAL=100, HIGH=50, MEDIUM=20, LOW=5, INFO=1 |
| family_weight | `FAMILY_WEIGHTS` map | LEAKAGE=1.5, RECONCILIATION=1.4, BILLING_ERROR=1.3, RATE_CARD_BREACH=1.2, COMPLETENESS=1.1, COMMISSION_MISCALC=1.0, ANOMALY=1.0, SCHEMA=0.9 |
| age_contribution | `age_decay_per_day × age_days` | 0.5/day default |
| impact_contribution | `impact_weight × monetary_impact_kes` | 0.0001/KES default (so KES 100m → 10,000) |

All five components surfaced separately in `priority_components`
dict per Rule 1 transparency.

### Routing
First-match against a `Tuple[TriageRule, ...]` configured at
construction. Each rule pairs `(family_or_category, severity)` to
a team and SLA in days. No match → `default_team` +
`default_sla_days`.

### SLA
`sla_deadline = raised_date + timedelta(days=sla_days)`. `past_sla`
is just `as_of > sla_deadline`. The engine flags it; caller
workflow decides whether to escalate.

## Honest design decision flagged in tests

A self-test (`_test_large_monetary_impact_can_outrank_higher_severity`)
explicitly documents that with the default `impact_weight=0.0001`,
a confirmed KES 100m revenue leakage at MEDIUM severity legitimately
outranks a CRITICAL schema corruption with no quantified impact —
the impact contribution (10,000) dominates the severity × family
base. This is intentional: in revenue assurance, a quantified large
loss IS more urgent than an unquantified data-quality issue. Callers
who want strict severity dominance lower `impact_weight` in the
`OrchestratorConfig`.

The first version of this test had a confounded premise (gave the
MEDIUM finding KES 1m impact and asserted CRITICAL still won). The
math said it didn't, and reflection said the math was right — fixed
the test rather than rigging the formula.

## Rule 1 / Rule 7 / Rule 6 alignment

- All 4 new dataclasses frozen: `TriageRule`, `OrchestratorConfig`,
  `WorkItem`, `TriageReport`.
- Every `WorkItem` surfaces full provenance: source IDs, type tag,
  severity, family/category, description, affected record IDs,
  raised date, age in days, SLA deadline, past_sla flag, assigned
  team, priority score, components dict, monetary impact, current
  state, framework refs.
- Engine is **stateless** — verified by ORC-04 scenario which calls
  orchestrate twice with same inputs, supplies state on first call,
  omits on second, and asserts the second call yields RAISED (not
  the memoised RESOLVED). Per Rule 7.
- Engine never:
  - mutates inputs (frozen dataclasses make this impossible)
  - persists anything to disk or DB
  - sends emails / Slack / API calls
  - auto-transitions state
  - auto-escalates past_sla items

## Validation envelope

- `TriageRule.__post_init__` rejects empty `family_or_category`
  and non-positive `sla_days`
- `OrchestratorConfig.__post_init__` rejects non-positive
  `default_sla_days`, negative `age_decay_per_day`, negative
  `impact_weight`
- Future-dated `raised_date` clipped to age=0 rather than raising
  (defensive — caller bug shouldn't crash batch)

## Standards registry

- **ENH-243** activated: `status: planned → active`,
  `implementation_batch: v10.40+ → v10.52`,
  `affected_engines: ("revenue_assurance",) → ("revenue_orchestrator",)`.
  Description rewritten to capture the stateless contract, the 6
  team / 6 state / 2 finding-type enums, the deterministic priority
  formula with all 5 components, the impact-can-outrank-severity
  design decision, the routing fallback semantics, and the Rule 1 /
  Rule 6 / Rule 7 alignment.
- Registry self-test PASS · total 260 · active **121 → 122**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **ORC-01 Cross-engine routing** — 1 ValidationFinding (SCHEMA
  CRITICAL) + 2 PatternFinding (LEAKAGE HIGH + RATE_CARD_BREACH
  HIGH) → routed to DATA_QUALITY + REVENUE_RECOVERY + COMPLIANCE
  respectively; FindingType tag preserved per Rule 1. 4 assertions.
- **ORC-02 Past-SLA flagging** — 2 LEAKAGE HIGH findings (7-day
  SLA): one 45 days old → past_sla=True; one 1 day old →
  past_sla=False; report past_sla_count=1. Engine flags but never
  auto-escalates per Rule 7. 4 assertions.
- **ORC-03 Priority sort order** — 4 findings spanning all four
  severity levels → sorted descending by priority_score; LOW is
  last; priority_components dict surfaces all 5 contributors. 4
  assertions.
- **ORC-04 Stateless verification** (Rule 7 cross-check) —
  orchestrate called twice on same finding; first call supplies
  RESOLVED state, second call omits state map. Second call must
  yield RAISED, not memoised RESOLVED. Routing remains
  deterministic. 3 assertions.

End-to-end runner: ORC-01..ORC-04 all PASS · **15/15 assertions**.
Scenario library 62 → **66**.

## Self-tests

- `python3 -m utils.revenue_orchestrator` → ✓ 23 tests covering
  validation envelope, cross-engine routing (validation via
  category, pattern via family), unmatched-fallback, age
  computation, future-date clipping, past-SLA flag, priority
  components surfaced, severity dominance at equal everything else,
  large-impact-can-outrank documentation, age lifts priority,
  impact lifts priority, state defaults to RAISED, state passes
  through when supplied, **stateless verification**, sort order
  descending, aggregates populated, work item provenance, empty
  findings yields empty report.
- `python3 -m utils.revenue_anomaly_patterns` → ✓ 21 tests (no regression).
- `python3 -m utils.revenue_validation` → ✓ 19 tests (no regression).
- `python3 -m utils.scenario_simulator` → ✓ 18 tests (no regression).
- `python3 -m utils.standards_registry` → ✓ self-test PASS.

## Gate verification

- `python3 scripts/audit.py` → **Score: 132/132 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (317 modules · 793 imports · 62 findings
  · HARD=3). Module +1 (revenue_orchestrator), imports +3 (3
  cross-engine imports from ENH-241 + ENH-242).

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-243) ✅
- ~750 line module (test count drove size — 23 tests across
  routing / priority / SLA / state semantics)
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure (per v10.46 amendment) ✅
- Audit + G128 + scenario library extension SHIPPED (non-negotiable) ✅
- Per Rule 1 every WorkItem surfaces full provenance + priority
  components dict ✅
- Per Rule 7 engine STATELESS — explicitly verified by ORC-04 ✅

## Files changed

- **NEW** `utils/revenue_orchestrator.py` (~750 lines, 23 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-243 activated, ~50 line
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 ORC-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.52.md`

## Honest scope notes

1. **No actual notifications, no actual workflow.** The engine
   produces WorkItem records. A production deployment would persist
   them to a case-management table, render in a Streamlit cockpit
   (closure batch), and trigger email/Slack from the workflow
   layer — none of which lives in this engine. Per Rule 7, that's
   the right boundary.

2. **Routing rules are caller-supplied.** The
   `_default_orchestrator_config` used in tests + scenarios is
   illustrative — production deployments craft a TriageRule tuple
   matching their actual org structure. The 7-rule default covers
   common cases but is not exhaustive (e.g., no rule for
   COMMISSION_MISCALC HIGH; falls through to OPERATIONS default).

3. **Priority components are weights, not money.** The
   priority_score is a relative ranking number, not a financial
   estimate. Two work items with priority_score=150 are roughly
   equal triage priority; the absolute value only matters for sort
   order.

4. **No "tracks remediation" feature.** The standard's third verb
   ("tracks remediation") is satisfied only in the read-state
   sense — the engine reads the caller's state map and surfaces it
   in the WorkItem. Production "remediation tracking" — durations
   in each state, state transition history, resolution notes —
   lives in the caller's case management, not here. Flagged
   honestly because the standard's wording is ambitious.

5. **Engine doesn't deduplicate findings across runs.** If a
   finding appears in two consecutive runs, the engine produces
   two WorkItems with the same `source_finding_id`. Caller
   workflow handles deduplication via the case-management DB —
   typically by treating `source_finding_id` as the primary key.

## Next batch — roadmap

- **v10.53** — ENH-244 Partner & Supplier Reconciliation: extends
  the cross-source reconciliation pattern from ENH-241 to
  multi-party settlements (partner revenue shares, supplier
  payments, agency commissions to outside firms). Likely composes
  with ENH-241's `CrossSourceTotal` rather than redefining.
- **v10.54..v10.57** — ENH-245..ENH-248 sequentially. ENH-245 is
  "Revenue Assurance Dashboard" — likely collapses into the v10.58
  closure cockpit per the v10.46 amendment (don't ship a
  freestanding dashboard standard plus a closure cockpit; consolidate).
- **v10.58** — revenue_assurance arc closure under v10.46 protocol:
  G133 ratchet + G134 UI ratchet + Tier 26 + Master Prompt +
  `pages/95_revenue_assurance_cockpit.py` wiring all six engines.

**134 consecutive clean batches.** 11 closed arcs holding;
revenue_assurance arc at 3/8 + closure pending.
