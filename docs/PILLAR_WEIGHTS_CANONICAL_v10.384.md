# Rescuing the Body's Prioritization Organ — Pillar Weights Consolidation

**Version anchor:** v10.384 (May 2026)
**Per:** Joshua's directive at v10.383 wrap-up — *"after we need rescue body's prioritization organ"*
**Pre-requisite:** `PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md` (the v10.382 deep review)

The pillar weights organ has been silently broken. v10.384 establishes the canonical accessor, exposes the silent failure explicitly, and adds audit-history. The full consolidation continues in v10.385-v10.388 per the v10.382 plan.

---

## Part 1 — The silent failure exposed

### 1.1 What v10.384 found in current production state

```
Canonical (kpi_library.json::pillar_weights):
  {Financial: 0.68, Customer Focus: 0.14, Operational Excellence: 0.06, People & Learning: 0.12}
  → Financial-heavy crisis weighting (90% read by 5 consumers)

Orphan (org_config.json::pillar_weights):
  {Financial: 0.40, Customer Focus: 0.25, Operational Excellence: 0.25, People & Learning: 0.10}
  → Kaplan-Norton balanced (written, but NEVER READ)
```

**Two different "current pillar weights" depending on which admin tab you visit.** Whoever set the balanced 40/25/25/10 via Bank Identity tab thought they'd rebalanced the bank. The BSC scoring engine never received the change.

### 1.2 Severity (per constitution §5.4)

This is a constitutional §5.4 violation already in production: the admin UI accepts input, says "saved successfully", but the change has zero effect. **The body accepts a prescription it never takes.**

---

## Part 2 — What v10.384 ships

### 2.1 `utils/pillar_weights_canonical.py` (NEW)

Leaf module — single source of truth for pillar weights:

| Function | Purpose |
|---|---|
| `get_pillar_weights()` | Read canonical state (kpi_library.json::pillar_weights) |
| `save_pillar_weights(weights, actor, reason)` | Validate + write to canonical + append history |
| `validate_pillar_weights(weights)` | Enforces sum=1.0, all positive, all 4 pillars present |
| `get_pillar_weights_history(limit)` | Recent changes (newest first) |
| `detect_orphan_pillar_weights()` | Check org_config.json for orphan; return them or None |
| `health_check()` | Diagnostic snapshot (canonical, orphan, history, shadow fields) |

Constants:
- `CANONICAL_PILLARS` — the 4 BSC perspectives (Financial / Customer Focus / Operational Excellence / People & Learning)
- `DEFAULT_BALANCED_WEIGHTS` — Kaplan-Norton 40/25/25/10
- `SUM_TOLERANCE` — 0.001 for float-arithmetic comfort

### 2.2 History file schema (`data/pillar_weights_history.json`)

```json
[
  {
    "changed_at":   "2026-05-13T13:14:15+00:00",
    "changed_by":   "olive001",
    "reason":       "Crisis quarter — financial recovery focus",
    "old_weights":  {"Financial": 0.40, ...},
    "new_weights":  {"Financial": 0.68, ...}
  }
]
```

Capped at 100 entries (most recent). Every `save_pillar_weights` call appends.

### 2.3 Admin Bank Identity tab — deprecation notice

`st.warning` added above the pillar weights section in `pages/7_admin.py`:

> ⚠️ **Deprecated.** Changes to pillar weights HERE do NOT affect BSC scoring. They write to a legacy location no longer read by the scoring engine. **To change pillar weights, go to: Admin → KPI Library → Pillar weights tab.** That tab writes to the canonical store (`kpi_library.json::pillar_weights`) with audit-history. This section is preserved only for backward compatibility and will be removed in v10.388.

The existing form code is preserved — operators who don't read the warning still get the no-op save (silent failure no longer silent). Removal scheduled for v10.388.

---

## Part 3 — Validation rules (per body-system framing)

`validate_pillar_weights` enforces:

| Rule | Rationale |
|---|---|
| All 4 canonical pillars present | The body has 4 vital-sign organs; missing one means the body can't sense itself fully |
| Each weight > 0 | A zero-weight pillar is a dead organ; the body needs every organ functioning |
| Each weight ≤ 1.0 | No pillar can dominate completely |
| Sum = 1.0 ± 0.001 | The body's attention budget must be conserved |
| All weights numeric | Schrödinger's-weight breaks scoring |

These rules align with Donella Meadows' systems-thinking: complex systems require multiple feedback channels. Eliminating any channel (zero-weight) destabilizes the system.

---

## Part 4 — What v10.384 deliberately does NOT do

