A2Z MIS 360 — v5.41 release notes
===================================
STANDARD #14: Peer Learning Network — CLOSED
Audit: 25/25 gates, 100% (G25 added)
Tests: +38 (test_peer_learning.py) → 18 files / 409 tests total
Live volume: 30 cards / 2026-W18 (spec target ≥5)

THE HONEST READING:
The spec hand-waves on "patterns.key_tactics" — there's no truthful
way to extract tactical advice ("I call clients at 7am") from
observable data. So the engine produces what we CAN honestly
assemble: WHO the top performers are, WHAT we observe about them
(measurable patterns), HOW to engage them (conversation invitations,
not fake content). Engine deliberately refuses to fabricate.

DELIVERED:
1. utils/peer_learning.py — PeerLearningNetwork with three paths:
   a) share_best_practice(staff, kpi, period) — spec entry
   b) match_for_skill(skill, requesting_staff) — composes with #12
   c) generate_weekly_cards / generate_weekly_skill_cards — batch
   Filter: ≥110% achievement to qualify for KPI cards.
   Card IDs deterministic via SHA1 (idempotent).
2. scripts/generate_learning_cards.py — weekly driver.
   Discovers KPIs from target_cascade.json (real shape:
     <from_code>|<kpi>|<year> keyed with allocations list).
   Falls back to skill-axis batch when KPI cards <5.
3. scripts/audit.py G25 peer_learning_volume — enforces ≥5/week
4. tests/test_peer_learning.py — 38 tests

TWO MID-BUILD FIXES:
- Cascade shape: rewrote _default_kpi_leaderboard,
  _default_target_lookup, _discover_active_kpis
- Wording: split _observe_skill_patterns into _targeted ("above your
  level") vs _general ("Top assessed level on...") so weekly cards
  don't say "above your level" when no requester is set.

ARCHITECTURAL PAYOFF — V2 ENGINES COMPOSING:
- #11 (nudges) recognises perf via achievement_pct ≥110%
- #12 (growth paths) materialises skill_gaps per staff
- #14 (peer learning) USES BOTH: KPI cards filter by ≥110% (#11
  threshold), skill cards consume staff_skills.json (#12 seed)
Engines decoupled at runtime, data products compose naturally.

INSTALL: extract over v5.40, run audit, run driver, re-run audit.
ROLLBACK: restore scripts/audit.py.v5.40.bak; delete new files.

git add scripts/audit.py scripts/generate_learning_cards.py \
        utils/peer_learning.py \
        tests/test_peer_learning.py \
        Master_Prompt_v3.md
git commit -m "v5.41: Standard #14 PeerLearningNetwork + G25"
git tag v5.41
