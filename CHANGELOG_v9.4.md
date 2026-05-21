# CHANGELOG v9.4 — Commercial Readiness UI surface

**Audit:** 112/112 PASS — **57th consecutive clean.**

## What

Closes the v9.1-v9.3 engine-then-UI canonical sequence by surfacing the v9.x commercial-readiness artifacts in the admin dashboard. Adds a 4th sub-tab "📜 Commercial Readiness" to the System section of `pages/7_admin.py`.

## Changes

### New sub-tab in System section

System section sub-tabs grow from 3 to 4 (G4 cap is 7; remaining headroom = 3). New tab order:
1. ⚙️ System health
2. 📤 Upload format
3. 📑 Living Documentation
4. **📜 Commercial Readiness** (new)

### Three artifact-status panels

Each panel is a collapsible expander showing files in the corresponding directory:

1. **📋 Legal templates (v9.1)** — `docs/legal_templates/`
   - Verifies presence of: NDA_MUTUAL_TEMPLATE.md, NDA_UNILATERAL_TEMPLATE.md, IP_ASSIGNMENT_TEMPLATE.md, REFERENCE_CUSTOMER_AGREEMENT_TEMPLATE.md, README.md
   - Shows file size + line count for each
   - Caption: "Not binding — require Kenyan corporate lawyer refinement"

2. **🌍 Translation prep (v9.2)** — `docs/translations/`
   - Verifies presence of: TRANSLATION_PREP_GUIDE.md
   - Caption: "Draft translations are machine-generated starting points; require native-speaker verification"

3. **📝 Patent briefs (v9.3)** — `docs/patent_briefs/`
   - Verifies presence of: INV-008_BRIEF.md, INV-009_BRIEF.md, README.md
   - Caption: "Not filed applications — require registered Kenyan patent agent"

### v9.x progress map

Markdown table showing the 6-batch v9.0-v9.5 arc with status markers. The v9.4 row says "You're looking at it" matching the v8.15 self-aware-feature pattern.

### Operator action items table

Lists 5 external-engagement actions Joshua must drive (lawyer engagement, translator engagement, patent agent engagement, LICENSE.md email insert, github LICENSE verification) with source batch + budget guidance.

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — UI compile-tested only; user runs `streamlit run app.py` to confirm new sub-tab renders.
2. **File presence checks are best-effort** — `Path.exists()` + `Path.stat()`; transient I/O errors caught silently with "Present (unreadable)" status.
3. **Imports are local to the panel** — `pandas as _ardf` and `pandas as _crpd` inside the sub-tab; `Path as _CRPath` at panel top; minor namespace pollution acceptable for the contained scope.
4. **No download buttons in this batch** — operators view file metadata; full content access requires opening files directly. Future v9.x could add download buttons (~30 lines) per file.
5. **Operator action table is hardcoded** — the 5 actions reflect v9.x plan Part 13; future plan revisions need this table updated.
6. **Caption phrasing is opinionated** — explicitly emphasizes "not binding" / "require professional review" for every artifact group; matches IP plan Part 8 honesty discipline.
7. **Sub-tab self-reference** — the v9.4 row in the progress map says "You're looking at it"; matches v8.15 pattern.
8. **G4 7-tab cap respected** — System section now at 4 of 7 max sub-tabs.

## Next: v9.5 — G113 audit gate

Verifies all v9.1-v9.3 artifacts exist:
- 4 legal templates + README in `docs/legal_templates/`
- 1 translation prep guide in `docs/translations/`
- 2 patent briefs + README in `docs/patent_briefs/`

Pushes audit suite **112 → 113 gates**. **10-gate defense-in-depth perimeter** (G104-G113). Locks the v9.1-v9.4 commercial-readiness contracts as permanent invariants.
