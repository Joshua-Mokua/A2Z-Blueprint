# Changelog — v10.409 Negotiation Escalation Chain (E4) + KeyError fix

**Date:** 2026-05-14
**Phase:** QA-Standards enhancement (4 of 7) + critical bug fix from Joshua's live error
**Audit:** G295 added
**Tests:** 13/13 PASSED in `test_v10409_negotiation_escalation_chain.py`
**Verifier:** 606/606 checks pass
**G162 baseline:** 4022 (102 consecutive zero-drift batches)
**Master prompt:** v4.51 → v4.52 (lockstep — 53 consecutive batches)

---

## Joshua's live error report

```
KeyError: 'from_code'
File "pages/12_cascade.py", line 3369, in <module>
    fc=e["from_code"]
```

## Root cause

`cascade.items()` iterates the full target_cascade.json dict — including underscore-prefixed **meta-keys** like `_v10397_regenerated`, `_v10401_period_harmonization`, `_v10402_kpi_naming`, `_v10403_dedup_pending`, `_v10404_preserve_manual`. These are migration stamps, not cascade entries — they lack `from_code`.

The existing filter only skipped `deadline|` and `global_` prefixes. Meta-keys slipped through, crashing on `e["from_code"]`.

## Critical fix — defensive guards everywhere

**Cascade page** (`pages/12_cascade.py`):
- Line 1235 (existing_allocs loop): ✓ guarded
- Line 2470 (debug alloc_entries comprehension): ✓ guarded
- Line 3642 (Allocation coverage loop): ✓ guarded — **this was the crash site**
- Line 3677 (Deadline tracker `_my_dr_codes`): ✓ guarded

**Utils core** (`utils/core.py`):
- 9 sites already had underscore guards from earlier batches
- Line 3253 (clean_code lookup): ✓ added missing underscore guard

**Defensive pattern applied at every cascade.items() site:**
```python
for k, e in casc.cascade.items():
    if k.startswith("_") or k.startswith("deadline|") or k.startswith("global_"):
        continue
    if not isinstance(e, dict) or "from_code" not in e:
        continue  # defensive: malformed entry
    fc = e["from_code"]
    ...
```

## Per QA-Standards Enhancement #4

> **Problem:** Target disputes have no formal resolution process.
> **Solution:** Structured negotiation workflow with escalation path.

### Pre-v10.409 state

- `resolve_review(status, response, by)` — manager picks Approved or Rejected, that's it
- No counter-proposal, no escalation, no SLA enforcement

### v10.409 escalation API

**`resolve_review` extended:**
- `counter_target: float = None` — manager's counter-proposed value
- `escalate_to: str = ""` — skip-level manager staff_code
- `escalate_to_name: str = ""` — display name
- New statuses: `Counter-Proposed`, `Escalated`
- Escalated re-opens as Pending for the new resolver
- Each call appends to `r["history"]` for audit trail

**New `auto_escalate_overdue_reviews(sla_days=7)`:**
- Marks pending reviews older than 7 days as SLA-breached
- Stamps `auto_escalated_at`, `auto_escalation_reason`, `sla_breached`
- Idempotent (only fires once per request)

### v10.409 UI

Review Requests tab:
- 4-option decision selector (Approved / Counter-Proposed / Escalated / Rejected)
- Conditional counter_target number_input pre-filled with requested amount
- Conditional escalate_to text_input with staff_code lookup
- SLA badges: ⏰ 5+ days open, ⚠️ 7+ days overdue
- Escalation badge if request was previously escalated
- 📜 History expander showing full action chain
- **Admin SLA trigger** (MD/admin): warning + "🚀 Run SLA escalation" button

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 294 → **296** |
| Tests | 363 → **376** (+13 new) |
| Verifier | 593 → **606 checks** |
| Master prompt lockstep | **53/53 consecutive batches** |
| G162 baseline | 4022 (**102 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |
| KeyError crash | ✅ fixed at 4 cascade page sites + 1 core.py site |

## 10 honest acknowledgements

1. **Defensive coding saved embarrassment.** Same bug pattern in 4+ cascade page sites; every `cascade.items()` was a potential crash.

2. **Meta-keys accumulating over migrations.** Each batch stamps the cascade dict. Long-term: consider separate metadata file.

3. **Line 3369 = v10.408 position for what was 2944 in v10.405.** v10.406-v10.408 added 425 lines above the coverage section, shifting line numbers.

4. **Already-protected sites stayed protected.** v10.409 just added one missed site at L3253 + 4 cascade page sites; verified the others.

5. **E4 is now production-grade negotiation.** Counter-Proposed lets manager negotiate; Escalated routes to skip-level; SLA enforces accountability.

6. **Escalation reopens as Pending.** Manager A escalates to B; request becomes Pending for B who can Approve/Reject/Counter/Escalate further. Chain, not tree.

7. **History is append-only.** Every action stamps a new history entry. Full audit trail.

8. **Admin SLA trigger is manual.** Doesn't auto-run on page load (expensive). Admin sees count → clicks button. Future: scheduled job.

9. **No data migration needed.** Existing review requests keep their old shape; new fields appear with new resolutions.

10. **53 consecutive lockstep batches. 102 consecutive zero-drift G162 baseline.**

## What you'll see when you reload

1. **KeyError crash gone** on Coverage & deadlines tab — page renders cleanly past meta-keys.

2. **Review Requests tab** — full 4-option flow:
   ```
   Decision: [Approved v]   Response: [...]
                ├── Counter-Proposed
                ├── Escalated
                └── Rejected
   Counter target: [pre-filled]
   Escalate to staff_code: [type code]
   [Submit decision]
   ```

3. Admin/MD with overdue reviews:
   ```
   ⚠️ 3 review(s) overdue >7 days
   [🚀 Run SLA escalation]
   ```

4. Each pending review shows:
   - ⏰ Xd open / ⚠️ Xd overdue / 🆙 escalated from {prev}
   - 📜 History expander with full chain

## On your end

1. Close Streamlit
2. Extract `a2z_v10409_patch.zip` on top of v10.408 state
3. Run `python scripts\verify_local_state.py` → expect **606/606**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login → Cascade page → **Coverage & deadlines** tab → should render without crash
6. **Review requests** tab → 4-option decision flow visible
7. Tell me **"continue"** → v10.410 = E5 Executive Cascade Health Dashboard

## Roadmap

| Batch | Status |
|---|---|
| ~~v10.403-v10.405~~ Cleanup + UX repairs | ✅ |
| ~~v10.406~~ E1: Progress Rollup | ✅ |
| ~~v10.407~~ E2: Strategic pillar viz | ✅ |
| ~~v10.408~~ E3: Target what-if simulator | ✅ |
| ~~v10.409~~ E4: Negotiation escalation + KeyError fix | ✅ **DONE** |
| **v10.410** E5: Executive cascade health dashboard | **next** |
| v10.411 E6: Capacity feedback |
| v10.412 E7: Cascade API & exports |
| v10.413-v10.415 F2/F3/F5 architectural |
| v10.416-v10.421 Data integrity + housekeeping |
| v10.422-v10.424 CBS / BSC verification |
