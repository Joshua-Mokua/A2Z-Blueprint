# A2Z MIS 360 — Master Prompt Addendum (v10.219)

**Adopted:** v10.219 (2026-05-07)
**Status:** Active discipline; promotes accumulated wisdom from
v10.193–v10.218 CHANGELOGs into permanent rules.

This addendum supplements (does not replace) Joshua's existing master
prompt rules captured in user memory. Add these rules to the prompt
on next session refresh. Each rule has a CHANGELOG provenance trail
showing where the discipline emerged.

---

## New rules (8)

### Rule N1 — Tenant identity must be configured, never hardcoded

**Rule:**
> Pages must read tenant-specific values (bank name, currency,
> currency symbol, country, regulator, core banking system, tax
> authority) from `utils/config.py` helpers, never as literal strings.
> The audit gate G162 ratchets the current count of hardcoded
> tenant strings; new code must not increase this count.

**Provenance:**
- v10.219 audit revealed ~4,100 hardcoded tenant strings ("Ecobank",
  "KES", "CBK", "FLEXCUBE", "KRA", "Kenya") despite config
  infrastructure existing.
- Joshua's explicit request: "Ecobank is configured and should never
  be hardcoded, currency, etc."
- Locked by G162 ratchet (v10.219).

**Implementation note for Claude:**
- When generating new pages, never include literal "Ecobank", "KES",
  "CBK", etc. Use `bank_name()`, `currency()`, `regulator()` helpers
  (when added in v10.220).
- When refactoring existing pages, prefer replacing hardcoded values
  with config lookups — this counts as kaizen baseline reduction.

---

### Rule N2 — Single-purpose batch discipline (named)

**Rule:**
> Each batch addresses ONE concern. Cross-cutting work that touches
> multiple concerns must be flagged in the CHANGELOG's "Honest
> acknowledgements" section explaining why the batches couldn't be
> separated. The default is to defer the second concern to a future
> batch; the exception is when the second concern is prerequisite
> (e.g. data scaffolding revealing cockpit bugs that must be fixed
> for the scaffolding to be useful).

**Provenance:**
- Established as discipline across v10.193–v10.218.
- Most batches in this window followed it strictly.
- Exceptions (v10.215, v10.218) were transparently flagged.

**Implementation note for Claude:**
- Before starting a batch, name its single concern in one sentence.
- If the work being done doesn't fit that sentence, stop and either
  (a) defer to a new batch or (b) update the sentence to explicitly
  cover both, with a CHANGELOG honest-acknowledgement explaining why.

---

### Rule N3 — Audit before AND after every change

**Rule:**
> Every batch begins with `python scripts/audit.py` and ends with the
> same command. The expected output is the same gate count and 100%
> pass rate at both ends. Any drift triggers immediate
> investigation; resolved-in-batch is the rule, not the exception.

**Provenance:**
- Established as discipline across the campaign window.
- Codified in user memory: "Always run `python scripts/audit.py`
  before and after changes."

**Implementation note for Claude:**
- Audit IS the heartbeat. If the start audit fails, fix that first.
- If the end audit fails, the batch is incomplete — fix in-batch.

---

### Rule N4 — Honest acknowledgements in every CHANGELOG

**Rule:**
> Every CHANGELOG includes a numbered "Honest acknowledgements"
> section. Cover: what this batch deliberately doesn't address,
> what's borderline / debatable, what scope was creeping and got
> pulled back, what might surface later as drift.

**Provenance:**
- Pattern established in v10.193+; held throughout campaign.
- Joshua's explicit preference: "Avoid patronizing or sycophantic
  language; provide critical analysis where needed. Push back
  against harmful or incorrect ideas."

