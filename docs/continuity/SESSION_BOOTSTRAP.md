# SESSION_BOOTSTRAP.md

**Purpose:** orient a fresh Claude (or human collaborator) on A2Z Blueprint
in under 5 minutes. This file is the entry point â€” it does NOT duplicate
canonical artifacts; it points to them.

**Maintenance rule:** update this file at the end of each batch, alongside
the per-batch CHANGELOG. If you ship code without updating this file, the
next session will eat rediscovery tax.

---

## A2Z in 3 lines

A2Z Blueprint is an enterprise banking MIS configurable to any bank (Ecobank Kenya
is the prospect tenant): 700K simulated customers, 35 branches, 487 staff,
KES 11.5T simulated deposits. ~726,896 Python LOC (Streamlit + FastAPI) +
~1,811 TypeScript LOC (React frontend with 8 bespoke v10.496 primitives in
`frontend/web/src/components/`). 171 Streamlit pages. Constitutional governance
layer with 32 artifacts (16 .md + 16 .json pairs) in `docs/architecture/`,
mechanical audit suite with 418 gates in `scripts/audit.py`. The system is in
active development across multiple concurrent arcs (Stage C governance,
Phase 1 auth at Step 1.4, React migration, virtual bank simulation, Olympic
certification ladder).

---

## Current certified state

**Last commit on main:** `49e804f` (continuity layer; predecessor v10.498 Stage C Batch 1+1b at `5bbc669`)
**Last shipped batch:** v10.498 Stage C Batch 1+1b â€” 2026-05-22
**Governance doctrine in force:** CGR1 (reality-grounding) â€” active
**Gate count:** 418 total (verified via `grep -c '^[[:space:]]*("G' scripts/audit.py` at commit `49e804f`); G383â€“G387 ship from this batch
**G383 status:** passes (0 violations)
**G384 status:** passes (0 violations) â€” pre-existing discipline validated
**G385, G386, G387 status:** intentional FAIL (visibility-phase work backlog)

For full ledger: `docs/architecture/REVIVAL_LEDGER.md` (newest entry on top)
For current batch detail: `docs/CHANGELOG_v10498.md`

---

## Current architectural reality (CGR1-grounded)

These statements describe runtime as of commit `5bbc669`:

- **Governance Stage C is active.** Stage B (32 constitutional artifacts)
  shipped; Stage C is wiring those artifacts into enforcement gates.
  ~5/35 planned gates wired so far.
- **React migration in progress, Streamlit operational.** Both transports
  coexist. Frontend at `frontend/web/src/` (Vite + React + TS + Tailwind,
  24 TS/TSX files: 8 bespoke v10.496 primitives in `components/`, 4 pages,
  3 providers, 1 hook, lib + types). 171 Streamlit pages in `pages/*.py`.
  Migration is TRANSITIONAL, not ACTIVE. shadcn/ui pivot is ASPIRATIONAL
  per CGR1 Batch 2a — bespoke v10.496 primitives are canonical until a
  dedicated shadcn migration arc ships.
- **JWT cookie auth ACTIVE; transport-layer RBAC partial.** `utils/auth_jwt.py`
  has `create_access_token`, `get_current_user`, `require_admin`. There
  is NO `require_role` factory in `auth_jwt.py` â€” that's ASPIRATIONAL
  per CGR1. Streamlit alias `require_role` was renamed to
  `require_module_access` in v10.498 Stage C Batch 1b.
- **Virtual bank certified for Olympic simulation drills (G373).** Used
  for reproducibility checks; not production-load yet.
- **PostgreSQL migration TRANSITIONAL.** 27/52 tables migrated per G163
  baseline ratchet; remaining 25 tables still JSON-backed.
- **mlops_model_registry exists but 11 production AI engines do NOT yet
  load through it.** AI_GOVERNANCE AI1 doctrine is ACTIVE; implementation
  is TRANSITIONAL (Stage C Batch 2-3 work).
- **utils/agents/ has 4 modules (base, policies, runner, tools).** None
  declare `AGENT_SCOPE`. AI7 doctrine is ACTIVE; implementation is
  TRANSITIONAL.

When in doubt about whether something is ACTIVE or ASPIRATIONAL, consult
`docs/architecture/GOVERNANCE_REALITY_INDEX.md`.

---

## Active workstreams

1. **Stage C governance enforcement (current focus).**
   - Batch 1+1b shipped. Batches 2â€“7 pending.
   - Batch 2 candidates: G385 remediation (BrandingProvider), G386/G387
     remediation arcs, classification of remaining 28 governance
     artifacts (OI-66).

2. **Phase 1 Step 1.4+ â€” auth deepening.**
   - whoami-detailed endpoint
   - useRole() React hook canonical wiring
   - CSRF (Step 1.5)
   - verify_bcrypt.py script (Step 1.6)
   - Was originally paused to do Stage C; resume after Batch 2.

3. **React migration (TRANSITIONAL).**
   - 11 shadcn-style primitives shipped in v10.496 (Button, Card, etc.)
   - Showcase page mounted at `/components`
   - Dashboard refactored to compose primitives
   - Many pages still Streamlit-only â€” staged migration over future
     batches.

4. **Virtual bank realism (Olympic certification).**
   - G373 Olympic certification battery live
   - Used in reproducibility checks
   - Production-load scaling NOT scoped yet.

---

## Canonical artifact reading order

