# A2Z MIS 360 — Intellectual Property Strategy & Defensible IP Architecture

> **Status**: Planning document — intended to be implemented as a v8.14+ batch sequence (after Living Doc Phase 3)
> **Audience**: Future engineers + the founding inventor + a Kenyan registered patent agent + future legal counsel
> **Companion to**: `docs/A2Z_SYSTEMS_CHARTER.md`, `docs/A2Z_V7_RETROSPECTIVE.md`, `docs/A2Z_V8_RETROSPECTIVE.md`, `docs/A2Z_LIVING_DOCS_PLAN.md`
> **Discipline**: Per Charter §6 (every claim traceable) + the 38-batch honest-acknowledgement convention extended to IP claims
> **Related law**: Kenya Industrial Property Act 2001 (§21 software exclusion), EPO Article 52, US 35 USC §101 + Alice Corp. v. CLS Bank (2014)

---

## Foreword — Why this matters specifically for A2Z

A patent strategy that overclaims gets rejected. A patent strategy that underclaims leaves the platform exposed. A patent strategy that doesn't grapple with §21 of Kenya's Industrial Property Act 2001 — which excludes "schemes, rules and methods for performing mental acts, playing games or doing business, and computer programs" — wastes filing fees on applications that won't be granted.

The original IP plan from a product-strategy partner identified seven candidate inventions and proposed patenting all of them. This is the natural reflex: "we built something novel, file for patents on it." It is also, for software, frequently the wrong reflex.

This enhanced strategy starts from a different premise: **the strongest IP protection for a banking platform is multi-layered, with patents as one layer of seven.** Copyright is automatic. Trade secrets need only operational discipline. Defensive publication via the campaign's CHANGELOGs already prevents others from patenting our work. Trademark protects the brand. Contracts bind users. Selective patent filings — one or two genuinely novel combinations — provide the offensive lever where it's worth the cost.

The campaign discipline that built A2Z applies here: **document what's true, mark what isn't, file what's defensible, publish what isn't.** Sales collateral that overpromises undermines trust; patent filings that overclaim get rejected and cost money. Same pattern, different surface.

---

## Part 0 — The IP Strategy Decision Tree (NEW)

Before any patent draft, three questions decide everything else.

### Question 1: What's the actual commercial threat?

| Threat | Implication |
|---|---|
| A competitor copies our code | **Copyright** + **trade secret** are the main defenses. Not patents. |
| A competitor patents our method and sues us | **Defensive publication** prevents this. CHANGELOGs already do it. |
| A competitor independently builds a similar platform | **Trademark** (brand) + **execution discipline** are the moat. Not patents. |
| A licensee infringes our license terms | **Contracts** + **copyright** are the main defenses. Not patents. |
| A competitor blocks us from a market | **Patents** are the offensive lever — IF we filed before they did. |

Most of the realistic commercial threats to A2Z are not patent threats. The honest first question is: which of these threats actually applies?

### Question 2: Which IP mechanism gives the strongest defense per dollar?

| Mechanism | Cost per invention | Duration | Disclosure required | Strength for software |
|---|---|---|---|---|
| Copyright | Free (registration ~$45 USD) | Life + 50 yrs (KE), 70 yrs (US) | None | High (exact code) |
| Trade secret | Internal controls only | Indefinite while secret | None | Very high if maintained |
| Defensive publication | Effectively free (we already do this via CHANGELOGs) | Permanent | Full disclosure | High (blocks others) |
| Trademark | KES 25-50K KE; ~$300 USD | 10 yrs renewable | None | High (brand) |
| Contracts | Drafting cost only | Per agreement | None | Variable |
| Selective patent | KES 150-300K KE; $80-150K global | 20 yrs | Full disclosure | Variable; software is hard |

For software, copyright + trade secret + defensive publication frequently outprotect patents — at a fraction of the cost. The decision tree should privilege the cheaper layers and use patents only where they materially extend protection.

### Question 3: Is the candidate invention actually novel + non-obvious + technical?

These are the three statutory tests every patent must clear. For software, the THIRD test is the killer.

- **Novelty**: not in prior art anywhere (a single prior art document defeats it)
- **Non-obviousness**: not an obvious combination to a person skilled in the art
- **Technical effect** (EPO) / **not abstract idea** (US Alice): solves a technical problem with a technical solution, beyond merely automating a business process

The honest answer for most "AI-powered" or "ML-based" software is that the technical-effect test is hard to clear. The Alice doctrine in the US has invalidated thousands of software patents on this basis since 2014.

The decision tree's third gate: only proceed to drafting if all three tests are clearable on the specific invention as built. For most candidates listed in the original plan, this gate fails.

---

## Part 1 — The Invention Registry (Calibrated)

The original plan listed seven candidate inventions. Below they appear with honest patentability assessments and the recommended IP mechanism for each.

### Invention status markers (matching Living Docs convention)

| Marker | Meaning |
|---|---|
| ✓ Filed | Patent application submitted (none yet at v8.12) |
| ○ Drafted | Description + claims drafted but not filed |
| → Pre-draft | Prior art search not yet completed |
| ⊘ Not pursued | Decision: protect via different mechanism |

### Calibrated invention table

| ID | Name | Patent novelty | Realistic grant probability (KE) | Realistic grant probability (US after Alice) | Strongest IP mechanism | Status |
|---|---|---|---|---|---|---|
| INV-001 | Central BSC Contract Engine — 5-stage pipeline | **Weak** — generic ETL pattern; SHA-256 idempotency well-documented; hash-chained audit predates by decades (Merkle 1979) | Low | Very low (Alice) | Trade secret + copyright | → Pre-draft |
| INV-002 | Agentic Revenue Integrity — multi-agent AI with confidence handoff | **Weak** — multi-agent AI has extensive prior art; confidence-gated human handoff is in many AI products | Low | Very low (Alice) | Trade secret + defensive publication | → Pre-draft |
| INV-003 | Bi-Directional Target Cascade with ML allocation | **Moderate** — bidirectional cascade is standard ERP/S&OP; XGBoost is generic. The bank-specific KPI structure may be novel | Low-moderate | Low (Alice) | Defensive publication + trade secret | → Pre-draft |
| INV-004 | Behavioral Nudge Engine for banking | **Weak** — Thaler/Sunstein 2008; many banking nudge implementations exist | Low | Very low (Alice) | Defensive publication | → Pre-draft |
| INV-005 | Alternative Credit Scoring (M-PESA/utility) | **Weak** — crowded field: Branch, Tala, Zanifu, Migo, JUMO, etc. all have prior art. SHAP for explainability is generic ML | Very low | Very low (Alice) | Trade secret only | ⊘ Not pursued |
| INV-006 | Hybrid Origination Router | **Weak** — configurable rule engines are standard; loan routing rules are standard banking | Low | Very low (Alice) | Trade secret | ⊘ Not pursued |
| INV-007 | Value Chain Financing Orchestrator | **Weak** — C2FO and others have extensive patents in this space | Very low | Very low | Defensive publication | ⊘ Not pursued |

### Newly identified candidates (specific to A2Z's actual architecture)

These are NOT in the original seven. They reflect what the campaign actually built and what is genuinely distinctive.

| ID | Name | Patent novelty | Strongest IP mechanism |
|---|---|---|---|
| INV-008 | **Audit-locked architectural invariant enforcement for banking platforms** — 6-gate defense-in-depth perimeter (G104-G109) where architectural rules are encoded as build-time gates that fail the build on regression | **Moderate** — combination is novel; specific banking-platform application + deterministic gate-set may clear the technical-effect bar | **Selective patent (best candidate)** + defensive publication |
| INV-009 | **3-tier deterministic FLEXCUBE Anti-Corruption Layer fallback** (live → CBS-synthetic → demo defaults) with provenance-stamped output | **Moderate** — specific banking-domain application of the DDD ACL pattern; the deterministic 3-tier fallback with audit-trail provenance may be novel | Selective patent + defensive publication |
| INV-010 | **Audit-locked sales claim validation system** (the Living Doc Phase 1 work in v8.12) — registry-traced claim verification that aborts collateral generation on divergence | **Moderate** — applying the audit-lock pattern to documentation generation is novel | Defensive publication (already published via CHANGELOG_v8.12.md) |
| INV-011 | **Audit-gate-enforced PUBLISHED_LANGUAGE payload versioning** for inter-context messaging — G109 enforces payload contracts at build time across bounded contexts | **Moderate** — specific banking-platform application; combines DDD pattern with build-time gate enforcement | Trade secret + defensive publication |

