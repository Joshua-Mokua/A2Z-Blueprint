# Legal Templates — A2Z MIS 360

> **Status**: DRAFT TEMPLATES — NOT BINDING — FOR KENYAN CORPORATE LAWYER REFINEMENT
> **Shipped in**: v9.1 (May 2026)
> **Companion to**: `docs/A2Z_IP_STRATEGY_PLAN.md` Appendix A.2 (Tier 1 — URGENT documents)
> **Convention**: Same audit-locked discipline as Living Doc and CHANGELOG artifacts — every claim in these templates is either standard legal boilerplate (cited) or honestly flagged as needing professional review.

---

## What this folder is

Per the v8.13 IP Strategy Plan Appendix A.2, A2Z needs five Tier 1 legal documents within 30 days of beginning external commercial conversations. The plan stated:

> "AI cannot draft binding legal documents but can produce drafts for the lawyer to refine."

This folder ships exactly that — well-structured starting drafts that materially reduce the cost of engaging a Kenyan corporate lawyer. The lawyer's role is to:

1. Verify Kenyan-law conformance (Industrial Property Act 2001, Data Protection Act 2019, Companies Act 2015)
2. Adjust definitions and operative clauses to match Joshua's specific circumstances (sole proprietorship vs Ltd, contemplated transactions, etc.)
3. Add or remove clauses based on negotiation posture
4. Provide professional indemnity for the final binding versions

The lawyer is not starting from a blank page — these templates capture standard Kenyan commercial-legal conventions and the v8.13 IP Strategy Plan's specific recommendations.

---

## What this folder is NOT

1. **Not legal advice.** No clause in any template should be treated as legal advice. Joshua needs licensed counsel before signing anything based on these templates.
2. **Not Kenyan-law-validated.** Every clause is plausible by Kenyan-corporate-legal convention but has not been reviewed by a Kenyan advocate. There may be conflicts with current statute or case law that only a lawyer would catch.
3. **Not customized.** Templates use placeholder names (`[A2Z PARTY]`, `[OTHER PARTY]`, `[DATE]`) that must be filled in for each specific use.
4. **Not a substitute for negotiation.** Real commercial agreements emerge from negotiation; these are starting positions, not final positions.
5. **Not jurisdiction-flexible.** Templates assume Republic of Kenya governing law + Nairobi courts. Other jurisdictions need substantially different drafting.

---

## The five Tier 1 templates

| File | Document | Use when |
|---|---|---|
| `NDA_MUTUAL_TEMPLATE.md` | Mutual Non-Disclosure Agreement | Bank prospect conversations beyond marketing collateral; pilot/deployment discussions; contractor engagements |
| `NDA_UNILATERAL_TEMPLATE.md` | Unilateral Non-Disclosure Agreement | Investor pitches with non-public financials; hiring conversations involving codebase; pre-engagement consultations |
| `IP_ASSIGNMENT_TEMPLATE.md` | IP Assignment Agreement (founder → company) | After incorporating A2Z as a Limited Company in Kenya |
| `REFERENCE_CUSTOMER_AGREEMENT_TEMPLATE.md` | Reference Customer / Design Partner Agreement | Formalizing the Ecobank Kenya design-partner relationship |
| `README.md` | This file | — |

---

## Lawyer engagement workflow

Recommended sequence:

1. **Joshua selects a Kenyan corporate lawyer** with software/SaaS experience. KIPI maintains a public list of registered patent agents; many also do general corporate-commercial work. Budget: KES 30-50K for initial consult.

2. **Deliver this folder to the lawyer** with the v8.13 IP Strategy Plan as context. Ask the lawyer to:
   - Review the five templates against current Kenyan law
   - Flag clauses needing material rewriting
   - Add clauses missing for Joshua's specific circumstances
   - Provide indemnified final versions for execution

3. **Iterate**. Templates are starting positions; expect 2-3 rounds of redlines.

4. **Execute**. Joshua signs final versions with counterparties as situations require. Each NDA, IP Assignment, and Reference Customer Agreement becomes operationally binding only after both parties sign.

5. **Maintain registry**. Keep signed copies in a secure repository (not github, since these contain confidential commercial terms). Track which counterparty has signed which version of which template.

Budget for the full engagement: KES 200-400K for the five Tier 1 templates per the v8.13 plan. This is ~6 hours of senior corporate-legal time at typical Kenyan rates.

---

## What changes in v9.x and beyond

These templates reflect the v8.27 platform state and v8.13 IP plan recommendations. As the platform evolves:

- New product features may require additional licensable scope in the Reference Customer Agreement
- Multi-jurisdiction expansion would require parallel templates under different governing law
- Investor rounds would add SAFE / convertible note / equity round documents (Tier 4 in v8.13 plan)
- Hiring would add Employment Agreement + ESOP templates (Tier 4 in v8.13 plan)

When platform changes affect template scope, update the relevant template + bump version in the template's header. The audit-locked discipline applies: claims in templates that diverge from platform reality are bugs.

---

## Honest acknowledgements

1. **No lawyer reviewed these templates before publication.** Joshua should not rely on any clause without lawyer review.
2. **Drafting style mixes Kenyan-corporate-legal conventions with international SaaS conventions.** A Kenyan lawyer may prefer different phrasing for compliance with local norms.
3. **Some clauses are stricter than necessary.** E.g. the mutual NDA's 5-year confidentiality period is longer than the 3-year more-common version; a more relaxed counterparty may push back.
4. **Templates do not include schedules / annexes** for many provisions (e.g. specific sublicensable IP lists, customer-specific carve-outs). Lawyer adds these per deal.
5. **Currency is KES throughout.** Foreign counterparties may request USD pricing terms; lawyer adjusts.
6. **Notices clause assumes physical addresses.** Modern practice often allows email service; lawyer adjusts per Joshua's preference.
7. **No data-residency clause beyond what the IP plan recommends.** Specific banking deployments may require additional CBK-compliant data-handling provisions; lawyer adds per deal.
8. **No insurance clause.** Larger commercial contracts typically require both parties to maintain professional indemnity + cyber insurance; that's Tier 3 in the v8.13 plan and not yet drafted here.
9. **Templates are written in formal English.** No Kiswahili versions. Kenyan commercial practice usually uses English; if a deal requires bilingual drafting, lawyer translates.
10. **The v9.1 batch ships 4 templates but the v8.13 plan listed 5 Tier 1 documents.** The fifth is `LICENSE.md` which already shipped in v8.14 at repo root. Total Tier 1 inventory complete.

---

*v9.1 — Operational Legal Tier 1 templates. Companion to docs/A2Z_IP_STRATEGY_PLAN.md Appendix A.2. The Living Documentation discipline applied to legal artifacts.*
