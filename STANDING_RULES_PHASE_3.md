# A2Z MIS 360 — Standing Rules for Phase 3

**Effective:** v10.294 onward
**Phase:** 3 — Operational Hardening & Cockpit Integration
**Supersedes:** Phase 2A/2B standing rules where conflicts arise

---

## Phase 3 scope

Phase 2B closed with all 330 standards active. Phase 3 is no longer
about *adding* standards — it's about *making them operate together*
in a live system. Phase 3 has six tracks:

1. **Cockpit integration** — live Streamlit composition of the 330
   engines into operating cockpits. G130 deferred-to-closure
   obligation across all arcs that haven't yet been closed under
   the v10.208+ UI integration discipline.

2. **PostgreSQL migration** — currently 48/79 tables in PG-mode
   (61%). Phase 3 target: 75+ tables (95%+) in PG-mode, with the
   remaining tables either retired (deprecated arc) or explicitly
   marked as JSON-only with rationale.

3. **API endpoint coverage** — 192 endpoints across 19 modules
   today. Many engines still lack public API surfaces. Phase 3 will
   close gaps where external systems (FLEXCUBE, partner systems,
   mobile apps, the React SPA) need to read from the platform.

4. **Test coverage** — 187 test files today. Phase 3 will lift
   coverage for the Phase 2A/2B engines that were shipped with
   self-tests only (no integration tests).

5. **Regulatory artefacts** — FATCA/CRS XML output, the remaining
   5/8 CBK regulatory returns, IFRS 9 disclosures, IRA returns
   for bancassurance, KRA tax integration.

