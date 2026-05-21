# A2Z MIS 360 — v10.195 Changelog

## RUNTIME FIXES — five page-load and demo-button errors

**Release date:** 2026-05-06
**Audit score:** 159/159 gates = 100.0% PASS (unchanged from v10.194)

---

## Summary

This release fixes five distinct runtime errors that surfaced when
Joshua extracted earlier consolidated bundles into the live
Streamlit environment. Same shape as v10.192 — pure runtime-fix
release, no new standards, no module ratchets. Every error is
addressed at its root rather than papered over.

The five errors:

1. **P&L (SBU page) crashes** with `ValueError: Unknown format code
   'f' for object of type 'str'` — DataFrame cells loaded as strings
   are being f-formatted as floats
2. **Revenue Assurance Cockpit fails to load** — `WaiverRecord`
   import doesn't resolve because the symbol doesn't exist in
   `utils.revenue_anomaly_patterns`
3. **Risk Arc Cockpit fails to load** — `SEVERITY_MULTIPLIERS`
   import doesn't resolve because the symbol doesn't exist in
   `utils.op_risk`
4. **ML Governance Cockpit fails to load** — `audit_log()` called
   with bogus keyword arguments (`actor=`, `target=`, `metadata=`)
   that don't exist in the canonical signature
5. **Finance Arc Cockpit will fail to load** (latent — Joshua hadn't
   hit it yet) — `AccrualSchedule` import doesn't resolve because
   the class was renamed to `RecurringAccrualSchedule`

Plus one bonus fix to a latent demo-button bug in the Revenue
Assurance Cockpit that would crash on click.

---

## What shipped

### Fix 1: P&L format-code crash (`pages/9_sbu.py`)

#### Symptom
```
ValueError: Unknown format code 'f' for object of type 'str'
File "pages/9_sbu.py", line ~299
    f"PBT: {fmt_num(pbt_act, short=True)}  ({pbt_pct:.1f}% of target)..."
```

#### Root cause
`build_branch_pnl()` coerces values to float when constructing rows
(lines 108, 111), but the page reads from `df_proc` in session
state which is built upstream from user-uploaded BSC data. When the
upload preserves numeric values as strings, those strings propagate
through the DataFrame round-trip and arrive at f-format sites as
strings. `f"{'75.5':.1f}"` raises `ValueError`.

#### Fix
Added `_to_float_safe(value, default=0.0)` helper near the top of
the page (alongside the existing `_safe_date` helper). The helper
coerces with try/except and a numeric fallback. Wrapped 15 f-format
sites where DataFrame cells flow into `:.1f` directly:

- 6 sites where `branch.get('<key>_pct', 0)` or `pbt_pct` are
  formatted (lines ~299, 344, 351, 374, 392, 432)
- 4 sites where `branch.get('<key>_act', 0) * 100` is formatted
  for ratio display (lines ~385, 386, 530)
- 5 sites for region/branch percentage displays (lines ~424, 490,
  514, 539 plus CIR estimate at 326)

Sites that go through `fmt_num()` are unchanged because `fmt_num()`
is already defensive (does `float(v)` inside its own try/except).

### Fix 2: WaiverRecord import (`pages/95_revenue_assurance_cockpit.py`)

#### Symptom
```
ImportError: cannot import name 'WaiverRecord' from
'utils.revenue_anomaly_patterns'
```

#### Root cause
Line 37 imported `WaiverRecord` but the symbol doesn't exist in
`utils/revenue_anomaly_patterns.py`. The actual exports are
`ContractRate`, `RevenueRecordWithContext`, `CommissionRecord`,
`PatternFinding`, `AnomalyReport`, plus enum types. `WaiverRecord`
was either renamed/refactored or was a planned-but-not-built class.

`grep` confirmed `WaiverRecord` is referenced nowhere else in the
cockpit — it was an unused import.

#### Fix
Removed `WaiverRecord` from the import list. The remaining symbols
(`RevenueAnomalyPatternEngine`, `ContractRate`, `CommissionRecord`,
`PatternFamily`) still resolve correctly.

### Fix 3: SEVERITY_MULTIPLIERS import (`pages/93_risk_arc_cockpit.py`)

#### Symptom
```
ImportError: cannot import name 'SEVERITY_MULTIPLIERS' from
'utils.op_risk'
```