The honest assessment: of 11 total candidates (original 7 + new 4), **2-3 are realistic patent candidates**. The rest are stronger via copyright + trade secret + defensive publication.

---

## Part 2 — The Patentability Calibration (the honest part)

Software patent eligibility varies sharply by jurisdiction. A strategy that ignores this wastes filing fees.

### Kenya — Industrial Property Act 2001 §21

> "The following shall not be regarded as inventions and shall be excluded from patent protection... (b) schemes, rules and methods for performing mental acts, playing games or doing business; (c) discoveries... (d) computer programs;"

Software is not patentable in Kenya **as such**. The key qualifier: "as such." Software that produces a **technical effect** beyond running a computer program — e.g. controlling a physical process, optimising hardware behaviour, securing cryptographic operations — may be patentable. Pure business-method software is not.

For each A2Z candidate: does it produce a technical effect beyond automating banking operations? For most, the answer is no. INV-008 (audit-gate enforcement) and INV-009 (deterministic ACL fallback) come closest because they affect platform behaviour at a system level.

### European Patent Office — Article 52 + Computer-Implemented Inventions

EPO requires "further technical character" beyond the running of a computer program. The bar is similar to Kenya's. EPO has granted software patents but typically for inventions tied to:
- Cryptographic protocols
- Compression/encoding algorithms
- Network protocol optimisation
- Hardware-aware compiler techniques
- Industrial control systems

A2Z is none of these. EPO patents for A2Z's candidate inventions are unlikely.

### United States — Alice Corp. v. CLS Bank (2014)

The Alice two-step framework:
1. Is the claim directed to an abstract idea, law of nature, or natural phenomenon?
2. If so, do the additional elements transform the claim into a patent-eligible application?

Pure business-method software almost always fails step 1 (abstract idea: "performing financial transactions"). Step 2 requires "significantly more" than implementation on a generic computer — typically a specific technical innovation in HOW the computer accomplishes the task.

The Federal Circuit has invalidated thousands of software patents under Alice since 2014. The viable strategy is to claim specific technical improvements in the software's operation — not the business method itself.

### Implication for A2Z

| Jurisdiction | Realistic patent grant for typical A2Z claim (e.g. "BSC pipeline") |
|---|---|
| Kenya (KIPI) | Low — falls under §21(b) and §21(d) |
| EPO | Low — lacks technical character |
| US (USPTO) | Very low — Alice abstract idea |
| China (CNIPA) | Variable — has been more accepting recently of technical software claims; expensive |
| India (IPO) | Low — Section 3(k) excludes computer programs per se |

The lesson: file fewer, more carefully. Claims that describe specific technical improvements (build-time gate enforcement, deterministic provenance-stamped fallback) clear the bar more often than claims describing the business outcome (automating BSC scoring).

---

## Part 3 — The Multi-Layered IP Protection Strategy

Patents are layer 4 of 7. Skipping the cheaper layers wastes the patent budget on protections that other layers already provide.

### Layer 1 — Copyright (automatic; register for stronger remedies)

Copyright protects the **expression** of an idea (the actual code), not the idea itself. Automatic the moment code is written. Registration is optional but provides:
- Statutory damages without proving actual harm (in the US)
- Stronger evidentiary presumption
- Required for litigation in the US

**Action items:**
- Register copyright for the canonical core modules: `utils/system_stocks.py`, `utils/system_flows.py`, `utils/system_invariants.py`, `utils/composite_scores.py`, `utils/flexcube_aggregator.py`, `scripts/audit.py`
- Register copyright for the canonical docs: `A2Z_SYSTEMS_CHARTER.md`, the two retrospectives, `A2Z_LIVING_DOCS_PLAN.md`, this strategy doc
- Cost in Kenya: KES 1,000-3,000 per work via Kenya Copyright Board (KECOBO)
- Cost in US: $45-65 per work via copyright.gov

### Layer 2 — Trade secrets (operational discipline)

Trade secrets protect anything that derives commercial value from being non-public. Indefinite duration while secrecy is maintained.

**What in A2Z is a trade secret:**
- The exact heuristics and thresholds in alternative credit scoring
- The PD/LGD calibration assumptions
- Deployment-specific FLEXCUBE configuration
- Customer-specific implementation details
- Internal benchmarks, test data calibrations