6. **Frontend** — React SPA (#37) and React Native (#38) standards
   remain as design-only; Phase 3 will not deliver them in full,
   but may scaffold the JSON API contracts they'll consume.

---

## Locked rules from Phase 2 (still apply)

The following Phase 2 rules remain in force. Breaking any of them
will fail audit and block delivery.

### Imports

- `from utils.core_audit import audit_log` — NEVER `utils.audit_log`
- `from pages._access import require_access` — NEVER `utils.access_helpers`
- G177 enforces these statically across all pages.

### audit_log signature

```
audit_log(action, username, detail, module, before, after)
```

Never `actor`, `target`, `entity`, `outcome`, or `metadata`. Every
write operation in every engine and every page must call
`audit_log()` immediately after the write completes.

### require_access

Takes the manifest `module_path` verbatim, dotted notation. Page 108
uses `require_access("operations.cims_closure")` because the
manifest entry for `108_cims_closure.py` declares
`module_path: "operations.cims_closure"`.

### Manifest entries (G160 enforces from v10.294)

Seven required fields on every page entry in `pages/_manifest.json`:

1. `department_primary` — must be in `manifest["departments"]`
2. `module_path` — dotted, unique across all pages
3. `secondary_visibility` — list (may be empty or `["__all_admins__"]`)
4. `title` — non-empty string
5. `icon` — non-empty string (emoji)
6. `current_module_key` — non-empty string
7. `description` — non-empty string (NEW G160-enforced from v10.294)

### Tab discipline (G4)

Hard ceiling: **≤7 tabs per page.** Plan the tab layout BEFORE
writing the page. If a feature would push past 7, split into a
second page rather than cramming.

### Engine Hub admin tiers

Never add module-specific config tabs to `7_admin.py`. Use the
registry pattern: add a tier entry to `ENGINE_HUB_TIERS` with the
module name, class name, and description. Tier numbers are linear
(no reuse, no gaps); next tier is 54.

### Gate IDs

Linear, never reused. Next gate is G186.

### Standards registry

Standards are flipped from `status="planned"` /
`implementation_batch="v10.135+"` to `status="active"` /
`implementation_batch="v10.NNN"` via the locked regex pattern. With
all 330 active, this transition mostly stops being a regular
operation. New standards (if any) are added with `status="active"`
from the start, citing the activation version directly.

### Legacy-data tolerance

Pages must filter unknown record shapes and show a warning banner
rather than crashing. Never hard-key `record["field"]` without a
guard. This pattern is baked into all Phase 2A/2B pages.

### Cluster invariants

For multi-engine clusters in Phase 3 (cockpit integrations may
touch several engines at once):

- One ZIP per cluster.
- Sequential implementation, never batch standards into one ZIP.
- Return only changed files, never full repo dumps.
- Never self-grade — quote the audit script's score only.
- Run `python scripts/audit.py` before AND after changes.
- Update memory line 7 at every cluster closure.

---

## New Phase 3 rules

### UI integration is a first-class deliverable

In Phase 2, the cockpit was often deferred to arc closure under G130.
In Phase 3, **the cockpit IS the deliverable** for the cockpit
integration track. Engine work is in service of the cockpit, not
the other way around.

This means:

- Each cockpit integration arc closes with a working Streamlit page
  that calls the live engines, not with placeholder tabs.
- `require_access()` must work end-to-end with real role-gating.
- `audit_log()` calls must produce real audit records, not stubs.
- Every cockpit tab must be tested under at least one role.

### No new audit gates without a cockpit

Standalone engines are no longer the default deliverable. If a Phase
3 arc would add an engine without surfacing it in a cockpit, that's
a strong signal to either delay the engine or extend an existing
cockpit instead.

### G163 is the PG migration scoreboard

G163 currently reports 48/79 tables in PG-mode (61%). Phase 3 PG
migration progress is measured by this gate. Every PG migration
cluster updates the baseline; the gate stays green as long as the
baseline doesn't regress.

### G130 cockpit lock evolves

G130 currently locks the Risk arc UI integration from v10.208. As
Phase 3 closes additional cockpit arcs, G130 will be extended (or
new gates G186+ added) to lock each integrated arc.

### Honesty in claims

The Phase 3 pre-flight audit found stale memory ("PG at 19/52
tables") that misrepresented actual state (48/79). Going forward:

- Every batch closure cites audit script output verbatim, never
  paraphrased.
- Memory updates use audit-derived numbers, not narrative estimates.
- "Working" means the audit passes AND the cockpit renders AND the
  audit trail captures the operation — not just "engine self-test
  passes".

### Cleanup is part of the cycle

Phase 2B added engines fast and left bookkeeping debt (stale
modules, missing fields, formatting inconsistencies). Phase 3 will
allocate ~10% of each batch's effort to cleanup of debt surfaced
by deep audits. The cleanup batch (v10.294) is the first instance
of this pattern.

---

## Master prompt directives (unchanged from Phase 2B)

These directives, lifted from the user's stated preferences,
continue to govern delivery style:

- `fast #X` mode for code implementation — code only, no
  explanatory prose unless asked.
- One standard per ZIP; never batch multiple standards into one
  delivery.
- All API endpoints must have JWT auth
  (`Depends(get_current_user)`).
- Batch imports at the top of each file.
- Return only changed files.
- Never self-grade; quote the audit script's score only.
- Always run `python scripts/audit.py` before and after changes.
- Never add module-specific config tabs to `7_admin.py`; use the
  registry pattern.
- Never write directly to `performance.*` tables; use the central
  BSC integration engine.
- Prefer extending existing patterns over inventing new ones.
- Prefer ZIP delivery for code implementation.
- Prefer sequential implementation over batch.
- Provide honest, no-marketing-language reviews; value
  incremental delivery with rollback capability.
- Ask follow-up questions only when appropriate; avoid overusing
  the same emoji.
- Do not use patronizing language, sycophantic praise, or phrases
  like "let's pause" / "let's take a step back."
- Avoid clipped, list-heavy responses; prefer short paragraphs with
  varied sentence structure.
- Use writing blocks only for emails, chat messages, or social
  posts.
- Push back against harmful or incorrect ideas; keep responses
  grounded in rational thought.

---

## First Phase 3 arc — recommended

**Live Streamlit cockpit integration.**

Rationale:

- Highest-leverage deferred item — unblocks user-facing demos.
- Closes the G130 obligation that's been outstanding since v10.46.
- Tests the entire stack end-to-end (engines + manifest + access
  control + audit + tabs + PG/JSON storage) under real conditions.
- Surfaces hidden integration issues before they're buried under
  more work.
- Doesn't require a regulatory clock (unlike FATCA/CRS or CBK
  returns) so the team controls the schedule.

A reasonable first-arc target: lift the CIMS cockpit pages
(105, 106, 107, 108) from "deferred lazy-rendering" to "live data,
real-time refresh, real-role enforcement, full audit trail." Once
the pattern is proven on CIMS, replicate across Treasury, Credit,
Compliance, and the remaining arcs.

---

## Document control

- Version: 1.0 (v10.294)
- Owner: Joshua Mokua
- Replaces: Phase 2A/2B implicit rules embedded in memory and
  scattered changelogs
- Next review: after the first Phase 3 cockpit arc closes
