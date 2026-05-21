# A2Z MIS 360 — KAIZEN Framework for Continuous Improvement

**Adopted:** v10.219 (2026-05-07)
**Status:** Active discipline
**Owner:** A2Z Platform Engineering

> **Kaizen** (改善, "improvement"): a Japanese business philosophy
> emphasizing **incremental, continuous improvement** through small
> daily changes. Toyota Production System made it famous; the discipline
> is universal.

---

## 1. Why KAIZEN for A2Z

The platform reached a structural maturity point at v10.218:
- 13/13 cockpits absorbed
- 162 audit gates ratcheting invariants
- Manifest-as-canonical for routes
- Dotted-form access mechanism
- Helper extracted for future absorptions

What got us here: **disciplined small batches** averaging ~120 lines/
batch, audit before AND after every change, single-purpose batches,
honest acknowledgements.

What kaizen formalizes: **the discipline that already worked.** This
document doesn't introduce new rules; it names the rules that already
hold and ensures they survive the campaign window.

---

## 2. Five KAIZEN principles for A2Z

### Principle 1 — Baselines are ceilings, never floors

Every drift area gets a baseline measurement and a ratchet that
prevents the count from going UP. Reduction happens incrementally
through normal work; the ratchet just guarantees no backsliding.

**Example:** v10.219's G162 records current count of hardcoded
tenant strings. New code can't add more. Refactors that replace
hardcoded strings with `cfg()` calls reduce the baseline. Either
direction is fine; only INCREASING the count fails the gate.

This is how the audit suite turns one-time cleanup into permanent
hygiene.

### Principle 2 — Small batches, daily cadence

The v10.193–v10.218 window proved this works:
- 26 consecutive clean batches over ~7 weeks
- ~120 lines/batch average
- Each batch single-purpose with clear deliverable

Avoid the temptation of big-bang refactors. A 4,100-line tenant
hardcoding cleanup looks attractive but:
- Risks introducing new bugs at scale
- Spends weeks on one thing that should be 10 batches of 1 week each
- Misses the kaizen pattern entirely

Better: ten batches of ~410 lines each, with G162 ratcheting baseline
down by 10% each batch. Same total work; ten times the risk
mitigation; ten times the visibility.

### Principle 3 — Audit before AND after every change

Already established discipline. Codified by:
- `python scripts/audit.py` before starting work
- Same command after the change is complete
- Same expected output (X/X gates = 100.0% PASS)

Any drift in the gate count or pass percentage triggers immediate
investigation. The audit log is the heartbeat.

### Principle 4 — Honest acknowledgements in every CHANGELOG

Every CHANGELOG includes a numbered "Honest acknowledgements" section
covering:
- What this batch deliberately doesn't address
- What's borderline / debatable
- What might surface later as drift
- What scope was creeping and got pulled back

This serves three purposes:
- Future readers (including future-you) understand the trade-offs
- Drift becomes visible BEFORE it bites
- Single-purpose discipline gets enforced via the awkwardness of
  having to explain why scope grew

### Principle 5 — Ratchets, not heroics

A one-time cleanup that doesn't add a gate is heroic but doesn't
hold. Within 6 months, the same drift returns.

A ratchet that locks the post-cleanup state is permanent. The
cleanup happens once; the gate ensures it stays clean.

Examples from the campaign:
- G161 (module_path_dept_aligned, v10.218) — locks v10.217's
  manifest cleanup
- G149 (cockpits_registered_in_app, v10.199) — locks the cockpit
  campaign's manifest discipline
- G162 (tenant_identity_hardcoding, v10.219) — locks the current
  hardcoded count as ceiling

When you finish a cleanup, the next question is always: "What gate
prevents this from breaking again?"

---

## 3. KAIZEN rituals

### Daily ritual: One batch, audit-bracketed

```
09:00 — python scripts/audit.py            (start state)
        Open the user's request / plan the day's work
09:15 — Make the change
11:00 — python scripts/audit.py            (end state)
        Same gate count, same 100% pass rate
        Write CHANGELOG with honest acknowledgements
        Package zip
        Deliver
```

This is the rhythm that produced v10.193–v10.218.

### Weekly ritual: Memory reconciliation

User memory tracks campaign state ("13/13 cockpits absorbed",
"PG migration 33/52", etc.). Periodically reconcile against
ground truth:

```bash
# Cockpit campaign reconciliation
ls pages/*_cockpit*.py    # should be 0 after v10.212

# PG migration reconciliation
grep -c "^def migrate_" scripts/migrate_to_postgres.py
grep -c "^CREATE TABLE" *.sql
```

When reality diverges from memory, update the memory. The v10.219
audit caught one such divergence (PG migration progress claimed in
memory ≠ actual code state).

### Monthly ritual: Drift area review

Re-run the v10.219 audit-style review:
- Count hardcoded tenant strings (G162 ratchet provides this)
- Count direct write_text in pages (vs db.dual_save)
- Count cfg() lookups (should grow over time)
- Count test coverage % (when G165 is in place)

If any drift area is moving in the wrong direction, schedule a
sub-campaign batch.

### Quarterly ritual: Master prompt update

User memory + CHANGELOG accumulated wisdom gets distilled into
docs/MASTER_PROMPT.md (when it exists; currently being created).
Every quarter:
- Promote any rule that surfaced 3+ times in CHANGELOGs into the
  prompt
- Demote any rule that hasn't applied in 6 months
- Test the prompt by reading recent CHANGELOGs and asking "would
  this have helped me catch X earlier?"

---

## 4. KAIZEN anti-patterns to avoid

### Anti-pattern 1: Big-bang refactors

> "Let me fix all 4,100 hardcoded strings in one batch."