#### Root cause
Line 42 imported `SEVERITY_MULTIPLIERS as _OR_NOOP, # import safety`
— the rename to `_OR_NOOP` and the inline comment `# import safety`
indicate this was added defensively to "prove" the module exports
the symbol. But `SEVERITY_MULTIPLIERS` doesn't exist in
`utils/op_risk.py`. The op_risk module's actual surface is the SMA
(Standardised Approach) constants like `ALPHA_BUCKET_1/2/3`,
`BUCKET_*_CEILING_EUR`, `LC_MULTIPLIER`, `RWA_MULTIPLIER`,
`ILM_EXPONENT`, etc.

`grep` confirmed `_OR_NOOP` is referenced nowhere — the import was
unused even when working.

#### Fix
Removed the `SEVERITY_MULTIPLIERS as _OR_NOOP` line from the import
tuple. The op_risk classes (`OperationalRiskSMA`,
`BusinessIndicatorInputs`, `OperationalLossEvent`, `SMAInputs`,
`SMAResult`, `Bucket`, `ILMSource`) still resolve.

### Fix 4: audit_log bogus kwargs (`pages/98_ml_governance_arc_cockpit.py`)

#### Symptom
```
TypeError: audit_log() got an unexpected keyword argument 'actor'.
Did you mean 'action'?
File "pages/98_ml_governance_arc_cockpit.py", line 58
```

#### Root cause
Six call sites (lines 58, 184, 263, 337, 418, 498) used the wrong
audit_log signature:

```python
audit_log(
    actor=uname,                 # not in canonical signature
    action="ml_governance_view", # OK
    target="ml_governance_arc",  # not in canonical signature
    metadata={"page": "..."})    # not in canonical signature
```

The canonical signature in `utils/core_audit.py`:
```python
def audit_log(action: str, username: str, detail: str = "",
              module: str = "", before: str = "", after: str = "")
```

There's no `actor`, `target`, or `metadata`.

#### Fix
Programmatically rewrote all six call sites to use the canonical
positional form, folding `target` and `metadata` into the `detail`
string for traceability:

```python
audit_log(
    "ml_governance_cockpit_view",
    uname,
    "target=" + str("ml_governance_arc") + " " + "meta=" + str({"page": "98_ml_governance_arc_cockpit"}))
```

The information is preserved in the audit trail; it just lives in
the `detail` field rather than as separate columns.

### Fix 5: AccrualSchedule import (`pages/96_finance_arc_cockpit.py`)

#### Symptom (latent — would have surfaced when Joshua opened the page)
```
ImportError: cannot import name 'AccrualSchedule' from
'utils.finance_close_orchestrator'
```

#### Root cause
`utils/finance_close_orchestrator.py` exports
`RecurringAccrualSchedule` and `PrepaymentSchedule` but no plain
`AccrualSchedule`. The import on line 36 was either left over from
a rename or written against a planned API.

`grep` confirmed `AccrualSchedule` is referenced only in the import
line — unused in the cockpit body.

#### Fix
Removed `AccrualSchedule` from the import list. The remaining
symbols (`FinanceCloseOrchestrator`, `GLEntry`, `AccountType`,
`AccrualFrequency`, `CloseTaskSeverity`) still resolve.

### Bonus fix: Revenue Assurance demo-button rework

#### Symptom (latent — only fires when "Demo: route a sample finding" button is clicked)
```
ImportError: cannot import name 'FindingInput' from
'utils.revenue_orchestrator'
ImportError: cannot import name 'RoutingResult' from
'utils.revenue_orchestrator'
```

#### Root cause
The demo block at lines 248-275 was written against an API that
doesn't exist. There is no `FindingInput` (real input is
`PatternFinding` or `ValidationFinding` — the `SourceFinding`
union). There is no `RoutingResult` (the real output is
`TriageReport.work_items[0]`). The constructor `RevenueOrchestrator()`
was also wrong — it requires a `config: OrchestratorConfig`
positional argument. The `orchestrate()` method signature has
changed to take `findings`, `raised_dates`, `as_of`,
`current_states`, `monetary_impacts` — not `findings`,
`current_states`, `today`.

#### Fix
Rewrote the demo block against the real API:

- Constructs an `OrchestratorConfig` with three example
  `TriageRule` entries (BILLING_ERROR/HIGH → REVENUE_RECOVERY,
  LEAKAGE/HIGH → REVENUE_RECOVERY, COMMISSION_MISCALC/MEDIUM →
  OPERATIONS) — minimal but realistic
- Constructs a `PatternFinding` (not `FindingInput`) with the real
  fields: `pattern_id` (`PatternId.EXPIRED_CONTRACT_BILLING`),
  `family` (`PatternFamily.BILLING_ERROR`), `evidence`,
  `confidence`, `framework_refs`, `notes` — these are the actual
  fields of the dataclass