Read in this order to build context fast:

1. **This file** (`docs/continuity/SESSION_BOOTSTRAP.md`) â€” you're here
2. **`docs/CHANGELOG_v10498.md`** â€” what shipped most recently
3. **`docs/architecture/REVIVAL_LEDGER.md`** (top entry only) â€” current
   operational state
4. **`docs/architecture/GOVERNANCE_REALITY_INDEX.md`** â€” classification
   of every governance artifact
5. **`docs/architecture/SYSTEM_CONSTITUTION.md`** â€” doctrine; CGR1 is
   the latest article
6. **`scripts/audit.py`** â€” only when authoring or modifying gates
7. **Other `docs/architecture/*.md`** â€” on-demand by topic

Do NOT try to read everything upfront. Read what the current task needs.

---

## Top rediscovery traps

These are things sessions repeatedly get wrong. If you find yourself
making any of these assumptions, **stop and check reality first**:

1. **`require_role` factory in `utils/auth_jwt.py` is ACTIVE** (corrected
   v10.499 Stage C Batch 2a — see GOVERNANCE_REALITY_INDEX). Implemented
   at lines 391–441, returns a FastAPI Depends-compatible callable,
   case-insensitive role matching, raises 403 on insufficient role. Use
   it directly: `Depends(require_role(["MD", "Director Retail Banking"]))`.
   The Streamlit-side `require_role` alias in `utils/auth.py` was renamed
   to `require_module_access` in v10.498 Stage C Batch 1b (G383 enforces
   the no-collision invariant).

2. **Do NOT assume the Streamlit alias `require_role` still exists in
   `utils/auth.py`.** It was renamed to `require_module_access` in
   v10.498 Stage C Batch 1b.

3. **Do NOT assume the 11 production AI engines load through
   `mlops_model_registry`.** They do not. AI1 doctrine says they should;
   implementation is TRANSITIONAL.

4. **Do NOT assume `utils/agents/` modules have `AGENT_SCOPE`.** They do
   not. AI7 doctrine says they should; implementation is TRANSITIONAL.

5. **Do NOT assume the GATES list in `scripts/audit.py` is sorted purely
   chronologically.** It's mostly descending by G-number with some
   exceptions (G10463\_\* prefix block, suffixed variants like G356aâ€“G356i).
   The list opens at line ~59249 and closes at line ~59668.

6. **Do NOT add new gate function definitions AFTER the GATES list in
   `scripts/audit.py`.** Python evaluates the list at parse time; functions
   referenced in tuples must be defined BEFORE the list opens.

7. **Do NOT assume PostgreSQL is the canonical persistence backend.** Only
   27/52 tables are migrated. JSON files in `data/` are still authoritative
   for the rest.

8. **Do NOT recreate role governance registries.** Canonical is
   `data/org_hierarchy_config.json` (data) + `utils/role_taxonomy.py`
   (logic). `docs/architecture/ROLE_GOVERNANCE.md` documents what those
   say.

9. **Do NOT assume the React frontend covers all pages.** It covers a
   small showcase + Dashboard + auth screens. Most pages are still
   Streamlit (`pages/*.py`).

10. **Do NOT assume new doctrine claims are automatically ACTIVE.** Per
    CGR1: classify the claim before relying on it. Run gates to validate
    reality.

---

## Next concrete action

(Update this every session.)

**As of commit `5bbc669` (2026-05-22):**

Stage C Batch 1+1b shipped clean. Three candidate next actions:

- **A** â€” Stage C Batch 2: choose next 5 gates from planned ~30
  remaining gates. Likely focus: G385 BrandingProvider fix + G386 engine
  registration batch + 3 more gates from the artifact priorities.
- **B** â€” Phase 1 Step 1.4: resume whoami-detailed + useRole hook
  wiring + CSRF.
- **C** â€” OI-66: classify remaining 28 governance artifacts under CGR1.

Recommend reading the latest CHANGELOG entry and choosing A or B based
on what you'd find most useful next.

---

## How this file evolves

- **Every batch ship** â†’ update the "Current certified state" section
  with new commit SHA, batch number, gate count.
- **Every doctrine correction** â†’ update "Current architectural reality"
  AND add new entry to "Top rediscovery traps" if relevant.
- **Every workstream shift** â†’ update "Active workstreams" and "Next
  concrete action."

This file is supposed to be short. If it grows past ~300 lines, that's
a signal it's drifting from "orientation" into "duplicate canonical
artifact" territory â€” prune ruthlessly.

---

## Session-opening template

When starting a new chat, paste this opener:

```
I'm working on A2Z Blueprint (Ecobank Kenya banking MIS). Before we begin:

1. Read docs/continuity/SESSION_BOOTSTRAP.md from my repo at
   github.com/Joshua-Mokua/A2Z-Blueprint. That orients you to current
   state, active workstreams, and known rediscovery traps.

2. Last shipped commit: 5bbc669 (v10.498 Stage C Batch 1+1b).

3. Today I want to work on: <one-sentence description of intent>

Acknowledge that you've read the bootstrap, summarize back in 2-3
sentences what you understand about current state, then we'll begin.
```

That opener is the discipline that makes this file useful. See
`SESSION_DISCIPLINE.md` for the full session-management playbook.

---

**End of SESSION_BOOTSTRAP.md** â€” last updated: 2026-05-22, commit `5bbc669`.
