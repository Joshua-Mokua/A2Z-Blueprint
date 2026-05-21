# CHANGELOG v10.208 — Seventh cockpit absorption (Risk Arc → 35_stress_testing.py)

**Date:** 2026-05-07
**Theme:** Seventh cockpit absorption batch. Folds
`93_risk_arc_cockpit.py` (715 lines — the largest absorbed so far)
into `35_stress_testing.py` (999 lines) as a 6th top-level
"🤖 Arc Engines" tab containing 5 nested sub-tabs. Refactors G130
from location-based to manifest-aware behavior-based — eighth
instance, most complex variant since this gate also checks engine
constructor + method invocation patterns. Audit holds at
**160/160 PASS**.

## What v10.208 ships

### 1. `pages/35_stress_testing.py` — absorbed Arc Engines as 6th tab

Stress Testing page goes from 5 → 6 top-level tabs (within G4's 7-tab
cap, 1 slot of headroom remaining):

```
📊 Scenario Runner  📈 Side-by-Side  🎛️ Custom Scenario  📄 ICAAP Report  🏛️ CBK Supervisory  🤖 Arc Engines  ← NEW
```

Inside the new tab, 5 nested sub-tabs reproduce the cockpit's structure:

```
📈 Market Risk VaR (#ENH-MR-001)    — VaREngine + parametric/historical/MC methods
🏛️ IRB Capital (#ENH-CR-001)       — IRBCapitalEngine + compute()/compute_portfolio()
⚙️ Op Risk SMA (#ENH-OR-001)       — OperationalRiskSMA + compute()
💧 Stressed LCR (#ENH-LR-001)       — LiquidityStressEngine + compute()
ℹ️ About                            — Framework references + governance flow
```

All 4 Basel III regulatory engines (BCBS d352, d424, d457, d295)
preserved with their full dataclass surfaces. Engines are
**diagnostic-only** — no remediation buttons; outputs feed governance
discussions (ALCO, Capital Management Committee, Risk Committee).

### 2. MD/CEO visibility preserved

Per Joshua's reminder, the MD/CEO has full cross-departmental
visibility through the admin path. After v10.208, the Risk Arc
engines remain visible to the MD via:

- **Direct path:** Sidebar → Risk department → Stress Testing →
  🤖 Arc Engines tab. The MD sees all departments, so this works.
- **Future MD Cockpit consideration:** The MD's natural workflow
  centers on Command Centre (`6_integrate.py`), Board Papers
  (`84_board.py`), BSC (`1_perform.py`), Tier-1 Benchmarking
  (`87_benchmarking.py`), Strategic Initiatives (`83_strategy.py`),
  and the financial cuts (Management Accounts, Capital & Liquidity).
  Each cockpit absorption keeps these working — the engines relocate
  to their primary department's parent page where the MD already
  has access. A dedicated "🎯 MD Cockpit" page that aggregates these
  cross-departmental strategic views is a future enhancement
  candidate; for now, the admin/MD path through the manifest's
  department traversal serves the same need.

### 3. `scripts/audit.py` — G130 refactored to manifest-aware

Eighth instance of the manifest-aware refactor pattern. Most complex
variant yet, since G130 doesn't just check imports — it also checks
**engine constructor + method invocation patterns** for each of the
4 engines. The refactored gate scans all non-deprecated pages in the
`risk` department, concatenates their text, and verifies:

- 4 required imports present somewhere in dept text
- 4 engine constructors `Class()` present
- For each engine, at least one of its compute-style methods invoked
- `require_access(` present somewhere
- `audit_log(` present somewhere

Note: this is a stricter gate than the simple "imports only" check
of G149/G151/G159/G148/G153/G155/G157. Preserving the strictness
is important — the original v10.46 design intent was that engines
must be **interactively used**, not just descriptively imported.

### 4. `pages/_manifest.json` — cockpit entry removed

Manifest entry for `93_risk_arc_cockpit.py` deleted. Manifest goes
102 → 101 pages, 7 → 6 deprecated cockpits.

### 5. `pages/93_risk_arc_cockpit.py` — DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/93_risk_arc_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 1 deletion)

```
pages/35_stress_testing.py        MOD  +682 lines  (999 → 1681)
                                       (6th top-level tab + 5 nested sub-tabs)
scripts/audit.py                  MOD  +20 lines net  (G130 manifest refactor)
pages/_manifest.json              MOD  -16 lines  (cockpit entry removed)
pages/93_risk_arc_cockpit.py      DEL  -715 lines  (manual deletion required)
```

Net cockpit absorption: -715 (cockpit) + +682 (target) - 16 (manifest)
= **-49 lines net code reduction**. Smaller than typical because the
cockpit has substantial scenario-loaded content with dataclass
constructors that don't compress as much as boilerplate-heavy cockpits.

## Audit

```
Before (v10.207): Score: 160/160 gates = 100.0% — PASS
After  (v10.208): Score: 160/160 gates = 100.0% — PASS
```

## Trajectory through this batch

1. Add 6th top-level tab to 35_stress_testing.py: 160/160 PASS
2. Append nested sub-tabs (after fixing indentation: cockpit body at
   col 4 → col 12, +8 spaces): 160/160 PASS
3. Refactor G130 to manifest-aware (preserving strict invocation
   checks): 160/160 PASS
4. Delete cockpit + manifest entry: 160/160 PASS

Indentation transform was +8 spaces this time (col 4 cockpit body →
col 12 target body), different from v10.204..v10.205 (+4). The Risk
cockpit's tabs are at col 0 (module-level `with risk_tabs[N]:`),
not col 4 like Compliance/Product. Pattern variant catalog grows by
one entry — but this is just a recombination of existing variants.

