# Store & Push Discipline — preventing "works here / off at the bank"

**Owner:** Joshua Onyancha Mokua (KE1347) · **Collaborator running production:** Alex
**Created:** 2026-08-05 · **Status:** ACTIVE doctrine

## Why this exists

A2Z is a **half-migrated** system: some data lives in PostgreSQL (DB-first), some in ~130 JSON
files. Separately, some git-tracked config is **site-defined** (Alex configures it at the bank).
Two failure modes caused recurring "it works on my machine but is off at the bank" drift:

1. **DB-first data doesn't travel via git.** Editing the JSON for a DB-first table has no effect
   (the API reads Postgres); and the DB itself never travels on push. Your DB ≠ Alex's DB.
2. **Site-defined config that travels via git clobbers Alex's work.** A whole-file push of a
   config Alex customizes (e.g. product_flows) overwrites his configuration on his next pull.

This doc classifies every store and states the delivery rule for each. **Check it before pushing.**

---

## Bucket 1 — DB-FIRST tables (Postgres is truth; data does NOT travel via git)

Reads hit Postgres first (`_PIPELINE_READ_DB_FIRST`, `table_uses_db()` where `TABLE_USE_DB[t]=True`).
JSON files of the same name are legacy fallback only.

Key DB-first tables: `pipeline_deals`, `users`, `bsc_scores`, `loan_applications`, `bank_targets`*,
`referrals`, `projects`, `credit_admin`, `collateral_register`, `disciplinary`, `audit_trail`,
`edms_documents`, `lms_enrollments`, `execute_initiatives`, `staff_history`, `treasury_fd/fx`,
`trade_finance`, `compliance_cases`, plus ~30 more (see `TABLE_USE_DB` in `utils/db.py`).

**RULE:**
- Never edit the JSON for these expecting a runtime effect — the running API ignores it.
- To change this data on YOUR machine: use the API or a DB script.
- To deliver to Alex: a **SQL / seed script he runs against HIS database**, or via the API.
  Never assume a git push moves this data — **it does not travel.**
- Instrument first: `curl` the live API or query Postgres before reasoning about the file.

\* `bank_targets` is a KNOWN LATENT BUG: `TABLE_USE_DB['bank_targets']=True` but the Postgres
   table does not exist, so it silently falls back to JSON. Resolve deliberately: either create
   + migrate the table, or set the flag to False. Until then, the JSON is the live source.

---

## Bucket 2 — SITE-DEFINED config (per-site; must NOT travel as a whole file)

Alex configures these at the bank (admin UI / seed scripts). They are `skip-worktree` (S) or
gitignored, so they stay per-site.

| File | State | Why per-site |
|---|---|---|
| `data/pipeline_settings.json` | S | product_flows, committee_routing, sla_config, customer_segments — all admin-configured |
| `data/lms_config.json` | S | committee palette, LMS config — seeded per site |
| `data/org_config.json` | S | branches, regions, hierarchy — Alex maps DSA regions |
| `data/org_hierarchy_config.json` | S | role tiers, span-of-control, chief mapping — bank-tuned |
| `data/kpi_library.json` | S | role_kpis, pillar/kpi weights — configured via admin |
| `data/role_default_targets.json` | S | per-role quarterly targets — site-specific |
| `data/target_cascade.json` | gitignored | per-staff targets — per site |
| `data/users.json` | gitignored | logins/roster — per site |
| `data/reporting_lines.json` | gitignored | per site |
| `data/unit_map.json` | gitignored | per site |

**RULE:**
- Never push these as whole files. Your local edits won't stage (S) or are ignored.
- To deliver a change to Alex: write a **MERGE script** (pattern: `seed_committee_palette.py`)
  that reads his existing file, updates ONLY the specific key(s), writes back — preserving all
  his other config. He runs it on his site.
- **skip-worktree is per-clone.** Alex must set it on HIS clone too (one-time), or a pull can
  still overwrite his file. See "Alex one-time setup" below.

---

## Bucket 3 — SHARED / STATIC config (travels via git; safe to push)

Static reference data both sides share; improvements SHOULD travel.

- `data/products.json` (H) — fixed product catalogue (rates, books)
- `data/product_registry.json` (H) — currently empty
- Static keys inside otherwise-shared files (deal_types, sectors, probability_map, client_types)
- All source code

**RULE:** normal `git add` / `commit` / `push`. Targeted `git add <file>` only, never `-A`.

---

## Alex one-time setup (hand this to Alex once)

On his clone, so his per-site configs are preserved on pull:

```
git update-index --skip-worktree data/pipeline_settings.json
git update-index --skip-worktree data/lms_config.json
git update-index --skip-worktree data/org_config.json
git update-index --skip-worktree data/org_hierarchy_config.json
git update-index --skip-worktree data/kpi_library.json
git update-index --skip-worktree data/role_default_targets.json
git ls-files -v -- data/pipeline_settings.json data/lms_config.json data/org_config.json data/org_hierarchy_config.json data/kpi_library.json data/role_default_targets.json
```
(each should show `S`). The gitignored files need no action.

---

## Pre-push checklist (run before every push to the bank)

1. Am I changing DB-first data? → NO file push moves it. Deliver a SQL/seed/API change instead.
2. Am I changing a site-defined config (Bucket 2)? → NO whole-file push. Write a merge script.
3. Am I only changing code or shared/static config (Bucket 3)? → normal targeted push is fine.
4. `git status` — confirm only intended files are staged. Never `git add -A`.
5. For frontend: `pushd frontend\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT` before commit.

---

## Root principle

**Site-specific runtime state must never be a shared, whole-file git artifact.** If Alex can
change it at the bank, or if it lives in the DB, it does not travel — it is delivered as a
targeted script he runs. Code and static reference data travel; live state does not.
