# A2Z MIS 360 — CHANGELOG v8.14

**v8.14 Living Doc Phase 2 — three generators + orchestrator + LICENSE.md**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **40th consecutive clean**
**Strategic milestone:** **🎯 LIVING DOC PHASE 2 DONE + LEGAL INFRASTRUCTURE TIER 1 OPENED.** Both sub-campaigns advance: Living Doc has 4 audit-locked artifacts; Legal Infrastructure has the operational `LICENSE.md` closing the github commercial-use ambiguity.

---

## What this batch is

**Two parallel deliverables shipped together** because they're each other's complement:

1. **Living Doc Phase 2** — Three generators + orchestrator that produce 4 audit-locked sales-grade artifacts. Per `docs/A2Z_LIVING_DOCS_PLAN.md` Part 7, this is the canonical Phase 2 deliverable (deferred from v8.13 to take the IP Strategy planning slot).

2. **Operational Tier 1 Legal — `LICENSE.md`** — Per `docs/A2Z_IP_STRATEGY_PLAN.md` Appendix A.1, the github LICENSE absence was the most urgent unaddressed item. This batch ships the proprietary license that closes the commercial-use ambiguity.

This is the first batch where both sub-campaigns advance simultaneously. Living Doc is now end-to-end functional (registries → claim validator → 4 generators → 4 rendered artifacts). Legal Infrastructure has its first operational item.

---

## What changed — Living Doc Phase 2

### `scripts/docgen/_theme.py` (~70 lines)

Shared visual constants for all 4 generators. Ocean Gradient palette per pptx-skill design guidance:

| Role | Hex | Use |
|---|---|---|
| PRIMARY | #065A82 | Deep ocean blue — title bars, section headers |
| SECONDARY | #1C7293 | Teal — accents |
| ACCENT | #21295C | Midnight — sharp callouts |
| STATUS_SHIPPED | #2F855A | Green — ✓ Shipped |
| STATUS_DESIGNED | #C05621 | Orange — ○ Designed |
| STATUS_ROADMAP | #718096 | Grey — → Roadmap |

Typography: PPT_HEADER_FONT=Calibri, FONT_HEADER=Helvetica-Bold (PDF), FONT_MONO=Courier. Helpers `status_marker()` and `status_color_hex()` consume the shipped/designed/roadmap convention.

### `scripts/docgen/_honest_section.py` (~95 lines)

Generates the **mandatory** "What this document does not claim" sections:
- `collect_honest_scope_lines()` aggregates `honest_scope` blocks across all 6 sales-content JSONs (de-duplicated, order-preserving)
- `collect_roadmap_callouts()` pulls items where status=='roadmap'
- `standard_disclaimer_paragraph()` returns the canonical intro
- `section_title()` returns the canonical heading

### `scripts/docgen/ppt_generator.py` (~530 lines)

Produces **A2Z_MIS_360_Brochure.pptx** (15 slides, 52.7KB). Slide structure:

| # | Title | Highlights |
|---|---|---|
| 1 | A2Z MIS 360 | Title with audit credentials block + verification command |
| 2 | The strategy-execution gap | 70% of strategies fail framing |
| 3 | The A2Z approach | 3-column card layout (audit-locked / systems-first / honest scope) |
| 4 | Architecture — six tiers | 6-tier architecture with numbered circles |
| 5 | Systems-layer | 4-stat callout (6 stocks / 15 loops / 3 learning / 109 gates) |
| 6 | FLEXCUBE Anti-Corruption Layer | 5 method names |
| 7 | Resilience layers | 4 numbered rows: retry + circuit + latency + restart-free admin |
| 8 | Observability triangle | 3-column with mode/circuit/latency |
| 9 | Audit perimeter — 6-gate defense-in-depth | 2-column G104-G109 |
| 10 | Regulatory alignment | check marks |
| 11 | Implementation approach | 4-phase phased rollout |
| 12 | Canonical references | Meadows + Evans + Nygard + Newman + CBK |
| **13** | **What this document does not claim** | **MANDATORY honest-scope slide with orange accent stripe** |
| 14 | Verify yourself | Dark slide with audit command in mono font |
| 15 | Next steps | 5 numbered items |

5 audit-locked claims validated. Helpers (`_add_blank_slide`, `_add_textbox`, `_add_filled_rect`, `_add_footer`) keep slide builders DRY.

### `scripts/docgen/magazine_generator.py` (~390 lines)

Produces **A2Z_MIS_360_Magazine.pdf** (11 pages, 19.7KB) via reportlab Platypus. 8 sections:

1. Cover with audit credentials table
2. Foreword (engineer-honest, not CEO-testimonial)
3. Part 1 — Platform Overview (3-callout structure)
4. Part 2 — Architecture (6-tier table)
5. Part 3 — Systems Layer (stock + loops tables)
6. Part 4 — Resilience + Observability (triangle table)
7. Part 5 — Audit Perimeter (6-gate table)
8. Part 6 — Regulatory Alignment with honest scope
9. Part 7 — Canonical References (internal canon)
10. **MANDATORY Part 8 — What this document does not claim** (disclaimer + roadmap callouts + 20 honest-scope statements)