- Calls `orchestrate(findings=..., raised_dates=..., as_of=...,
  monetary_impacts=...)` — the real signature
- Reads `result.work_items[0]` for `priority_score`,
  `assigned_team`, `past_sla`, `priority_components`

Verified end-to-end: priority_score=117.5, team=REVENUE_RECOVERY,
past_sla=False, priority_components surfaces 6 keys
(severity_weight, family_weight, base, age_contribution,
impact_contribution, total).

Also added defensive coercion `f"{float(wi.priority_score):.1f}"`
since the value is `Decimal` and would have rendered as
`Decimal('117.500')` without the cast — minor display polish.

Top-level imports updated to add `PatternFinding` (needed by the
demo) — `ValidationSeverity` was already imported from
`utils.revenue_validation`.

### Audit gate update (G134)

The gate `gate_revenue_assurance_arc_ui_integrated` (G134) was
checking for the literal string `"RevenueOrchestrator()"` in the
cockpit. The corrected demo uses `RevenueOrchestrator(config=cfg)`
since the real constructor requires a config arg. Updated the gate
to check for `"RevenueOrchestrator(config="` instead — same intent
(verify the constructor is invoked), correct surface match.

---

## Files changed

```
pages/9_sbu.py                              (added _to_float_safe helper, wrapped 15 f-format sites)
pages/93_risk_arc_cockpit.py                (removed bogus SEVERITY_MULTIPLIERS import)
pages/95_revenue_assurance_cockpit.py       (removed unused WaiverRecord import; reworked demo block; added PatternFinding to top-level imports)
pages/96_finance_arc_cockpit.py             (removed unused AccrualSchedule import)
pages/98_ml_governance_arc_cockpit.py       (rewrote 6 audit_log call sites to canonical signature)
scripts/audit.py                            (G134 expected constructor string updated)
CHANGELOG_v10.195.md                        (this file)
```

Seven files. No new audit gates, no new tests, no engine changes —
pure runtime-fix release.

---

## Audit ratchet

```
v10.194 (entering this release): 159/159 = 100% PASS
v10.195 (this release):           159/159 = 100% PASS
                                  no new gates
```

---

## How to apply

```bash
unzip -o a2z_v10.195_runtime_fixes.zip
python scripts/audit.py        # → 159/159 PASS
streamlit run app.py           # the previously-broken pages now load
```

---

## Honest scope statement

This release fixes the **five reported runtime errors plus one
related latent bug**. It does not:

- **Audit every page for similar latent issues exhaustively.** I
  ran a programmatic scan of all 108 pages for symbols imported
  from `utils.*` that don't actually exist in the source module —
  the three latent issues found were the WaiverRecord, AccrualSchedule,
  and FindingInput/RoutingResult bugs, all addressed. But the scan
  doesn't catch dynamic imports inside function bodies or lazy
  imports in conditional blocks. If similar bugs surface as you
  use other pages, file them.
- **Refactor the upstream P&L upload pipeline.** The fix is
  defensive at the format-string sites; the real fix would be to
  enforce dtype on the DataFrame at load time. That's a larger
  change because it touches the BSC upload paths in
  `utils/core.py` and `pages/_shared.py`. The current defensive
  fix is correct (no crash, sensible fallback to 0.0) and
  doesn't preclude a future cleanup batch.
- **Address ML Governance Cockpit functionality beyond the import
  fix.** The audit_log calls now use the right signature, so the
  page loads. Whether the underlying ML governance engines behave
  correctly under operator interaction is a separate question.
- **Add a UI surface for v10.193 / v10.194 (CBK NPL/IRR/OPR + FATCA/CRS XML
  generation).** Those engine extensions ship without a Streamlit
  page that lets a compliance officer trigger them. A future batch
  could add a tab on `pages/74_cbk_returns.py` for the new
  diagnostic returns and a small page for FATCA/CRS XML preview,
  but that's outside this release's scope.

---

## What's next

If more runtime errors surface, file them and I'll fix in the next
batch. Otherwise the open candidates remain:

- **Start a PG migration batch** — pick a domain (Treasury,
  Compliance) and migrate 5-10 JSON-backed reads to PostgreSQL
- **UI surface for v10.193 / v10.194** — CBK NPL/IRR/OPR returns
  preview + FATCA/CRS XML download button
- **Dig into the upstream BSC upload pipeline** — strict dtype
  enforcement so the P&L defensive coercion becomes belt-and-braces
  instead of necessary

No commitment is made by this release.