**What is NOT a trade secret (because it's public):**
- The overall architecture (charter is public on github)
- The systems-layer model (`system_stocks.py` is public)
- The audit gates (in `scripts/audit.py` which is public)
- The CHANGELOGs

**Action items:**
- Identify which modules contain genuine secrets (not just public-on-github code)
- Implement access controls for those (private branches, NDA-gated repositories)
- Add `LICENSE.md` with explicit trade-secret notice for sensitive modules
- Onboarding docs for any future engineers must include NDA + trade-secret training

### Layer 3 — Defensive publication (already happening — don't disrupt it)

Defensive publication = publishing a technical disclosure publicly with a verifiable date. This creates prior art that prevents OTHERS from patenting the same idea later. It does not protect us offensively, but it's effectively free and very effective for blocking patent troll attacks.

**A2Z already has substantial defensive publication via:**
- 32 CHANGELOG_v*.md files (each dated, github-timestamped, technical disclosures)
- `docs/A2Z_SYSTEMS_CHARTER.md`
- `docs/A2Z_V7_RETROSPECTIVE.md`
- `docs/A2Z_V8_RETROSPECTIVE.md`
- `docs/A2Z_LIVING_DOCS_PLAN.md`
- The github commit history (with author + timestamp on every change)

**Action items:**
- Continue the campaign discipline (every batch ships a CHANGELOG)
- Consider mirroring CHANGELOGs to a non-github archive for additional date evidence (e.g. archive.org, IPFS, or a notarised PDF archive)
- For each candidate invention NOT being patented, write a 2-5 page technical disclosure as a `docs/defensive_disclosures/INV-NNN.md` file

**Critical caveat — the 12-month grace period:**
- Kenya: 12-month grace period (file within 12 months of public disclosure)
- US: 12-month grace period (file within 12 months — but only the disclosure by inventor, not third parties)
- EPO: NO grace period — public disclosure before filing destroys novelty
- China: NO grace period — public disclosure before filing destroys novelty

**This means:** the github repository is a published disclosure that has already passed many EPO/China grace-period dates. Patents in EPO/China for the existing v7.x and v8.x architecture are **likely NOT possible** because the github disclosure predates any filing. This is a constraint the original plan did not flag.

For inventions where EPO/China grant matters, file BEFORE the disclosure goes public — meaning new architecture in a future v9.x would need to be filed before being committed to a public repository.

### Layer 4 — Selective patent filings (1-2 strongest candidates only)

After layers 1-3 are deployed, patents fill the offensive-lever gap. Recommend: file **at most 2** patents, on the strongest candidates only.

**Recommended candidates:**
1. **INV-008 — Audit-locked architectural invariant enforcement for banking platforms** (combination of audit gates + invariant registry + cross-cutting build-time enforcement, applied to banking domain)
2. **INV-009 — 3-tier deterministic FLEXCUBE Anti-Corruption Layer fallback** with provenance-stamped output

Both have:
- Specific technical effect beyond business automation (build behaviour, deterministic fallback semantics)
- Non-obvious combinations (the audit gate + invariant registry pattern as applied to banking is not standard)
- Concrete technical implementation (visible in the audit script and the ACL aggregator)

**Strategy:**
- File provisional in Kenya first (cost: KES 15-30K + agent fees ~KES 50K)
- Get prior-art search results + agent's grant-probability assessment
- Only proceed to PCT (~$10-20K USD) if prior-art search supports it
- Skip EPO/China unless there's a specific market reason (existing public disclosure may have already foreclosed these)

### Layer 5 — Trademark (the brand)

Trademarks protect commercial identifiers (names, logos, slogans). Cheap, indefinitely renewable, high commercial value.

**Action items:**
- Register `A2Z MIS 360` as a trademark in Kenya (KIPI Form TM 1)
- Cost: ~KES 25-50K including agent fees
- Renewable every 10 years
- Consider also: `Audit-Locked` (slogan), product visual identity (logo)

### Layer 6 — Contracts (binding what cannot be patented)

For SaaS / on-premise deployments, contracts bind users in ways patents don't. Standard agreements:
- Master Services Agreement (MSA)
- Software License Agreement (perpetual or subscription)
- Data Processing Agreement (DPA, for DPA 2019 compliance)
- Confidentiality Agreement (NDA) before any deep technical disclosure
- Acceptable Use Policy
- Terms of Service

**Action items:**
- Engage a Kenyan corporate lawyer to draft templates for all six
- These are the strongest defense against most realistic commercial threats — copy-paste, code redistribution, sublicensing without permission

### Layer 7 — Audit-locked discipline as competitive moat (the unique A2Z thing)

The pattern itself — audit-locked architectural invariants + 38 consecutive clean-first-try batches + honest acknowledgements + Living Documentation — is reproducible by others IF they invest the discipline. Most won't. The moat is **execution**, not the abstract pattern.

This is not legally enforceable IP. It is operational IP. It compounds over time: every additional batch widens the gap between A2Z and any would-be replicator.

---

## Part 4 — Defensive Publication Inventory (mapping CHANGELOGs to inventions)

The campaign already produces defensive publications continuously. This table maps existing public artifacts to the inventions they cover, so a future patent agent can confirm prior-art positions.

| Invention | Defensive publication | Date stamp | Github URL |
|---|---|---|---|
| INV-001 BSC Engine | CHANGELOG_v5.71.md (v5.71 first commit) | from git log | github.com/Joshua-Mokua/A2Z-Blueprint |
| INV-002 Revenue Integrity | CHANGELOG entries v6.x (revenue assurance batch) | from git log | same |
| INV-003 Cascade | CHANGELOG entries v6.x (cascade batches) | from git log | same |
| INV-004 Nudges | CHANGELOG entries v5.x | from git log | same |
| INV-005 Alt Credit | CHANGELOG entries v6.x | from git log | same |
| INV-006 Origination Router | CHANGELOG entries v6.x | from git log | same |
| INV-007 VCF | CHANGELOG entries v6.x | from git log | same |
| INV-008 Audit-locked invariants | A2Z_SYSTEMS_CHARTER.md (v7.0, line counts: 288) + A2Z_V7_RETROSPECTIVE.md + CHANGELOG_v7.0.md | v7.0 ship date from git log | same |
| INV-009 ACL 3-tier fallback | A2Z_V7_RETROSPECTIVE.md sections + utils/flexcube_aggregator.py | v7.10/v7.11 ship dates | same |
| INV-010 Audit-locked sales claims | A2Z_LIVING_DOCS_PLAN.md (v8.11) + CHANGELOG_v8.11.md + CHANGELOG_v8.12.md + scripts/docgen/_claim_validator.py | v8.11/v8.12 ship dates | same |
| INV-011 PUBLISHED_LANGUAGE gating | CHANGELOG_v8.7.md (G109) + audit gate G109 in scripts/audit.py | v8.7 ship date | same |

**Key observation:** for inventions INV-001 through INV-007, the defensive publication occurred during the v5.x/v6.x phases. The 12-month grace period for filing in those jurisdictions that have one (Kenya, US) likely **expired well before this strategy doc**. EPO/China grants are almost certainly foreclosed for those inventions.

**For INV-008 through INV-011** (the v7.x/v8.x architectural innovations), the disclosure window is more recent. Filing decisions need to be made within 12 months of first public disclosure to preserve grace-period rights in Kenya/US.

**Action item:** review github commit dates for INV-008 (v7.0) and INV-009 (v7.10/v7.11) — first-disclosure dates are ~6+ months ago, putting Kenya/US grace period under pressure. Filing decisions should not be delayed.

---

## Part 5 — Selected Patent Filing Plan (with honest probability)

The recommendation is to file **two patents in Kenya as provisionals**, then re-evaluate after prior-art search results.

### Filing 1 — INV-008 Audit-Locked Architectural Invariant Enforcement

**Working title**: "Method and System for Build-Time Enforcement of Cross-Cutting Architectural Invariants in a Banking Management Information Platform"

**Core technical claims to draft:**
- A method comprising defining a set of architectural rules as executable test gates within a build pipeline
- Wherein each gate corresponds to a structural property of a system component (data_source provenance, payload version, registry usage)
- Wherein build success is conditioned on every gate passing
- Wherein the gates collectively form a defense-in-depth perimeter that locks structural properties as permanent invariants
- Wherein the invariants are enforced across bounded contexts identified using domain-driven design
- Specifically applied to a banking platform with explicit gates for FLEXCUBE adapter resilience and inter-context payload versioning

**Why this might clear the technical-effect bar:**
- The invention affects build behaviour (system-level technical effect)
- It enforces structural properties that improve operational resilience (technical, not business outcome)
- The specific banking-platform gate set is non-obvious

**Honest grant probability:**
- Kenya KIPI: moderate (40-60%) — depends on agent's framing of technical effect
- US USPTO: low-moderate (20-40%) — Alice analysis is subjective; specific build-time enforcement may clear
- EPO: low (15-30%) — likely already disclosed via charter on github; further technical character argument is winnable but expensive

**Recommended action:**
1. Engage a Kenyan registered patent agent within 30 days
2. Provide the agent with: charter + relevant CHANGELOGs + scripts/audit.py + a draft technical specification
3. Agent commissions prior-art search (~KES 30-50K)
4. Decide based on results: provisional file in Kenya / abandon / refine claims

### Filing 2 — INV-009 Deterministic 3-Tier ACL Fallback with Provenance Stamping

**Working title**: "Method and System for Deterministic Multi-Tier Fallback in a Banking Anti-Corruption Layer with Provenance-Stamped Output"

**Core technical claims to draft:**
- A method for translating between a banking core's vocabulary and an internal platform's vocabulary
- Comprising a primary live-data tier, a secondary synthetic-data tier from local persistence, and a tertiary demo-default tier
- Wherein each tier produces output stamped with provenance metadata identifying which tier produced the value
- Wherein fallback occurs deterministically based on tier health signals
- Wherein health signals include retry exhaustion, circuit-breaker state, and source-data presence
- Specifically applied to FLEXCUBE-derived portfolio aggregates with a domain-specific Published Language

**Why this might clear the technical-effect bar:**
- The deterministic fallback semantics are a technical solution to an availability problem
- Provenance stamping affects observable system behaviour (auditable downstream)
- The specific multi-tier architecture is non-obvious

**Honest grant probability:**
- Kenya KIPI: moderate (40-60%)
- US USPTO: low-moderate (20-40%)
- EPO: low (15-30%) — likely already publicly disclosed

**Recommended action:** same workflow as Filing 1; bundle with the same agent for cost efficiency.

### What NOT to file (for now)

INV-001 through INV-007: defer / abandon patent route. Rely on copyright + trade secret + defensive publication. The 38-batch CHANGELOG history already serves as defensive publication preventing OTHERS from patenting these.

INV-010 (Living Doc audit-locked claims), INV-011 (PUBLISHED_LANGUAGE gating): defer until v9.x. Mark these as defensive publication (CHANGELOG_v8.7 and CHANGELOG_v8.11/12 already exist as prior art).

### Realistic budget for filings 1 + 2 — first 12 months

| Item | Estimated cost (KES) |
|---|---|
| Patent agent engagement letter + initial consult | 30,000 - 50,000 |
| Prior-art search × 2 inventions | 60,000 - 100,000 |
| Provisional patent filings × 2 in Kenya | 60,000 - 100,000 |
| Trademark filing (A2Z MIS 360) | 25,000 - 50,000 |
| Copyright registration × 6 canonical works | 15,000 - 30,000 |
| Contract drafting (MSA + license + DPA + NDA + AUP + ToS) | 200,000 - 400,000 |
| **Total — first 12 months** | **390,000 - 730,000 KES** |

This is substantially less than the original plan's "$80-150K USD for 3 inventions" and provides multi-layered protection rather than relying on patents alone.

---

## Part 6 — The Living Patent Documentation System

Mirror the Living Doc Phase 1 architecture (v8.12) — registry + claim validator + content files + audit-locked generation. Apply the same discipline to patent documentation.

### Architecture

```
patents/
├── inventions.json                           # Source of truth — invention registry
├── prior_art/
│   ├── INV-008_search.json                   # Prior art search results
│   └── INV-009_search.json
├── drafts/
│   ├── INV-008_description.md                # Patent specification draft
│   ├── INV-008_claims.md
│   ├── INV-008_drawings/                     # Mermaid sources + rendered PNGs
│   └── INV-009_*
├── defensive_disclosures/                    # Public technical disclosures for non-filed inventions
│   ├── INV-001_bsc_engine.md
│   ├── INV-002_revenue_integrity.md
│   └── ...
└── filings/
    ├── INV-008_KE_provisional_2026.pdf       # Filed application copies
    └── ...

scripts/
├── patentgen/                                # Living Patent System (v8.16+)
│   ├── _registry_loader.py                   # Reads inventions.json + prior_art/ + drafts/
│   ├── _claim_validator.py                   # Verifies patent claims trace to code or prior art
│   ├── description_generator.py              # AI-assisted description drafting
│   ├── claims_generator.py                   # AI-assisted claims drafting (review by agent required)
│   ├── prior_art_search_assistant.py         # Generates search query suggestions
│   └── filing_package_generator.py           # Assembles agent-ready filing package
└── patent_status.py                          # Like audit.py — reports filing status
```

### `inventions.json` schema

```json
{
  "_doc": "Patent invention registry; companion to docs/A2Z_IP_STRATEGY_PLAN.md",
  "_schema_version": "1.0",
  "_last_reviewed_iso": "2026-05-01",
  "inventions": [
    {
      "id": "INV-008",
      "name": "Audit-locked architectural invariant enforcement",
      "status": "pre-draft",
      "patent_strategy": "selective_patent",
      "priority": "high",
      "first_disclosure_date": "2026-XX-XX (from git log of v7.0)",
      "first_disclosure_path": "github.com/Joshua-Mokua/A2Z-Blueprint",
      "patentable_elements": [
        "6-gate defense-in-depth perimeter (G104-G109)",
        "Build-time enforcement of structural properties",
        "Cross-cutting invariants applied to banking platform"
      ],
      "source_files": ["scripts/audit.py", "utils/system_invariants.py"],
      "prior_art_search_done": false,
      "draft_path": "patents/drafts/INV-008_description.md",
      "claims_path": "patents/drafts/INV-008_claims.md",
      "filed_jurisdictions": [],
      "honest_scope": [
        "Specific banking-platform application is the novel angle.",
        "Generic audit-as-code patterns predate this; the bank-specific gate set may be the distinctive element.",
        "EPO grant unlikely due to existing github disclosure."
      ]
    }
  ]
}
```

### Patent claim validator

Same pattern as `scripts/docgen/_claim_validator.py` (v8.12), adapted:

```python
class PatentClaim:
    text: str                       # The claim language
    description_path: str           # Section in description supporting it
    code_path: str                  # File in codebase implementing it
    prior_art_distinguishing_arg: str  # How this is non-obvious vs prior art
    confidence: str                 # "strong" / "moderate" / "weak"
```

Generation aborts if any claim:
- Cites a code file that does not exist
- Cites a description section that does not exist
- Lacks a prior-art distinguishing argument

This is the patent analog of "claims must trace to the registry": **patent claims must trace to code AND to a prior-art distinguishing argument.**

### Defensive disclosure auto-generator

For inventions classified as "defensive_publication" or "trade_secret_only" (INV-001 to INV-007), generate a 2-5 page technical disclosure markdown automatically from the invention registry + the relevant source files. Each disclosure becomes a separate dated public document.

---

## Part 7 — Patent Drafting Discipline (the spirit applied)

Same discipline as the Living Doc Generation Discipline (Living Docs Plan Part 3). Six rules, adapted for patent context.

### 1. No invented capabilities

Patent claims describe what the codebase does, not what it might do. If a claim describes a feature, that feature must be in code at the time of filing. Filing on a roadmap feature is fraud and grounds for invalidation.

### 2. Prior art must be searched before drafting

The original plan listed 7 inventions without prior-art searches. This is filing for a rejection. Required workflow:
- Engage patent agent for professional search ($300-1000 USD per invention via firm)
- Or use Google Patents + USPTO + KIPI search yourself + INPADOC + Espacenet
- Document every relevant prior art finding in `patents/prior_art/INV-NNN_search.json`
- Only proceed to drafting if a non-obviousness argument can be constructed

### 3. Claims trace to specific code lines

Every claim element references a specific file + line range in the codebase. The claim validator enforces this. Examples:

| Claim element | Code reference |
|---|---|
| "a build-time gate verifying engine migration" | `scripts/audit.py:gate_engine_migration_ratchet()` |
| "a 3-tier fallback with provenance stamping" | `utils/flexcube_aggregator.py:_resolve_loan_portfolio()` + `data_source` field |

### 4. Honest scope: what the patent does NOT cover

Same as Living Doc artifacts: every patent draft has a "scope limitations" section that enumerates what the claims do NOT cover. This is for OUR records, not the filing. It prevents post-filing surprise when the agent narrows claims during prosecution.

### 5. Match canonical references

Where claims invoke standard CS / engineering patterns, cite them. Examples:
- "Anti-Corruption Layer pattern (Evans 2003)"
- "Circuit breaker pattern (Nygard 2007)"
- "Systems-thinking feedback-loop model (Meadows 2008)"
- "CBK Operations Resilience Guidelines (2019)"

This shows the prior art context and frames our innovation as a specific combination + application, not a primitive invention.

### 6. Build-time honesty over runtime polish

A claim that cannot be traced fails the validator. A diagram that cannot be sourced is excluded. A capability that's not in code is removed.

---

## Part 8 — AI Agent Capabilities (honestly calibrated)

The original plan's prompts for AI-assisted patent drafting are useful. They need calibration on what AI actually CAN and CANNOT do well.

### What AI does well

| Task | How well |
|---|---|
| Drafting the **description section** of a patent (technical disclosure) | Very well — given the codebase as input, produces 20-50 page descriptions |
| Generating **diagrams** in Mermaid / PlantUML / draw.io | Well |
| Drafting the **abstract** (150 words) | Well |
| Suggesting **prior art search terms** | Moderately — but always supplement with agent's professional search |
| Drafting **defensive disclosures** for non-filed inventions | Very well |
| **Cross-checking** claim language against description | Well — flags inconsistencies |
| **Translating** between formats (provisional → PCT → national phase) | Well |

### What AI does NOT do well

| Task | Why |
|---|---|
| **Drafting independent claims** | Claim language is legal art; AI produces plausible-sounding but legally weak claims. Agent required. |
| **Performing prior art search** | AI doesn't have access to current patent databases (USPTO, EPO, KIPI). Manual search or commercial service required. |
| **Determining inventorship** | Legal determination requiring evidence about who contributed inventively. Agent + you must decide. |
| **Strategic jurisdictional decisions** | Cost/benefit analysis depends on commercial strategy (which markets, which competitors, etc.) — outside AI scope. |
| **Prosecution responses** (office actions) | These require real-time legal argument with the examiner. Agent only. |
| **Validity opinions** | Whether a granted patent would survive challenge. Agent + litigator territory. |
| **Filing decisions** | Whether to file, where to file, when to file. You + agent decide. |

### What AI must NOT do

| Task | Why |
|---|---|
| **File a patent** | Legally requires registered agent in the jurisdiction. AI has no standing. |
| **Sign declarations of inventorship** | Legal documents require human signature. |
| **Provide legal advice** | AI can produce information; only licensed counsel provides legal advice. |
| **Make claims about likelihood of grant** to investors / regulators | AI's grant-probability assessments are heuristics; using them as legal opinions creates liability. |

### Recommended AI workflow

1. **Inventor (you) writes a 1-page invention summary** — what it does, why it's novel
2. **AI generates a draft technical description (10-30 pages)** from the summary + code
3. **AI suggests prior-art search terms** to seed the agent's professional search
4. **Patent agent runs professional prior-art search**
5. **Agent + you decide whether to proceed**
6. **AI generates draft claims** (independent + dependent)
7. **Agent reviews claims, rewrites for legal sufficiency**
8. **Agent files**
9. **Agent prosecutes office actions** (AI may help draft technical responses; agent reviews)

The AI accelerates step 2, 3, 6, and provides input for step 9. The agent is required for steps 4, 5, 7, 8, 9.

---

## Part 9 — Cost-Benefit Decision Framework

For each invention, the strategic question: is the realistic protection-value over 5 years greater than the realistic cost over 5 years?

### Cost components (per invention)

| Year | Cost component | Estimated KES |
|---|---|---|
| Year 1 | Filing + agent fees + prior art search | 100,000 - 250,000 |
| Years 2-5 | National phase filings (per country) | 50,000 - 150,000 each |
| Years 1-20 | Maintenance fees (per country) | 5,000 - 25,000/year each |
| **Total per invention over 20 years (Kenya only)** | | ~500,000 - 1,000,000 |
| **Total per invention over 20 years (PCT + 3 countries)** | | ~5,000,000 - 12,000,000 |

### Value components

| Source of value | When realized |
|---|---|
| Defensive (preventing competitors blocking us) | Year 1+ |
| Offensive (asserting against infringers) | Years 3-15 (typical) |
| Licensing revenue (selling rights) | Years 3-15 |
| Acquisition value (raising platform's enterprise value) | Year 1+ continuous |
| Marketing signal (credibility for sales) | Year 1+ continuous |

### Honest break-even analysis

For a single Kenyan filing on INV-008:
- 20-year cost: ~KES 500-1000K
- Required 20-year value: KES 500-1000K
- Realistic value sources for early-stage A2Z:
  - Acquisition signaling: high (a granted patent meaningfully raises enterprise value if A2Z is acquired)
  - Defensive: moderate (prevents one specific competitor blocking pattern)
  - Offensive: very low (litigation is too expensive for a startup; rare to monetise)
  - Licensing: very low (no buyers identified)
  - Marketing: moderate (procurement teams notice "patent pending")

**Verdict for INV-008 in Kenya only**: marginally positive. Worth filing if combined with the broader 7-layer strategy. NOT worth filing as a standalone investment.

For PCT + global (US + 2 others): cost is KES 5-12M. Required value is the same. **Verdict**: too expensive for current stage. Defer global filings until commercial traction (signed enterprise customer).

### Strategic recommendation

- **Year 1**: file 2 provisionals in Kenya (INV-008 + INV-009), no global. Total cost ~400-700K KES bundled with copyright + trademark + contract templates.
- **Year 2**: based on signed customers, decide on PCT.
- **Year 3-5**: based on PCT decisions, decide on national phase entry.

---

## Part 10 — Action Plan (Prioritized + Honest)

This replaces the original plan's "Step 1-4" sequence with a calibrated version.

### IMMEDIATE (within 30 days)

1. **Engage a Kenyan patent agent**
   - Recommended: KIPI list of registered patent agents (publicly available)
   - Budget for initial consult: KES 30-50K
   - Deliverables: shortlist of inventions with realistic grant probability after agent's preliminary review

2. **Register copyright on canonical works** (does not require an agent)
   - 6 canonical code modules + 4 canonical docs
   - Cost: KES 15-30K total

3. **Formalize trade-secret operational discipline**
   - Add `LICENSE.md` to the repo with explicit licence terms
   - Add `TRADE_SECRETS.md` listing what is confidential vs. public
   - Implement access controls on private branches if needed

4. **Engage corporate counsel for contract templates** (see Appendix A for the full inventory)
   - Tier 1 priority: 5 documents within 30 days (mutual NDA + unilateral NDA + IP Assignment + LICENSE.md + Reference Customer agreement with Ecobank)
   - Budget for Tier 1: KES 110-220K
   - Tier 2 (90 days): MSA, license, DPA 2019 compliant, Privacy Policy, ToS, AUP, Pilot Agreement (KES 320-640K)
   - Note: the **github LICENSE.md** is the most overlooked critical item. Currently the public repo has no explicit license, creating commercial-use ambiguity. Add an explicit proprietary license (template in Appendix A.1) immediately — this is a zero-cost zero-risk change with material protective effect.

### Q2 2026 (within 90 days)

5. **Prior-art search for INV-008 + INV-009** (via patent agent)
   - Budget: KES 60-100K
   - Deliverable: search report identifying relevant prior art and assessing distinguishability

6. **Decision gate**: based on prior-art search results, decide whether to file provisionals
   - If results favourable: proceed to drafting
   - If results identify defeating prior art: pivot to defensive publication only

7. **Trademark filing for "A2Z MIS 360"**
   - Form TM 1 at KIPI
   - Budget: KES 25-50K

### Q3 2026 (within 6 months)

8. **Provisional patent filings for INV-008 + INV-009 in Kenya** (if step 6 favourable)
   - Budget: KES 60-100K
   - Deliverables: filed provisionals; 12-month priority window opens

9. **Defensive disclosure publishing for INV-001 through INV-007 + INV-010 + INV-011**
   - Author 2-5 page technical disclosures
   - Publish under `docs/defensive_disclosures/` and on a permanent archive (archive.org / IPFS)

### Q4 2026 — Q1 2027 (within 12 months)

10. **Re-evaluate provisional filings**
    - 12-month window: convert to full Kenyan patent OR file PCT
    - Decision criteria: signed customer interest, competitive landscape, agent's grant-probability update

11. **Establish recurring IP review** (annually)
    - Review invention registry for new candidates
    - Update defensive disclosures
    - Renewals + maintenance fees

### Beyond 12 months

12. **Consider PCT filings if commercial traction supports it** (one or both of INV-008, INV-009)
13. **Consider US/EU national phase entries** based on customer geographic distribution
14. **Continue defensive publication via the campaign discipline** (every CHANGELOG is implicit defensive disclosure)

---

## Part 11 — Spirit Statements (IP-specific)

These are the principles every contributor to A2Z's IP strategy signs onto. They are the campaign discipline applied to legal claims.

1. **We file what we built, not what we plan to build.** A claim describing a roadmap feature is fraud and grounds for invalidation. Same as sales collateral.

2. **We document everything technical (defensive publication is automatic via CHANGELOGs).** Stop the campaign discipline and you stop the IP protection it produces. Every batch's CHANGELOG is dated public disclosure.

3. **We disclose prior art honestly in applications.** Concealing material prior art voids the patent. Patent applications are like sworn statements; honesty is non-negotiable.

4. **We treat patents as commercial decisions, not vanity exercises.** A granted patent has continuing cost (maintenance fees) and only matters if it produces commercial value. We do not file patents because we can; we file because the cost-benefit is positive.

5. **Most of what we built is not patentable.** And that's fine. Copyright + trade secret + defensive publication + execution discipline outprotect patents for software. Patents are layer 4 of 7.

6. **The audit-locked discipline is the moat. Patents are an additional lever.** The 38-batch clean-streak compounds; competitors with same patents but no execution discipline produce inferior platforms.

7. **The github repository is a published disclosure with consequences.** EPO and China have no grace period; existing public disclosure of v7.x and v8.x architecture forecloses patents in those jurisdictions. New v9.x architecture must be filed BEFORE github commit if those markets matter.

8. **Honesty in patent claims is not idealism — it is risk management.** Overclaiming triggers rejection or invalidation. Underclaiming leaves protection on the table. Calibration matters.

9. **The 12-month rule is real.** Provisional filings that turn into full applications must be done within 12 months of public disclosure (Kenya, US). Missing the window forecloses the option permanently.

10. **AI assists drafting; humans assist filing.** AI accelerates the description and abstract. Patent agents file. Mixing this up creates legal exposure.

---

## Appendix A — The Legal Document Inventory & Operational Trigger Map

This appendix expands Part 3 Layer 6 (Contracts) into the complete operational inventory. Layer 6 is where legal protection lives in practice — patents are the offensive lever, but contracts and NDAs are what protect day-to-day operations.

The user asked: do we need an NDA, and what other documents legally protect us from exploitation? The honest answer: yes to NDAs, and there are roughly 26 distinct documents over the platform's first 12-18 months, organized in four priority tiers. Only five are urgent.

### A.1 — The github LICENSE crisis (Tier 0 — IMMEDIATE)

Before any other document, address the github repository's licensing posture.

**Current state at v8.12** (per userMemories: github.com/Joshua-Mokua/A2Z-Blueprint, public): the repository is publicly viewable. If no `LICENSE` file is present, default copyright applies — under Berne Convention and Kenya Copyright Act 2001, the work is automatically "all rights reserved" to Joshua Mokua personally. Github's Terms of Service grant limited rights (viewing the repo, forking it on github), but **no rights to commercial use, redistribution, or modification** in the absence of an explicit license.

**This is paradoxically protective by default** — buyers cannot legally use the code commercially without negotiating with Joshua. But it is also commercially friction-inducing: enterprise procurement teams refuse to engage with code that has ambiguous license terms.

**Recommended actions** (one of three options, in priority order):

| Option | Description | When to use |
|---|---|---|
| **Option A — Explicit proprietary license** | Add `LICENSE.md` stating "Copyright © 2026 Joshua Mokua. All Rights Reserved. Commercial use requires written license. Contact: [email]." | **Recommended for current stage.** Maintains all rights, removes ambiguity, signals commercial-readiness. |
| Option B — Make repo private | Convert to private; share via NDA-gated access only | If keeping codebase secret matters more than defensive publication. **Loses defensive-publication protection** for future commits. |
| Option C — Dual license (AGPL v3 + commercial) | AGPL v3 for non-commercial / community use; separate commercial license for production deployments | Long-term option for community building. Complex; defer to v9.x if pursued. |

**Action**: ship `LICENSE.md` with Option A within the next batch (v8.14 candidate). The text is short enough to template:

```
PROPRIETARY LICENSE

Copyright © 2026 Joshua Mokua. All Rights Reserved.

This software, including all source code, documentation, and associated
artifacts (collectively the "Software"), is the proprietary intellectual
property of Joshua Mokua.

VIEWING THE SOFTWARE IS PERMITTED for educational and evaluation
purposes via this public github repository.

ALL OTHER RIGHTS ARE EXPRESSLY RESERVED, including without limitation:
copying, modifying, distributing, sublicensing, selling, deploying in
production environments, or creating derivative works.

Commercial use, deployment, or licensing inquiries:
[contact email]

The defensive publication of technical disclosures via this repository's
CHANGELOG files and dated commits is intentional. The presence of these
disclosures does NOT grant any rights to the Software itself.
```

This single document does more for IP protection than any patent filing would.

---

### A.2 — Tier 1: URGENT (within 30 days; before any external conversation)

These five documents must exist before Joshua has any conversation about A2Z that goes beyond what's already public on github.

#### A.2.1 — `LICENSE.md` (the github file above)

Trigger: immediate. Cost: zero. Protects against: ambiguous commercial-use claims, accidental open-source distribution.

#### A.2.2 — Mutual Non-Disclosure Agreement (NDA) template

**Why mutual not unilateral**: in any serious commercial conversation, both sides exchange confidential information. The bank discloses internal data architecture, regulatory positions, deployment constraints. A2Z discloses technical roadmaps, pricing models, customer-specific configurations. Mutual NDAs are simpler to negotiate (no asymmetry to argue about) and protect both sides.

**Required terms** (Kenyan law, English-language template):

| Element | Standard scope |
|---|---|
| Definition of Confidential Information | Information marked confidential, plus all non-public technical/commercial info exchanged in any form |
| Carve-outs | Information already public; independently developed; required to be disclosed by law (with notice) |
| Obligations | No disclosure to third parties without consent; reasonable security; use only for the stated purpose |
| Duration | 3-5 years from disclosure (5 is more conservative) |
| Return/destruction | At end of relationship, return or destroy all confidential materials |
| Equitable remedy | Specific performance / injunction available (damages alone insufficient) |
| Governing law | Kenyan law; courts in Nairobi |
| Term | NDA itself runs 1-2 years; confidentiality obligations survive termination per Duration above |

**Trigger events for using this template**:
- Conversation with a bank prospect that goes beyond marketing collateral
- Conversation with a patent agent about pre-filing strategy
- Conversation with an investor about non-public financials/roadmap
- Conversation with a potential employee/contractor about role specifics

Cost: KES 30-60K to have a Kenyan corporate lawyer draft a reusable template. Reuse it dozens of times.

#### A.2.3 — Unilateral NDA template (one-way disclosure)

**When mutual is wrong**: when only A2Z is disclosing — e.g., investor pitch where the investor is hearing many pitches and resists mutual obligations; consultant engagement where A2Z is paying for advice; technical-due-diligence sessions.

Same structure as mutual but simplified: only A2Z's disclosure obligations; receiving party agrees to confidentiality.

Cost: included with mutual template (same lawyer, ~10% additional drafting).

#### A.2.4 — IP Assignment Agreement (founder → company)

**This applies if**: Joshua has incorporated A2Z as a Limited Company (Ltd) in Kenya, or plans to. If A2Z is currently operating as a sole proprietorship (Joshua personally), this document is deferred until incorporation.

**Why it matters**: in Kenya as in most jurisdictions, IP created by an individual is owned by that individual unless explicitly assigned. If Joshua creates the codebase personally and then incorporates a Ltd, the company does NOT automatically own the IP. The company owns nothing until Joshua signs an explicit assignment.

**Investor due diligence will require this**. So will any acquirer. So will any litigation defending the IP. A founder who hasn't formally assigned IP to their own company has a structural defect in their cap table.

**Required elements**:
- Schedule listing all assigned IP (the codebase, docs, trademarks, patent rights, trade secrets)
- Explicit "all right, title, and interest" assignment language
- Effective date (preferably the company's incorporation date, with retroactive effect)
- Consideration (the equity Joshua receives in the company)
- Signed by Joshua individually + Joshua as company director (he signs both sides)

Cost: KES 30-60K, included with corporate-counsel engagement.

#### A.2.5 — Reference Customer / Design Partner Agreement (Ecobank Kenya)

**Current state per case_studies.json**: "Ecobank Kenya is the design partner... a development context, not a production deployment with measured outcomes... may_appear_in_collateral: false."

This is honest but informal. As soon as any value flows in either direction (Ecobank provides data/access, A2Z provides a working pilot), there must be a written agreement. Verbal arrangements with banks in Kenya have repeatedly led to disputes.

**Required elements**:
- Scope of access (what A2Z systems/data Ecobank can use)
- Scope of consideration (free pilot vs. paid pilot; logo usage; case-study rights)
- IP ownership of co-developed features (default: A2Z owns; Ecobank gets perpetual license)
- Term + exit terms (how either party can end the relationship)
- Data handling (which Ecobank data A2Z can see; data residency; data destruction at exit)
- Confidentiality (mutual; both sides have sensitive info)
- Liability limitations (both sides cap their exposure)
- Reference rights (does A2Z get to publicly identify Ecobank? Use the logo? When?)

Cost: KES 80-150K (negotiation-heavy document; bank's legal team will mark up A2Z's draft).

---

### A.3 — Tier 2: IMPORTANT (within 90 days; before paid customer activity)

Seven documents needed before A2Z accepts payment for production use or scales pilot to production.

#### A.3.1 — Master Services Agreement (MSA)

The umbrella commercial contract. Each subsequent agreement (license, SLA, DPA) sits beneath it as an attached schedule or exhibit.

Standard sections: parties, services, fees, payment terms, IP ownership, confidentiality, warranties (limited), indemnification, limitation of liability, term + termination, governing law (Kenya), dispute resolution (arbitration in Nairobi).

Cost: KES 100-200K for a high-quality template.

#### A.3.2 — Software License Agreement

Subscription model (annual fees, perpetual right while paying) or perpetual model (one-time fee, ongoing maintenance optional). Most enterprise software is subscription now.

Standard sections: licensed software (defined), license grant (scope + restrictions), permitted users, restrictions (no reverse engineering, no resale), updates, support, warranties, term + renewal, termination effects.

Cost: KES 60-120K (often bundled with MSA).

#### A.3.3 — Data Processing Agreement (DPA) — Kenya DPA 2019 compliant

**This is a legal requirement, not optional.** Under Kenya's Data Protection Act 2019, any processor of personal data on behalf of a controller must have a written DPA. A2Z processes bank customer data, so it is a processor under the Act.

**Mandatory contents per Kenya DPA 2019 §41**:
- Subject matter, duration, nature, and purpose of processing
- Type of personal data and categories of data subjects
- Controller's obligations and rights
- Processor obligations: confidentiality, security measures (technical + organizational), notification of breaches, sub-processor restrictions, deletion or return at end of processing
- Audit rights for controller
- Cross-border data transfer mechanisms (if applicable)

Cost: KES 60-120K. Penalties for non-compliance under DPA 2019 §72: up to KES 5,000,000 or 1% of annual turnover.

#### A.3.4 — Privacy Policy

Outward-facing notice describing what data A2Z collects (about end users, not bank customers — different document for that), how it's used, who it's shared with, retention, data-subject rights, contact for privacy concerns.

Required for any A2Z-operated surface (the website, the github account if it collects analytics, internal tools that touch personal data).

Cost: KES 20-40K (often paired with ToS).

#### A.3.5 — Terms of Service (ToS)

For any user-facing A2Z interface. Even if A2Z is currently internal-only, future SaaS surfaces or evaluation portals will need this.

Standard sections: account registration, acceptable use, fees, IP, liability disclaimer, indemnification, termination, governing law.

Cost: KES 20-40K.

#### A.3.6 — Acceptable Use Policy (AUP)

Often a section of ToS but increasingly standalone. What users may NOT do — no reverse engineering, no scraping, no use for illegal purposes, no probing security, no creating derivative competing products.

Cost: included with ToS.

#### A.3.7 — Beta/Pilot Test Agreement (Ecobank-specific or generalized)

For any pre-production deployment. Distinct from the design-partner agreement (Tier 1.5) which governs the development relationship; this governs the actual pilot.

Standard sections: pilot scope, success criteria, duration, exit conditions, data handling, support obligations during pilot, conversion to paid (or not), reference rights post-pilot.

Cost: KES 60-120K.

---

### A.4 — Tier 3: OPERATIONAL (within 6 months; before scaled production)

Seven documents needed once A2Z has paying customers and operational obligations.

| # | Document | Purpose | Trigger | Est. cost (KES) |
|---|---|---|---|---|
| A.4.1 | Service Level Agreement (SLA) | Uptime + response-time commitments | First production deployment | 60-120K |
| A.4.2 | Maintenance & Support Agreement | Ongoing support terms | Customer requesting support beyond MSA scope | 40-80K |
| A.4.3 | Subcontractor / Independent Contractor Agreement | Engaging external developers | First contractor hire | 30-60K |
| A.4.4 | Source Code Escrow Agreement | Enterprise risk mitigation | Customer requesting escrow as condition of contract | 50-100K + escrow agent fees |
| A.4.5 | Joint Development Agreement (JDA) | Co-developing features with a customer | Bank requests bespoke feature work | 80-150K |
| A.4.6 | Insurance — Professional Indemnity + Cyber Liability + E&O | Risk transfer | Production deployment with data exposure | 200-500K/year (varies) |
| A.4.7 | Reseller / Partner Agreement | Channel partnerships | Approaching a SI / consulting firm to resell | 60-120K |

Cost subtotal Tier 3: ~520K-1.13M KES + ongoing insurance.

---

### A.5 — Tier 4: MATURITY (within 12-18 months; for scale)

These documents are needed once A2Z has multiple customers, employees, and is on a fundraise / acquisition trajectory.

| # | Document | Purpose | Trigger |
|---|---|---|---|
| A.5.1 | Founder Agreement (if co-founders exist or are added) | IP assignment, vesting, departure handling | Adding any co-founder |
| A.5.2 | Vesting Agreement | Time-based equity vesting (typical 4-year, 1-year cliff) | Issuing equity to anyone |
| A.5.3 | Employment Agreement template | Hiring employees | First employee |
| A.5.4 | Employee Stock Option Plan (ESOP) | Granting options to employees | First employee with equity |
| A.5.5 | Investor-related: SAFE / Convertible Note / Equity Round | Fundraising | Accepting investor capital |
| A.5.6 | Cap Table maintenance system | Tracking equity ownership | Multiple equity holders |
| A.5.7 | Board governance documents | Multi-stakeholder governance | First external board member |

Cost varies dramatically by complexity; typical seed-stage company: KES 500K-2M for the bundle.

---

### A.6 — When each NDA flavor applies (the operational map)

The NDA question deserves specific treatment because it comes up most often.

| Conversation type | NDA needed? | Mutual or unilateral? |
|---|---|---|
| Reading the public github repo | No (LICENSE governs) | N/A |
| Reading the public CHANGELOGs | No (defensive publication) | N/A |
| Reading the canonical docs (charter, retrospectives, plans) on github | No (defensive publication) | N/A |
| Sales conversation using only published collateral | No | N/A |
| Sales conversation that reveals customer-specific roadmap, internal pricing, or non-public technical detail | **Yes** | **Mutual** (bank also reveals their internals) |
| Patent agent engagement (pre-filing) | **Yes** | Mutual or unilateral (agent is professionally bound but explicit NDA is standard) |
| Investor pitch with non-public financials/roadmap | **Yes** | Sometimes unilateral (many VCs refuse mutual) |
| Contractor engagement | **Yes** | Mutual (contractor may have their own background IP) |
| Bank pilot / production deployment | **Yes** | Mutual (covered in MSA + DPA but standalone NDA used for pre-MSA phase) |
| Reference customer conversation (existing customer talking to prospect) | Often the existing reference customer has signed reference rights in their original MSA, no separate NDA needed | N/A typically |
| Hiring conversation (employee or contractor) with someone reviewing the codebase | **Yes** | Unilateral (only A2Z disclosing) |
| Internal strategy review with corporate counsel | Counsel is professionally bound; no NDA needed for that relationship | N/A |
| Conversation with KIPI / regulatory body | Generally no NDA — official engagement | N/A |

**Default rule**: if the conversation goes beyond the public github content, an NDA is appropriate. Better to over-NDA than under-NDA.

---

### A.7 — Updated cost-benefit summary

Tier 1 (Urgent — 30 days): KES 110-220K + zero (LICENSE)
Tier 2 (Important — 90 days): KES 320-640K
Tier 3 (Operational — 6 months): KES 520K-1.13M + insurance
Tier 4 (Maturity — 12-18 months): KES 500K-2M

**Total first 18 months for full legal-document inventory**: KES 1.45M-4M, plus annual insurance.

This is a meaningful investment but it is the largest single contributor to defensible IP rights in practice. Patents are visible; contracts are operational. Most disputes never reach the patent stage; they're resolved (or not) through the contract terms.

---

### A.8 — Honest acknowledgements for this appendix

Following the campaign discipline, what this appendix deliberately does not do:

1. **Provide actual document drafts.** This appendix is a strategic inventory. The drafts must come from a Kenyan corporate lawyer engaged for that purpose. Generic templates from the internet will have gaps that surface during disputes.

2. **Predict precise costs.** Ranges are based on Kenyan corporate-legal market rates as of 2024-2025; specific quotes will vary by lawyer reputation, document complexity, and negotiation depth.

3. **Cover non-Kenyan jurisdictions.** Banks operating across multiple African markets need additional documents per jurisdiction. East African Community common-law alignment helps but doesn't eliminate the work.

4. **Address sector-specific regulations** beyond general data protection. Banking-specific regulatory contracts (CBK directives, KIPI filings) may impose additional contract requirements that bank counsel will surface.

5. **Replace the patent strategy.** This appendix is the contracts side of Layer 6. Layers 1-5 (copyright, trade secret, defensive publication, patents, trademark) are still essential and covered in Parts 1-5 of this strategy.

6. **Treat NDAs as a substitute for trade-secret discipline.** An NDA is a legal mechanism; trade-secret protection requires actual operational secrecy (access controls, confidential markings, departure handling). One without the other is weak.

7. **Cover labor law in detail.** Employment Acts, contractor classification, statutory benefits — these need specialized employment-law counsel, separate from corporate-commercial counsel.

8. **Make recommendations on entity structure.** Sole proprietorship vs. Ltd vs. partnership vs. trust — that's a tax + liability decision requiring an accountant + lawyer pair, not a strategy planning doc.

9. **Provide insurance specifications.** Insurance specs depend on revenue, customer base, data sensitivity — needs to be quoted by an insurance broker familiar with software/banking risks.

10. **Define what NDA-protected information looks like in practice.** That requires an information-classification policy (public / internal / confidential / secret) which is a separate operational document.

---

### A.9 — The path forward

**Within 30 days**:
1. Engage a Kenyan corporate lawyer (recommendation: someone with software / SaaS experience, not generic commercial)
2. Decide on the github LICENSE.md (Option A recommended)
3. Get the 5 Tier 1 documents drafted
4. If a Ltd company exists or is being formed, complete the IP Assignment

**Q2 2026**:
5. Get the 7 Tier 2 documents drafted
6. Engage with Ecobank to formalize the design-partner relationship in writing

**Q3-Q4 2026**:
7. Tier 3 documents as needed; insurance evaluation
8. First production-deployment legal package complete

**12-18 months**:
9. Tier 4 documents as the company matures

The total cost of this legal infrastructure is comparable to a single patent global filing (~KES 4M). It provides far more practical protection.

---

## Part 12 — References

### Internal — the campaign canon

| Document | Lines | Purpose |
|---|---|---|
| `docs/A2Z_SYSTEMS_CHARTER.md` | 288 | Architecture truth + first technical disclosure |
| `docs/A2Z_V7_RETROSPECTIVE.md` | 282 | v7.x technical disclosure |
| `docs/A2Z_V8_RETROSPECTIVE.md` | 364 | v8.x technical disclosure |
| `docs/A2Z_LIVING_DOCS_PLAN.md` | 588 | Living Doc planning + sales-discipline source |
| `docs/A2Z_IP_STRATEGY_PLAN.md` | this | IP strategy planning |
| `CHANGELOG_v5.71.md` through `CHANGELOG_v8.12.md` | varies | Per-batch dated disclosures |
| `Master_Prompt_v3.md` | varies | Self-extending campaign log |
| `scripts/audit.py` | ~12,800 | Truth-source for INV-008 audit-gate claims |
| `utils/flexcube_aggregator.py` | varies | Truth-source for INV-009 ACL claims |

### External — patent law canon

- Kenya **Industrial Property Act 2001** §21 (subject-matter exclusions)
- Kenya **KIPI Manual of Patent Practice** (current edition; via kipi.go.ke)
- **Patent Cooperation Treaty (PCT)** — WIPO; the international filing route
- **European Patent Convention (EPC)** Article 52 (computer-implemented inventions)
- **EPO Guidelines for Examination** Part G Chapter II (CII)
- **35 USC §101** (US patent-eligible subject matter) + **Alice Corp. v. CLS Bank** (2014) + **Mayo v. Prometheus** (2012)
- **USPTO Manual of Patent Examining Procedure (MPEP)** §2106 (subject matter eligibility)
- **Berne Convention** (copyright; automatic protection)
- **Hague Agreement** (industrial designs)
- **Madrid Protocol** (international trademarks)

### External — software-patent strategy literature

- Lemley, Mark A. (2017). "Software Patents and the Return of Functional Claiming"
- Bessen, James & Meurer, Michael J. (2008). *Patent Failure: How Judges, Bureaucrats, and Lawyers Put Innovators at Risk*
- Stallman, Richard et al. — extensive literature on free-software / copyleft + patent interactions
- WIPO Patent Drafting Manual (2nd edition, 2023) — applicable globally

### Patent search tools (free)

- **Google Patents** (patents.google.com) — broad, easy
- **USPTO Patent Public Search** (ppubs.uspto.gov)
- **Espacenet** (worldwide.espacenet.com) — EPO + worldwide
- **KIPI Online Search** (search.kipi.go.ke)
- **WIPO PATENTSCOPE** (patentscope.wipo.int)
- **The Lens** (lens.org) — academic + patent literature

### What this document deliberately does not do

- **Recommend a specific patent agent** — the choice depends on the agent's track record with software patents in the target jurisdiction and is best made after interviewing several
- **Provide legal advice** — this is a strategy document for engineering leadership; final filing decisions require licensed counsel
- **Predict grant outcomes** — grant decisions depend on examiner judgement, prior-art surfaced, and prosecution argument; probabilities listed here are heuristic
- **Cover non-IP commercial protections** — escrow agreements, source-code disclosure clauses, exit warranties, etc., which are part of broader commercial strategy

---

## Closing

The original IP plan was structurally sound but optimistic about software patentability. This enriched plan calibrates the reality and provides a multi-layered strategy that protects the platform within realistic budget constraints.

Three commitments shape this strategy:

**First**, we accept that most of A2Z is not patentable as software-as-such, and we deploy copyright + trade secret + defensive publication + trademark + contracts to cover those layers cheaply and effectively.

**Second**, we file selectively — two provisional patents in Kenya on the strongest combinations (INV-008 audit-locked enforcement, INV-009 deterministic ACL fallback) — and re-evaluate after prior-art search.

**Third**, we maintain the campaign discipline as the moat. The 38 consecutive clean-first-try batches that built the platform produce defensive publication continuously. Competitors who copy the patterns without the discipline ship inferior platforms; the gap compounds with every batch.

The patent strategy serves the platform; the platform does not serve the patent strategy.

When we proceed to v8.14, the build sequence opens: a Living Patent Documentation System (registry loader + claim validator + draft generator) mirroring the v8.12 Living Documentation Phase 1 work. Same architectural pattern, applied to a different surface.

The audit script that proves engineering integrity proves marketing accuracy proves IP-claim defensibility — the same discipline, three levels.

---

*Planning document — to be implemented as v8.14 (patent invention registry + claim validator) → v8.15 (description + claims generators + defensive disclosures) → v8.16 (admin/systems-view IP-status panel) → optional v8.17 (G110 audit gate locking patent-claim traceability). Companion to docs/A2Z_SYSTEMS_CHARTER.md, docs/A2Z_LIVING_DOCS_PLAN.md, and the v7+v8 retrospectives. References Kenyan IPA 2001 + EPO + USPTO + Berne + WIPO. The campaign that built the platform now extends its honesty discipline to patent claims.*