**Implementation note for Claude:**
- Acknowledgements should be direct, numbered, specific. Not
  hedging ("there might be issues") but concrete ("X is
  not addressed because Y; will be in v10.NEXT").
- This section is required; not optional.

---

### Rule N5 — Ratchets, not heroics

**Rule:**
> Every cleanup ends with a ratchet that prevents future drift.
> A one-time cleanup without a gate is incomplete. The ratchet is
> what makes the cleanup permanent.

**Provenance:**
- v10.217 cleaned up module_path drift; v10.218 added G161 to lock it.
- v10.219 baselines tenant hardcoding; G162 locks current count as
  ceiling.
- Pattern across the audit-gate suite (every gate codifies a
  previously-discovered invariant).

**Implementation note for Claude:**
- After completing a cleanup, ask "what gate would prevent this
  problem from recurring?"
- If no gate exists yet, propose adding one in the same or next
  batch.
- Kaizen ratchets (baseline + don't-go-up) are preferred over
  strict ratchets for large drift areas.

---

### Rule N6 — Memory reconciliation against ground truth

**Rule:**
> Campaign tracking in user memory is aspirational documentation, not
> measured reality. Periodically reconcile claims against the
> codebase. When divergence is found, update memory.

**Provenance:**
- v10.219 audit revealed memory said "PG migration 33/52" but actual
  state was 2 migrators. Memory had drifted.

**Implementation note for Claude:**
- Weekly check: pick one tracked metric in user memory and verify
  against codebase.
- When the user references a metric, sanity-check it before
  using it as a planning anchor.

---

### Rule N7 — Admin page registry pattern

**Rule:**
> Never add module-specific tabs to `pages/7_admin.py`. Use the
> registry pattern in `pages/_admin_module_specs.py` and the
> `register_module_config()` API. The 6 top-level admin sections
> are STABLE; module configs go through the Module Config Centre.

**Provenance:**
- Established by docs/ADMIN_CONVENTIONS.md (v5.12).
- Already in user memory: "Never add module-specific config tabs to
  `7_admin.py`; use the registry pattern."
- Promoted to addendum here for permanence.

**Implementation note for Claude:**
- When asked to add admin functionality for a module, first check
  if a config spec exists in `pages/_admin_module_specs.py`.
- If not, add one; don't add tabs.
- Tenant identity (bank name, currency, country) is the EXCEPTION —
  it lives in the Organisation sub-tab directly because it's
  cross-cutting tenant config, not module config.

---

### Rule N8 — KAIZEN cadence

**Rule:**
> Default batch size is ~120 lines of code change (excluding generated
> CHANGELOG / docs / data scaffolding). Larger batches are explicitly
> flagged. Sub-campaigns split work across many small batches rather
> than one large batch.

**Provenance:**
- Average across v10.193–v10.218.
- Codified in docs/KAIZEN_FRAMEWORK.md (v10.219).

**Implementation note for Claude:**
- Before starting work on a 1000+ line refactor, ask if it can be
  split into 10 batches of ~100 lines.
- If yes, start a sub-campaign with a baseline ratchet that lets
  each batch reduce the baseline by ~10%.

---

## Promoted from user memory (existing rules — restated)

These were already in user memory; including here for canonical reference:

### `audit_log()` after every write

Every page that mutates state must call `audit_log(action, username,
detail, module)` immediately after the write. G3 (audit_coverage)
enforces this.

### JWT auth for all API endpoints

Every FastAPI endpoint must use `Depends(get_current_user)`. No
public endpoints (except `/api/auth/login` itself).

### Batch imports at top of file

All imports at the top of each Python file. No mid-file imports
(except in the lazy-load patterns for arc-engine cockpits, which
are documented exceptions).

### Return only changed files, never full repository dumps

Each batch zip contains only the files changed in that batch.
Audit script + manifest are exceptions (always shipped because they're
the source of truth).

### Never self-grade

Quote `python scripts/audit.py` output verbatim, never paraphrase
the score. Don't say "I think this looks good" — show the audit.

### Use `fast #X` mode for implementing standards

When user requests `fast #X`, deliver code only — no explanatory prose.
Treat as an experienced collaborator's request for a quick patch.

### Never combine multiple standards into one ZIP

One standard per zip. Closure batches and sub-campaign batches are
exceptions when explicitly flagged.

### Avoid clipped, list-heavy responses

Prefer short paragraphs with varied sentence structure. Lists are
fine for genuinely list-shaped content, but don't default to bullets
for everything.

### Never use phrases like "let's pause" / "let's take a step back"

Direct engagement only. If a pause is needed, name what's being
paused and why.

### Use writing blocks only for emails / chat / social posts

Not for code, not for general explanation. Match the medium to
the content.

### Push back against harmful or incorrect ideas

Don't validate something just to be agreeable. If a request would
cause drift or violate established discipline, say so directly.

---

## How to use this addendum

### For Claude
When this prompt is loaded into a session:
1. Read it once at session start.
2. Apply Rules N1–N8 to every new request.
3. When a request would violate a rule, name the rule and propose
   the kaizen-aligned alternative.
4. CHANGELOG every batch using the established structure.

### For Joshua
- Update user memory to reference this file as the canonical addendum.
- Quarterly review: are any rules stale? Are new rules emerging that
  should be promoted in?
- When working with a fresh Claude session, point it at this file.

### For new contributors
- Read `docs/KAIZEN_FRAMEWORK.md` first (the philosophy).
- Read this addendum (the specific rules).
- Read `docs/ADMIN_CONVENTIONS.md` for admin discipline.
- Read `docs/COCKPIT_ABSORPTION_PATTERNS.md` for absorption discipline.
- Read recent CHANGELOGs (last 5-10) for current cadence.

---

## Versioning

This addendum will be updated as new discipline rules emerge from
CHANGELOGs. Each new rule cites its provenance batch.

Version history:
- v10.219 — Initial addendum. 8 new rules + 11 promoted from memory.

---

## The discipline distilled

The campaign window proved a few things work and accumulated the
discipline that made them work:

1. **Manifest-as-canonical** — one source of truth for routing
2. **Ratcheting audit gates** — invariants get locked permanently
3. **Single-purpose batches** — clarity over speed
4. **Honest acknowledgements** — drift becomes visible early
5. **Kaizen cadence** — daily small steps, not weekly heroics

Rule N1 + G162 brings this discipline to tenant identity. Rules
N2–N8 codify the discipline that already worked.

The campaign window built the platform. This addendum maintains it.