Per Rule N2 (single concern), v10.384 explicitly:

- Does NOT change the canonical pillar weights value (still 68/14/6/12)
- Does NOT remove the Bank Identity tab pillar-weights form (deprecation notice only)
- Does NOT delete `org_config.json::pillar_weights` (orphan preserved for migration audit)
- Does NOT remove `kpi_library.json::pillars[].weight` (shadow data preserved)
- Does NOT touch any of the 5 canonical-location readers
- Does NOT migrate the orphan weights to canonical (operator decision)
- Does NOT add a separate per-role pillar weights override (deferred per v10.382 plan)
- Does NOT consolidate with Tab 23 Thresholds (deferred per v10.382 plan)

Single concern: **establish the canonical accessor + history + deprecation notice. Make the silent failure visible.**

---

## Part 5 — Recommended next actions (queued for Joshua)

| Step | Batch | Action |
|---|---|---|
| A | v10.385 | (Deep body diagnosis — per Joshua's second directive) |
| B | v10.386 | Migrate KPI Library Pillar Weights admin tab to use `save_pillar_weights()` — gets audit-log + validation |
| C | v10.387 | Add a "History" view to the admin tab — shows last 10 changes with OLD/NEW values |
| D | v10.388 | Remove the deprecated Bank Identity pillar weights form |
| E | v10.389 | Remove `kpi_library.json::pillars[].weight` shadow fields |
| F | v10.390 | Remove `org_config.json::pillar_weights` orphan |

After v10.390: ONE storage location, ONE admin UI, FULL audit trail, NO silent failures. The prioritization organ functions correctly as one.

---

## Part 6 — Body-system framing

Before v10.384, the body's prioritization organ had three problems:
1. **Two competing voices** (two admin UIs editing the same concept)
2. **One voice ignored** (the Bank Identity tab writes were silently discarded)
3. **No memory** (no audit trail of who changed what when)

After v10.384:
1. **One canonical voice** (the `utils.pillar_weights_canonical` module is THE accessor)
2. **The silent voice is now visibly silent** (deprecation warning visible in the orphan UI)
3. **Memory established** (pillar_weights_history.json captures every change)

The body still has two paths to write pillar weights (the deprecation period), but only one path actually affects scoring. Operators now see the truth on screen.

The body's prioritization organ is no longer silently broken — it's **transparently in transition**. The rescue is in progress; completion at v10.388-v10.390.

---

## Part 7 — Honest acknowledgements

1. **The orphan 40/25/25/10 has been ignored for an unknown duration.** Whoever set it via Bank Identity tab thought they'd rebalanced the bank. The fact that this was undetectable for so long is the kind of silent debt the constitution §5.4 warns against.

2. **The canonical 68/14/6/12 is financial-heavy.** Per the v10.381 recommendations, this should return to balanced — but that's a separate batch (and needs operator confirmation per Decision W5).

3. **The deprecation notice doesn't STOP the dead-branch write.** Operators who save via Bank Identity still write to org_config. The notice makes the failure visible; removal of the dead form is v10.388.

4. **The history file is empty at v10.384 ship.** Future `save_pillar_weights()` calls will populate it. The 68/14/6/12 → unknown-origin change cannot be retroactively logged.

5. **`pillars[].weight` shadow data is untouched.** v10.382 review documented it; v10.384 doesn't remove it (would risk breaking some pillar-iteration consumers).

6. **Direct consumers of `kpi_library.json::pillar_weights` are unaffected.** They keep reading the same field; the canonical accessor reads the same field. No migration of consumers needed for v10.384.

7. **Per-role pillar weights (the older ROLE_MAP system)** are still parallel. v10.384 doesn't touch them. v10.382 Decision W6 deferred this.

8. **Validation rules align with body-system framing** — zero weight is a dead organ, sum must conserve attention budget. The validation is a small assertion of constitution §12 (Flow Principle).

9. **The deprecation notice text says "removed in v10.388".** This is a commitment captured in code. Don't let it slip — body-organ rescue should complete in 4 batches.

10. **Rule N2 single concern held strictly.** Canonical module + history schema + admin deprecation notice. No consumer migrations, no removal of the orphan, no consolidation with thresholds. Each is a separate batch.

11. **The canonical module is leaf.** Zero `utils.*` imports — pure JSON I/O + validation logic. Easy to test, easy to import, easy to verify safe.

12. **The body-system framing is genuine here.** This isn't a metaphor stretched for the doc — pillar weights LITERALLY determine which of the four organ-systems gets attention in scoring. A broken prioritization organ means the body can't tell itself what matters.
