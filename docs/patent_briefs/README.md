# Patent Briefs — A2Z MIS 360

> **Status**: PRE-FILING TECHNICAL DISCLOSURES — FOR REGISTERED PATENT AGENT REVIEW
> **Shipped in**: v9.3 (May 2026)
> **Companion to**: `docs/A2Z_IP_STRATEGY_PLAN.md` (v8.13) — specifically Part 5 (Selected Patent Filing Plan) and Part 8 (AI Agent Capabilities)
> **Audience**: Kenyan registered patent agent + Joshua

---

## What this folder is

Per the v8.13 IP Strategy Plan, two A2Z inventions are recommended candidates for Kenyan provisional patent filing:

- **INV-008** — Audit-Locked Architectural Invariant Enforcement
- **INV-009** — Deterministic Three-Tier Anti-Corruption Layer Fallback

This folder ships **technical disclosure briefs** for each invention. The briefs are starting points for a registered Kenyan patent agent to:

1. Conduct professional prior-art searches
2. Refine the technical scope and claim language
3. Determine grant probability across jurisdictions
4. Prepare provisional patent applications

The briefs are **NOT**:

- Filed patents (provisional or otherwise)
- Legal opinions on patentability
- Substitutes for professional prior-art searches
- Defensible against patent prosecution challenges without lawyer refinement

Per v8.13 Part 8 ("AI Agent Capabilities calibrated honestly"), AI is well-suited to:
- Drafting technical disclosure (description sections)
- Identifying candidate prior art categories
- Suggesting search terms
- Articulating distinguishing arguments

AI is **NOT** suited to:
- Performing professional prior-art searches (no real-time access to current patent databases)
- Drafting legally-sufficient claims
- Determining inventorship
- Filing or prosecuting applications
- Providing legal opinions on grant probability

These briefs sit firmly in the "AI capable" category. The agent provides the professional capabilities that follow.

---

## The two briefs

| File | Invention | Primary technical effect |
|---|---|---|
| `INV-008_BRIEF.md` | Audit-Locked Architectural Invariant Enforcement | Build-time enforcement of cross-cutting structural properties via deterministic gate-set |
| `INV-009_BRIEF.md` | Deterministic Three-Tier Anti-Corruption Layer Fallback | Provenance-stamped multi-tier fallback for banking ACL with deterministic semantics |

Both briefs follow the same structure (per WIPO Patent Drafting Manual conventions):

1. **Field of the invention**
2. **Background of the invention** (problem statement)
3. **Summary of the invention**
4. **Detailed description** (with code references to the A2Z codebase)
5. **Suggested independent + dependent claim language**
6. **Suggested prior-art search categories and terms**
7. **Identified distinguishing arguments**
8. **Honest grant-probability calibration per jurisdiction**
9. **References to A2Z codebase**
10. **Defensive publication chain** (proving prior public disclosure dates)

---

## Suggested patent agent engagement workflow

1. **Joshua engages a Kenyan registered patent agent** with software/SaaS experience. KIPI maintains the official register of patent agents.

2. **Initial consultation** (~KES 30-50K). Joshua delivers:
   - This folder (both briefs + this README)
   - The v8.13 IP Strategy Plan
   - Read access to `github.com/Joshua-Mokua/A2Z-Blueprint`

3. **Agent reviews briefs and confirms scope.** If the agent identifies issues with the technical disclosure, scope, or grant probability, Joshua addresses the feedback.

4. **Agent commissions prior-art search** (~KES 30-50K per invention). Search covers:
   - Google Patents / USPTO / Espacenet / WIPO PATENTSCOPE / KIPI
   - Academic literature (IEEE, ACM, arXiv)
   - Industry publications and blogs
   - Open-source projects with similar patterns

5. **Decision gate.** Based on prior-art search results, Joshua + agent decide whether to:
   - **File** provisional in Kenya for one or both inventions
   - **Refine** the inventions to distinguish from surfaced prior art
   - **Abandon** patent route and rely on copyright + trade secret + defensive publication

6. **If filing proceeds** (~KES 60-100K per invention provisional), agent drafts and files the provisional. The 12-month priority window opens.

7. **Within 12 months**, Joshua + agent decide whether to:
   - Convert provisional to full Kenyan patent
   - File PCT (international) for global protection
   - Allow provisional to lapse

Total budget (per v8.13 plan recommendation):

| Item | Cost (KES) |
|---|---|
| Agent engagement + initial consultation | 30-50K |
| Prior-art search × 2 | 60-100K |
| Provisional filings × 2 (if proceeding) | 60-100K |
| Trademark filing (parallel) | 25-50K |
| **Year 1 budget** | **~175-300K** |

This is substantially less than full PCT global filing (~$80-150K USD per invention) while preserving the 12-month decision window.

---

## What this folder does NOT contain

1. **Filed applications.** No PDF or USPTO-filed copies; those exist only after the agent files them.
2. **Patent claims as legal text.** The briefs include "suggested claim language" as starting points; real claim drafting is the agent's responsibility.
3. **Prior-art search results.** Those are the agent's deliverable.
4. **Inventorship analysis.** Joshua + agent determine inventorship; documented separately.
5. **Costs of foreign filings.** v8.13 plan recommends Kenya-only Year 1; foreign filings deferred pending commercial traction.
6. **Inventions INV-001 through INV-007 + INV-010 + INV-011.** These are NOT recommended for filing per v8.13 Part 5; they're handled via defensive publication (CHANGELOGs already serve as dated public disclosure).

---

## Honest acknowledgements

1. **Briefs are pre-search.** Without professional prior-art search, grant probability is speculative. Agent's search may surface defeating prior art that requires invention refinement or abandonment.
2. **Suggested claim language is non-legal.** Real claim drafting requires patent agent's professional language familiar with KIPI examiner conventions.
3. **Distinguishing arguments may be incomplete.** Agent's prior-art search may identify references the briefs didn't anticipate; new distinguishing arguments may need development.
4. **Jurisdiction analysis is conservative.** Briefs note Kenya-IPA-2001 §21 and EPO Article 52 and US Alice doctrine concerns. Agent's professional opinion may differ.
5. **Github disclosure is acknowledged.** Per v8.13 Part 4, the public github repo (since v7.0) likely forecloses EPO and China grants for existing architecture (no grace period). Briefs acknowledge this; agent verifies.
6. **Briefs cite A2Z codebase paths.** If those paths refactor in v9.x, briefs need version-locking. The audit-locked discipline ensures the underlying invention claims remain traceable.
7. **No commercial-value analysis.** Whether the inventions justify filing cost depends on commercial trajectory. v8.13 plan analysis stands; agent + Joshua re-evaluate at decision gate.
8. **No inventor declaration drafted.** v9.x candidate; agent provides standard inventor declaration form for Joshua's signature.

---

*v9.3 — Patent briefs README. Companion to docs/A2Z_IP_STRATEGY_PLAN.md Parts 5 + 8. Pre-filing technical disclosures for registered patent agent review.*