Risks: introduces bugs at scale; weeks-long batches; obscures the
real progress signal; violates single-purpose discipline.

Better: kaizen-paced sub-campaign over 10 batches with G162
ratcheting baseline down each batch.

### Anti-pattern 2: Adding gates without baselines

> "Let me add a strict gate that fails if any hardcoded 'Ecobank'
> appears."

Risks: audit fails immediately; can't ship the gate; creates pressure
to either roll it back OR rush a 4,100-line fix.

Better: kaizen ratchet with baseline. Gate fails only on INCREASE.

### Anti-pattern 3: Heroic cleanups without gates

> "I refactored all the dotted-form access calls in finance dept!
> Done!"

Risks: nothing prevents future drift. Six months later, a new page
gets added with flat-form access; nobody notices; the rollout
quietly degrades.

Better: cleanup PLUS a ratchet (e.g. v10.218's G161 followed
v10.217's cleanup).

### Anti-pattern 4: Memory tracking drift

> "Memory says 33/52 PG tables, so we're more than half done."

Risks: planning decisions based on stale tracking. v10.219 audit
revealed actual state was 2 migrators, not 33.

Better: weekly memory reconciliation against ground truth.

### Anti-pattern 5: Scope creep within batches

> "While I was fixing X, I noticed Y was also broken, so I fixed
> Y too. And while looking at Y I saw Z..."

Risks: batches balloon; single-purpose discipline erodes; honest
acknowledgements section becomes a sprawling list of "also did".

Better: fix X, write a CHANGELOG note "Y is also broken, scheduling
v10.NEXT", deliver. Address Y in v10.NEXT.

The ONLY exception: when fixing X is impossible without fixing Y
(e.g. v10.215 bug-fix-plus-scaffolding where the data scaffolding
revealed cockpit reading bugs that had to be fixed for the
scaffolding to be useful). Even then, flag the multi-purpose nature
in the CHANGELOG honestly.

---

## 5. KAIZEN as applied to specific drift areas

### Tenant identity hardcoding (~4,100)

```
Today (v10.219): baseline locked at ~4,100 via G162
v10.220:        config helpers + admin tenant card (additive)
v10.221:        first ~400 hardcoded → cfg() conversions
                (e.g. utils/ files where the impact is highest)
v10.222:        next ~400 (largest pages: 7_admin.py, 87_benchmarking.py)
v10.223:        next ~400 (BSC + cascade pages)
...
v10.230:        last ~400; baseline at ~0; G162 becomes a strict
                "no hardcoded tenant strings" gate
```

10 batches of ~400 each. ~10 weeks at 1 batch/week. End state:
zero hardcoded tenant strings; multi-tenant ready.

### PG migration

```
Today (v10.219): 12 tables in DDL; 2 migrators; 165 JSON files
v10.220–v10.230: tenant hardcoding sub-campaign (different focus)
v10.231:         DDL for all 40+ remaining data files
v10.232:         5 highest-value migrators
v10.233:         next 10
...
v10.245:         all 50+ tables migrated; G164 ratchet
```

15+ batches. Could parallelize with tenant cleanup if scope allows.

### Test coverage

```
v10.246:        baseline coverage measurement (pytest run)
v10.247:        G165 ratchet (no coverage drop > 0.5pp)
v10.248–v10.260: incremental tests for highest-risk modules,
                ratcheting coverage UP each batch
```

Long-tail kaizen. End state: 80%+ coverage maintained ratchet-style.

---

## 6. KAIZEN governance

### Who decides what's a drift area?

The audit script is the source of truth. If a gate fails, that's
drift. If the count of hardcoded strings (or coverage %, etc.)
moves in the wrong direction, that's drift. **Numbers, not opinions.**

### Who decides batch scope?

Single-purpose discipline. The user requests; Claude proposes;
the CHANGELOG honest acknowledgements section is the test of whether
scope was right ("this batch deliberately doesn't address Y" is
fine; a long sprawling list is a signal that scope was wrong).

### Who decides when a sub-campaign starts?

Drift area severity. CRITICAL (like tenant hardcoding) gets
prioritized. HIGH gets queued. Lower-severity items wait until the
queue is empty.

### Who decides when a sub-campaign ends?

The ratchet that locks the cleanup state. When G162 reads "0 violations,
0 baseline" and stays there for 4 batches, the sub-campaign is done.

---

## 7. KAIZEN for the campaign tracker (user memory)

Joshua's memory tracks campaign state. Kaizen-pace updates:

- After each batch: update the "Top of mind" / "Recent months" sections
- Weekly: reconcile any aspirational claims (PG migration count, etc.)
- Monthly: prune stale items from memory; promote durable patterns
  to the prompt addendum

---

## 8. The KAIZEN promise

By following these principles:

1. The platform never gets WORSE between sessions. Every batch leaves
   the codebase ratcheted forward.
2. Drift becomes visible BEFORE it bites — the audit suite sees it
   first, and the user sees it via failed batches OR via documented
   drift areas in the audit reports.
3. Big problems become tractable through small steps. 4,100
   hardcoded strings is paralyzing as a one-batch task; ~400/batch
   for 10 batches is normal cadence.
4. Discipline is portable. New collaborators read this framework
   and the master prompt; they can contribute clean batches from
   day one.
5. The system improves while staying useful. Every batch ships
   working software. Audit gates ensure no regressions. Users keep
   getting value while the platform gets cleaner.

This is the v10.193–v10.218 discipline named. v10.219 onwards
applies it explicitly.

---

## 9. KAIZEN one-liner

**"Today's audit baseline is tomorrow's audit ceiling. Today's
hardcoded value is tomorrow's `cfg()` lookup. Today's drift signal
is tomorrow's ratchet. Small steps. Daily. Forever."**