## Cockpit absorption schedule — 7/13 done (54%) — over halfway

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1 | ✅ v10.202 | 26_treasury_arc_cockpit.py | 25_treasury.py |
| 2 | ✅ v10.203 | 15_strategy_arc_cockpit.py | 83_strategy.py |
| 3 | ✅ v10.204 | 16_product_arc_cockpit.py | 5_products.py |
| 4 | ✅ v10.205 | 27_compliance_arc_cockpit.py | 24_compliance.py |
| 5 | ✅ v10.206 | 28_legal_arc_cockpit.py | 26_legal.py |
| 6 | ✅ v10.207 | 29_resource_optimization_cockpit.py | 10_opex.py |
| 7 | **✅ v10.208** | **93_risk_arc_cockpit.py** | **35_stress_testing.py** |
| 8 | pending | 94_credit_governance_cockpit.py | 22_credit_analysis.py |
| 9 | pending | 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py |
| 10 | pending | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py |
| 11 | pending | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | pending | 98_ml_governance_arc_cockpit.py | 91_systems_view.py |
| 13 | pending | 99_integration_cockpit.py | 91_systems_view.py |

7/13 absorbed (54%). At 1/batch, completion at v10.214.

## Honest acknowledgements

1. **G130 refactor preserved strictness.** Unlike the simpler
   "imports-only" gate refactors, G130 also checks engine
   constructor + method invocation patterns. The refactored gate
   maintains all 4 invocation checks per engine — `Class()` must
   appear, AND at least one named method must be invoked.
   This is the correct level of strictness for the Risk arc
   ("engines surface exposure, never execute remediation" requires
   evidence of interactive use, not just imports).

2. **Indentation bug caught and fixed in-batch.** The first
   absorption attempt got body indentation wrong (+4 instead of
   +8). The script `ast.parse` caught it before the file was
   written; one retry with corrected indentation succeeded. Same
   pre-flight safety pattern that has caught all such bugs across
   the campaign.

3. **MD/CEO visibility preserved.** Per Joshua's note, the MD's
   primary modules (Command Centre, Board Papers, BSC, etc.)
   remain in their canonical locations and aren't affected by Risk
   Arc absorption. The Risk engines themselves are now reachable
   via Stress Testing → 🤖 Arc Engines tab; admin/MD users see all
   departments through the manifest's traversal.

4. **`35_stress_testing.py` is at 6/7 top-level tabs.** Same
   pattern as `24_compliance.py` (after v10.205) and `10_opex.py`
   (after v10.207). 1 slot of headroom remaining within G4.

5. **Net code reduction: -49 lines.** Smaller than typical (-86
   to -132 prior batches). The Risk cockpit has substantial
   scenario-loaded content with dataclass constructors that don't
   compress as much as boilerplate-heavy cockpits. Cumulative
   reduction across 7 batches now -662 lines.

6. **The `risk_tabs` named-variable convention** was a hybrid of
   the v10.205 indexed and v10.206 named-numbered conventions. The
   extraction script handled it as a variant of the indexed pattern
   (`with risk_tabs[N]:`). Pattern catalog adequacy confirmed —
   no new variants needed for this absorption.

7. **G130 is the eighth instance of manifest-aware refactor.** Now
   significantly stronger case for helper extraction (originally
   targeted at 7 instances). Continuing to defer because the
   remaining 6 absorptions follow the simpler pattern; the helper
   would primarily benefit those, and helper bugs would now block
   6 batches worth of work.

8. **Page-number collision dropping continues.** Slot 93 was
   claimed by `93_risk_arc_cockpit.py` only — no collision relief
   from this batch. Net collision count unchanged at 2.

9. **18 consecutive clean batches in this session** — v10.193
   through v10.208 (16 code batches + 2 advisory reviews). Cockpit
   absorption sub-campaign at 7/13 = 54% complete, over halfway.

10. **The `pages/_cockpit_render` import** referenced by some
    earlier cockpits isn't needed here — Risk cockpit renders its
    own custom widgets (Decimal-aware metrics, dataclass tables)
    rather than using the standard summary renderer. Absorbed
    section preserves this directly.

11. **Risk department's manifest count** now 6 → 5. The department
    had 6 active pages (35_stress_testing, 44_incidents, 82_oprisk,
    85_esg, 92_climate_esg) plus the Risk Arc cockpit; after
    absorption + deletion, 5 active pages remain. Each of the 5 is
    in active operational use.

12. **Looking ahead.** v10.209 candidate: Credit Governance Arc
    (`94_credit_governance_cockpit.py` → `22_credit_analysis.py`).
    Followed by Revenue Assurance (v10.210), Finance Arc (v10.211),
    Trade Finance Arc (v10.212). Then the dual-target pair: ML
    Governance + Integration both → 91_systems_view.py (v10.213).

## Next batch options

1. **v10.209 — Credit Governance absorption** (`94_credit_governance_cockpit.py`
   → `22_credit_analysis.py`). Mechanical continuation.
2. **v10.209 — Extract `scripts/absorb_cockpit.py`.** All variants
   now mapped + 8 refactor instances. Strong case for tooling batch.
3. **v10.209 — Page migration to dotted form.**
4. **v10.209 — Explore MD Cockpit page.** Aggregate cross-departmental
   strategic views into a dedicated page (Command Centre + Board
   Papers + BSC summary + Tier-1 Benchmarking + capital snapshot +
   compliance posture). New page in the strategy_performance
   department or a new "executive" department. ~150 lines.

I'll continue with **option 1** (Credit Governance) for momentum.
The MD Cockpit (option 4) becomes a natural standalone batch after
all 13 absorptions complete — by then the engine relocations are
done and the MD Cockpit's data sources are all stable.
