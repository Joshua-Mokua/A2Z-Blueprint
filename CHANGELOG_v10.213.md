# CHANGELOG v10.213 — Helper extraction: scripts/absorb_cockpit.py + COCKPIT_ABSORPTION_PATTERNS.md

**Date:** 2026-05-07
**Theme:** Clean wind-down of the v10.202–v10.212 cockpit absorption
sub-campaign. Codifies the 6 pattern variants + 13 closure-gate
refactor patterns into a reusable helper module + companion
documentation. **Single-purpose tooling batch.** Audit holds at
**160/160 PASS**.

## What v10.213 ships

### 1. `scripts/absorb_cockpit.py` (new file, ~620 lines)

Helper module exposing building blocks for cockpit-style
absorptions. Building blocks (not a one-shot CLI) because each
absorption has cockpit-specific quirks that benefit from explicit
per-batch composition.

**Public API:**

```python
extract_tab_blocks_indexed(cockpit_text, pattern=...)  # variants 3, 4, 6
extract_tab_blocks_named(cockpit_text, var_to_idx)     # variant 2
extract_render_functions(cockpit_text, fn_names)       # variant 5
extract_tab_labels(cockpit_text)                       # all variants
reindent(lines, prepend)                               # string-aware
build_manifest_aware_gate(gate_id, gate_name, department,
                            expected_imports,
                            expected_constructors,
                            ...)                       # gate refactor
```

All extraction + reindentation functions are **string-aware** by
default — handle multi-line `"""..."""` content correctly (variant 6
fix from v10.211).

The gate refactor template handles both **simple variant**
(8 of the 13 gates: G149/G151/G159/G148/G153/G155/G157/G140 — imports
+ constructors only) and **strict variant** (5 of the 13: G130/G132/
G134/G136/G138 — adds per-engine method invocation check).

**Smoke tests at end of file:** Run `python scripts/absorb_cockpit.py`
to verify all helpers work. Includes round-trip test for the
triple-quote bug fix.

### 2. `docs/COCKPIT_ABSORPTION_PATTERNS.md` (new file, ~250 lines)

Companion documentation. Documents:
- The 6 pattern variants with examples and indentation transforms
- The 2 closure gate refactor variants
- The "manifest as canonical source" principle
- When to use the helper, when not to
- Numerical summary of the campaign (13 cockpits, -1378 lines, etc.)

Reference material for future similar work + teaching context for
new contributors.

### 3. `scripts/audit.py` — `scripts/absorb_cockpit.py` added to FOUNDATIONAL

The helper's gate-refactor templates contain literal strings like
`json.loads(...read_text(...))` and `...write_text(json.dumps...)` —
the templates that the helper *generates* (not what it executes).
G2 (direct_io) regex-matches these patterns regardless of context,
so the helper file goes on the FOUNDATIONAL allowlist alongside
other meta-tools (etl_flexcube.py, audit.py itself, docgen modules).

This is the same pattern used for other code-generation tools in
the platform — they emit data-access patterns as output, not as
runtime behavior.

## Files changed (3 added + 1 modified)

```
scripts/absorb_cockpit.py                    NEW  ~620 lines  (helper module)
docs/COCKPIT_ABSORPTION_PATTERNS.md          NEW  ~250 lines  (documentation)
scripts/audit.py                             MOD  +1 line     (FOUNDATIONAL allowlist)
```

## Audit

```
Before (v10.212): Score: 160/160 gates = 100.0% — PASS
After  (v10.213): Score: 160/160 gates = 100.0% — PASS
```

Trajectory:
1. Add `scripts/absorb_cockpit.py` + `docs/COCKPIT_ABSORPTION_PATTERNS.md`
2. Run audit → 159/160 — G2 (direct_io) flags 2 violations in the
   helper's template strings (`json.loads(...read_text(...))` patterns
   inside the TEMPLATE_SIMPLE / TEMPLATE_STRICT format strings)
3. Add `scripts/absorb_cockpit.py` to FOUNDATIONAL allowlist
   (correct semantic — helper is a code-generation meta-tool, like
   audit.py itself or etl_flexcube.py)
4. Run audit → 160/160 PASS

The G2 false-positive surface area is documented in `audit.py`'s
existing FOUNDATIONAL list — every meta-tool that touches files
or generates code-that-touches-files gets exempted there. The
helper joins the same list with the same justification.

## Strategic narrative

This is the natural wind-down of a long sub-campaign. The 11-batch
sequence v10.202–v10.212 was 100% mechanical — every batch followed
the same pattern (extract cockpit body → re-indent → place in target
as nested sub-tabs → refactor closure gate → delete cockpit). v10.213
codifies that pattern into reusable tooling.

**The helper has a clear future use case:** any future deprecation
or page consolidation that follows the same shape can use the
helper's building blocks directly. Estimated savings: ~70% of the
absorption work was the mechanical pieces (extraction, re-indent,
gate template) and ~30% was per-cockpit specifics (header, engine
factory, narrative copy). The helper covers the 70%; the remaining
30% stays as per-batch composition.