4 audit-locked claims validated. Footer drawn on every page with version + audit gates + page number.

### `scripts/docgen/whitepaper_generator.py` (~320 lines)

Produces **2 PDFs** from the same module:

| Variant | Audience | Sections | Size |
|---|---|---|---|
| `A2Z_MIS_360_Security_Whitepaper.pdf` | CISO | auth+authz / encryption+audit / ops resilience / compliance+certifications / honest scope | 8.8KB |
| `A2Z_MIS_360_Compliance_Pack.pdf` | Regulator | regulatory alignment / engine-to-regulation mapping / 6-gate audit perimeter / honest scope | 7.3KB |

Every feature wrapped in `_shipped_box` helper that prints status marker (✓ Shipped / ○ Designed / → Roadmap) with color-coded label. Reads directly from `security_architecture.json` so e.g. SOC 2 + ISO 27001 explicitly marked roadmap with the disclaimer "A2Z does not currently hold these certifications".

### `scripts/generate_all_docs.py` (~110 lines) — orchestrator CLI

```
$ python scripts/generate_all_docs.py --out generated_docs
A2Z Living Documentation orchestrator (v8.14)
Output directory: /home/joshua/a2z/generated_docs
Targets: brochure, magazine, security, compliance

→ brochure
  ✓ generated_docs/A2Z_MIS_360_Brochure.pptx (52.7KB; 5 claims validated)
→ magazine
  ✓ generated_docs/A2Z_MIS_360_Magazine.pdf (19.7KB; 4 claims validated)
→ security
  ✓ generated_docs/A2Z_MIS_360_Security_Whitepaper.pdf (8.8KB; 2 claims validated)
→ compliance
  ✓ generated_docs/A2Z_MIS_360_Compliance_Pack.pdf (7.3KB; 2 claims validated)

Summary: 4/4 generated, 0/4 aborted
Total audit-locked claims validated: 13
```

CLI options: `--out DIR` for output directory; `--only [brochure|magazine|security|compliance]` for partial generation. sys.path patch at top so it runs as script OR module. Lazy imports so a single failure doesn't kill all. Returns exit code 1 if any target aborts.

---

## What changed — Operational Tier 1 Legal

### `LICENSE.md` (proprietary license at repo root)

Per v8.13 IP Strategy Plan Appendix A.1, this closes the github commercial-use ambiguity that v8.13 identified as Tier 0 immediate priority.

**Permitted use:**
- Viewing source + documentation in this public repo
- Forking on github (subject to github ToS)
- Citing in academic/technical/commercial discussions with attribution

**Reserved rights** (all expressly reserved):
- Copying outside this repository
- Modifying or creating derivative works
- Distributing or sublicensing
- Selling, renting, leasing
- Production deployment (commercial or non-commercial)
- Removing copyright notices

**Defensive publication notice:** explicit notice that the dated technical disclosures in CHANGELOGs + canonical docs are made public to establish prior art, but the presence of disclosures does NOT grant rights to the Software itself. The disclosures and the Software are governed independently.

**Trademarks notice** for "A2Z MIS 360" and "Audit-Locked".

**Disclaimer of warranties** with explicit notice that the audit-locked discipline reflects engineering effort but is NOT a warranty of fitness for any regulatory frame; bank-specific deployment review required for production certification.

**Limitation of liability** + **governing law** (Republic of Kenya, Nairobi courts).

Zero cost. Material protective effect. Closes the most overlooked critical item from v8.13.

---

## End-to-end smoke test (5 scenarios all green)

```
=== Scenario 1: PPT generator ===
  ✓ A2Z_MIS_360_Brochure.pptx (15 slides, 52.7KB)
  ✓ 5 audit-locked claims validated

=== Scenario 2: Magazine generator ===
  ✓ A2Z_MIS_360_Magazine.pdf (11 pages, 19.7KB)
  ✓ 4 audit-locked claims validated

=== Scenario 3: Whitepaper generator ===
  ✓ A2Z_MIS_360_Security_Whitepaper.pdf (8.8KB)
  ✓ A2Z_MIS_360_Compliance_Pack.pdf (7.3KB)
  ✓ 2 + 2 audit-locked claims validated

=== Scenario 4: Orchestrator runs all 4 ===
  ✓ Summary: 4/4 generated, 0/4 aborted
  ✓ Total audit-locked claims validated: 13

=== Scenario 5: Drift test (audit-lock fires) ===
  Corrupted claim (loops_count=100 vs registry's 15)
  ✓ validate_claims returned failed=1
  ✓ Diagnostic: "Claim '100 feedback loops (false)' diverges:
    expected 100, registry says 15 (source: utils/system_flows.py)"
  ✓ Generation would abort cleanly

=== FULL AUDIT ===
  Score: 109/109 gates = 100.0% — PASS
```

---

## ✅ Fortieth consecutive clean-first-try

40 batches in a row landing clean — v5.96 → v8.14.