**Documentation is part of the deliverable** because the patterns
are valuable beyond the immediate Python code. Future contributors
asking "how should I deprecate a page?" or "how should I refactor
a closure gate?" can read the patterns doc and understand the
campaign's accumulated wisdom without re-reading 11 CHANGELOGs.

## Honest acknowledgements

1. **The helper was not strictly necessary at this point** — the
   cockpit absorption sub-campaign is complete; there are no more
   cockpits to absorb. The helper is for hypothetical future
   similar work. Justification: (a) the patterns are in our heads
   right now; codifying them while fresh is cheap, vs reconstructing
   them in 6 months when needed; (b) the documentation has standalone
   teaching value; (c) campaign discipline says "leave the codebase
   better than you found it" and a 600-line helper + 250-line docs
   modestly does that.

2. **Smoke tests are minimal** (~30 lines at end of helper file).
   They verify the most error-prone parts: triple-quote toggle
   logic, round-trip extraction + reindentation on a synthetic
   cockpit, gate template generation. Not exhaustive — a future
   batch could add `tests/test_absorb_cockpit.py` with proper
   pytest cases. Deferred because the helper has no production
   callers yet; the audit gate ratchet (160/160) is the real
   regression test once future callers appear.

3. **`scripts/absorb_cockpit.py` exempted from G2** like other
   meta-tools. The risk: if someone misreads the helper as a
   runtime page and copies its `read_text()` patterns into a real
   page, they'd bypass the data-access discipline. Mitigation: the
   helper's docstring + the patterns doc both explicitly say
   "this generates code; the patterns it generates are intended
   for FOUNDATIONAL use only."

4. **The helper does NOT include CLI.** Considered argparse-based
   CLI but rejected because each absorption has cockpit-specific
   quirks (header design, engine factory wiring, sub-tab themes)
   that resist parameterization. The Python API is the right
   abstraction level — caller composes from building blocks.

5. **No new test file added.** Could have added
   `tests/test_absorb_cockpit.py` with proper pytest. Decided
   against because: (a) no production callers yet; (b) inline smoke
   tests at module-level run on import + on direct execution, which
   is sufficient for a single-author meta-tool; (c) test surface
   area for code-generators is awkward (test the generated code or
   the generator?).

6. **G140 simple variant inconsistency.** During v10.212, the G140
   refactor's str_replace had a partial match — the old summary
   tail wasn't included in my replacement string, leaving orphan
   code that needed a second str_replace. I noted this in v10.212's
   CHANGELOG. Looking back, the gate template in
   `build_manifest_aware_gate()` would prevent that class of bug —
   the template generates the full function including the return
   summary, so partial replacement isn't possible. Worth noting
   that the helper would have averted that 2-minute debugging
   detour.

7. **The pattern documentation could be richer.** Each variant
   could have a "before/after" example showing actual cockpit code
   becoming actual absorbed code. Deferred — current docs describe
   the shapes adequately for an experienced contributor; visual
   examples can be added if a new contributor reports difficulty.

8. **22 pre-v10.213 batches were all clean** (v10.193–v10.212).
   v10.213 makes 23 consecutive clean batches in this session.
   Cockpit absorption sub-campaign closed cleanly; helper extraction
   continued the streak.

9. **The campaign's audit-gate ratchet held throughout.** 160/160
   PASS at every batch boundary, including this one. Single
   transient regression in v10.213 (G2 from FOUNDATIONAL false
   positive) was caught + fixed in-batch via the established
   discipline (audit before AND after every change).

## What's next

With the cockpit campaign + helper extraction complete, natural
next batches:

1. **v10.214 — MD Cockpit page.** Per Joshua's standing reminder
   throughout the campaign. Aggregate Command Centre + Board Papers
   + BSC summary + Tier-1 Benchmarking + Capital snapshot +
   Management Accounts highlights + Strategic Initiatives RAG into
   a single executive surface. ~150-200 lines, single new page,
   manifest entry in strategy_performance or new "executive" dept.

2. **v10.214 — Page migration to dotted form.** Solidify v10.200's
   dotted-path access platform-wide. Per-department rollout, ~30
   lines per page × ~95 pages = sizable but mechanical batch (or
   could be split per-dept).

3. **v10.214 — Return to deferred platform items.** PG migration
   (33/52 tables remaining), API endpoints (114/136 remaining),
   test coverage expansion, FATCA/CRS XML, 5/8 CBK reports, React
   SPA (#37), React Native (#38), or Streamlit cockpit UI
   integration completion.

4. **v10.214 — Editorial reassignment review.** v10.210 demonstrated
   the editorial reassignment power (SBU + Revenue Assurance →
   Finance). Other reassignments may be worth doing now that the
   platform is structurally clean — e.g. reviewing whether
   `41_budget.py` should move from strategy → finance, etc.

I'd lean toward **option 1 (MD Cockpit)** — it directly addresses
your standing reminder throughout the campaign, creates real
user-facing value, and builds on a now-stable foundation. After
that, options 2/3/4 are all reasonable depending on what you want
to prioritize. Your call.