A milestone — the streak now spans 9 audit-hardening batches, 6 retrospective batches, 5 sub-campaign planning batches, and 20+ engine/feature batches — all clean on first try.

---

## Comparison vs v8.13

| | v8.13 | v8.14 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Standards in UI | 62 | 62 (unchanged) |
| **Living Doc artifacts** | **0** | **4** ⭐ (Brochure + Magazine + Security WP + Compliance) |
| **Audit-locked claims operational** | **No** | **Yes** ⭐ (13 claims validated at runtime) |
| **github LICENSE** | **Absent / unclear** | **Proprietary license shipped** ⭐ |
| FOUNDATIONAL allowlist | 24 entries | 24 entries (unchanged — pre-allocated in v8.13) |
| Clean-first-try streak | 39 | **40** |

---

## Strategic narrative — both sub-campaigns advance

| Sub-campaign | Plan | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|---|
| **Living Documentation** | v8.11 ✓ | v8.12 ✓ | **v8.14 ✓** | v8.15 next (UI surface) | v8.16 G110 (optional) |
| **Legal Infrastructure** | v8.13 ✓ | **v8.14 ✓ (LICENSE.md)** | TBD (Tier 2 docs) | TBD (Tier 3 ops) | TBD (Tier 4 maturity) |

**Living Doc is now end-to-end functional.** Run `python scripts/generate_all_docs.py` to regenerate the entire collateral set; every claim validates against the registry; drift produces clean abort with diagnostic; sales claims are as audit-lockable as engineering invariants.

**Legal Infrastructure has its first operational item.** The github LICENSE absence — the most overlooked critical issue identified in v8.13 — is closed. The remaining Tier 1 items (NDA templates, IP Assignment, Reference Customer Agreement) require Joshua to engage a Kenyan corporate lawyer; the AI cannot draft binding legal documents.

---

## Honest acknowledgements

1. **WeasyPrint not available in environment** — v8.11 plan specified WeasyPrint; reality required reportlab as substitute (pure-Python, mature, available). Architecturally fine; future plan revision could update Part 2.
2. **No live Streamlit deployment verification by Claude** — script + library batch; tested via Python CLI invocation.
3. **Magazine is 11 pages not 100 as the plan aspired to** — v8.14 ships canonical 8-section structure; 100+ pages would require richer per-domain prose; that's v8.16+ enhancement.
4. **No image embedding** — generators support text + tables + colored shapes; embedding screenshots/logos requires v8.16+ image-asset pipeline (which would also require signed reference agreements).
5. **PPT slide 13 limit of 7 honest-scope items + magazine Part 8 limit of 20** — the registry contains more honest-scope statements than fit; truncation is principled (most-impactful first via list ordering).
6. **Brochure Slide 14's command output is hardcoded as PASS** — assumes audit was clean before generation; future enhancement could actually run the audit at generation time.
7. **Reportlab table widths are hardcoded for A4** — widescreen variants would need width tuning.
8. **No CSS-equivalent theme system** — `_theme.py` defines constants used directly; future redesign would change the 70-line file.
9. **Claims list is per-generator** — each of 4 generators has its own `_build_claims()`; future enhancement could centralize the manifest.
10. **LICENSE.md contact email is placeholder** — flagged inline as `[contact email — to be added by Joshua]`; needs insertion before next github commit.
11. **LICENSE.md uses Republic of Kenya governing law + Nairobi courts** — conservative default; if A2Z incorporates elsewhere (e.g. Delaware C-corp for fundraising), license needs revision.
12. **The 4 artifacts are not yet committed to repository as fixtures** — regenerable from v8.14 source on demand; that's by design (registry drift would invalidate fixtures).

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.15 Living Doc Phase 3 — admin/systems-view UI surface** | Completes canonical 2-batch + UI surface sequence per Part 7; admin section with 4 generate-buttons + status panel + audit-claim diff view; ~250 lines of pages/7_admin.py extension; 41st-clean candidate |
| (2) | v8.15 G110 audit gate 'collateral claims traceable to registry' | Locks the audit-locked claim discipline as permanent invariant; 109 → 110 gates; ~80 lines |
| (3) | Diverge to v8.6 retrospective ack | Not recommended; sub-campaigns should close before diverging |

**Strong recommendation: v8.15 = Living Doc Phase 3 (admin/systems-view UI surface)** — closes the 2-batch + UI surface sequence; lets operators trigger collateral regeneration without leaving the dashboard; 41st-clean candidate. The Living Doc sub-campaign would then have a clean 4-batch arc (v8.11 plan → v8.12 Phase 1 → v8.14 Phase 2 → v8.15 Phase 3) with optional v8.16 G110.

---

🎯 **Living Doc Phase 2 done — 4 audit-locked artifacts shipped + 13 claims validated at runtime + drift detection working. LICENSE.md closes the github commercial-use ambiguity.**

⭐ **40th consecutive clean-first-try. Both sub-campaigns now have substantive deliverables. Sales claims become as audit-lockable as engineering invariants in practice.**
