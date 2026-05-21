# REFERENCE CUSTOMER / DESIGN PARTNER AGREEMENT (TEMPLATE)

> **STATUS**: DRAFT TEMPLATE — NOT BINDING — REQUIRES KENYAN CORPORATE LAWYER REVIEW BEFORE EXECUTION
> **Version**: v9.1 (May 2026)
> **Use when**: Formalizing the design-partner relationship with Ecobank Kenya. Per v8.13 IP Plan Appendix A.2.5.

---

**THIS DESIGN PARTNER AGREEMENT** ("**Agreement**") is made on `[DATE]` between:

**(1)** `[A2Z PARTY NAME]`, a `[sole proprietorship / limited company]` registered in the Republic of Kenya with `[business registration number / company number]`, having its principal place of business at `[ADDRESS]` ("**A2Z**"); and

**(2)** **Ecobank Kenya Limited**, a limited company incorporated in the Republic of Kenya under company number `[NUMBER]`, having its registered office at `[ADDRESS]`, regulated by the Central Bank of Kenya as a commercial bank ("**Ecobank**" or "**Design Partner**"),

each a "**Party**" and together the "**Parties**".

---

## Recitals

**A.** A2Z develops and operates the A2Z MIS 360 banking management intelligence platform (the "**Platform**"), an audit-locked balanced-scorecard contract engine with FLEXCUBE Anti-Corruption Layer integration, designed for commercial-bank deployment.

**B.** Ecobank operates a commercial banking franchise in Kenya including approximately 35 branches, 232 relationship managers, and a customer base of approximately 700,000 customers, using Oracle FLEXCUBE 12 as its core banking system.

**C.** A2Z and Ecobank wish to collaborate during the platform's development phase such that A2Z gains real-world deployment context and Ecobank gains early access to a platform designed for its operational needs.

**D.** The Parties acknowledge that no production deployment exists as of the Effective Date and no measured business outcomes have been produced. This Agreement governs the development and pre-production engagement only; production deployment requires a separate commercial agreement (Master Services Agreement or equivalent).

---

## 1. Definitions

**1.1** "**Effective Date**" means the date this Agreement is executed by both Parties.

**1.2** "**Term**" means the period from the Effective Date to the date of termination per Section 9, or to the date of execution of a Master Services Agreement (MSA) replacing this Agreement, whichever is earlier.

**1.3** "**Engagement Scope**" means the activities, deliverables, and access rights described in Schedule 1.

**1.4** "**Bank Data**" means any data originating from Ecobank's systems, customers, or operations that is shared with A2Z under this Agreement, including without limitation: (a) anonymized or pseudonymized portfolio aggregates; (b) FLEXCUBE configuration metadata; (c) operational performance data; (d) personal data within the meaning of the Kenya Data Protection Act 2019.

**1.5** "**Platform Improvements**" means any enhancements, modifications, or new features that A2Z develops as a result of, or in response to, feedback or insight from the engagement.

---

## 2. Engagement scope and access

**2.1** A2Z and Ecobank shall collaborate on the activities described in Schedule 1, which may include without limitation:

(a) joint architectural review of A2Z's FLEXCUBE Anti-Corruption Layer;
(b) Ecobank-feedback-driven adjustments to A2Z's KPI library, audit-locked invariants, and reporting formats;
(c) controlled access by A2Z personnel to anonymized or pseudonymized FLEXCUBE export data for testing and validation;
(d) joint development of a deployment runbook tailored to Ecobank's operational environment;
(e) periodic review meetings to assess progress and discuss evolving requirements.

**2.2** **No production access.** This Agreement does not grant A2Z access to live customer data, production transaction streams, or production banking infrastructure. Any such access requires a separate Master Services Agreement and Data Processing Agreement compliant with the Kenya Data Protection Act 2019.

**2.3** **No production deployment.** The Platform shall not be deployed in any production environment of Ecobank under this Agreement. Any production deployment requires Master Services Agreement, Data Processing Agreement, regulatory clearance per CBK Operations Resilience Guidelines, and CISO sign-off.

---

## 3. Bank data handling

**3.1** A2Z's handling of Bank Data shall comply with:

(a) the Kenya Data Protection Act 2019, including without limitation Sections 25-30 (data subject rights), Section 41 (data processor obligations), and Section 42 (impact assessment);
(b) CBK Prudential Guidelines for data confidentiality;
(c) any Ecobank-internal data-handling policies provided to A2Z in writing.

**3.2** **Anonymization required.** Any Bank Data shared with A2Z shall be anonymized or pseudonymized prior to disclosure, such that no individual customer or staff member can be identified. Ecobank is responsible for the anonymization process; A2Z is responsible for not attempting to re-identify individuals from received data.

**3.3** **Storage location.** A2Z shall store Bank Data only in systems located in the Republic of Kenya, in compliance with data-residency requirements. Cross-border transfer (including to cloud services with non-Kenyan availability zones) requires Ecobank's prior written consent.

**3.4** **Retention and destruction.** A2Z shall destroy all Bank Data within 90 days of termination of this Agreement and certify destruction in writing.

**3.5** **Breach notification.** A2Z shall notify Ecobank of any actual or suspected security breach affecting Bank Data within 24 hours of becoming aware, and cooperate in any investigation.

---

## 4. Intellectual property

**4.1** **Pre-existing IP.** Each Party retains all rights in its pre-existing intellectual property. Specifically:

(a) A2Z retains all rights in the Platform, the audit-locked architectural patterns, the 9-gate defense-in-depth perimeter, the Living Documentation system, the Anti-Corruption Layer fallback design, and all related source code, documentation, and trademarks;

(b) Ecobank retains all rights in its FLEXCUBE configuration, customer data, operational processes, brand identity, and all proprietary banking systems.

**4.2** **Platform Improvements.** Any Platform Improvements developed by A2Z, including those resulting from Ecobank feedback, shall be the sole property of A2Z. Ecobank shall not acquire any rights in the Platform or Platform Improvements except as expressly set out in this Agreement.

**4.3** **Ecobank license to use Platform Improvements.** A2Z hereby grants Ecobank a non-exclusive, non-transferable, royalty-free license to use any Platform Improvements developed during the Term in connection with any future production deployment, contingent on execution of a Master Services Agreement covering such production deployment. This license expires automatically if no MSA is executed within 24 months of termination of this Agreement.

**4.4** **No trademark license.** Neither Party may use the other's trademarks without prior written consent, except as expressly permitted under Section 5 (Reference Rights).

---

## 5. Reference rights and publicity

**5.1** **A2Z's reference rights.** During the Term and for 24 months after termination, A2Z may identify Ecobank as a "design partner" in:

(a) sales conversations subject to a mutual NDA;
(b) the `docs/sales_content/case_studies.json` file in A2Z's github repository, with the relationship described as "design partner — development context, not production deployment, no measured outcomes" (or substantially similar honest-scope language);
(c) investor pitches and similar non-public commercial conversations.

**5.2** **A2Z's restricted publications.** A2Z shall NOT, without Ecobank's prior written consent:

(a) issue any press release naming Ecobank;
(b) publish customer testimonials attributed to Ecobank;
(c) make any public claim that Ecobank is using the Platform in production;
(d) display Ecobank's logo or trademarks in any marketing collateral;
(e) cite specific operational metrics, financial figures, or proprietary details of Ecobank in any sales material;
(f) publish on any social media platform any content that identifies Ecobank.

**5.3** **Ecobank's reference rights.** Ecobank may identify A2Z in internal Ecobank communications and regulatory filings as required, and may discuss the engagement with consultants, auditors, and advisors subject to confidentiality.

**5.4** **Future reference upgrade.** Upon execution of a Master Services Agreement and successful production deployment, the Parties may negotiate expanded reference rights including testimonials, logo use, joint case studies, and joint conference presentations. Such expanded rights shall be addressed in the MSA, not this Agreement.

---

## 6. Confidentiality

**6.1** This Agreement incorporates by reference the terms of the Mutual Non-Disclosure Agreement executed between the Parties on `[NDA DATE]`. To the extent of any conflict, the more restrictive provision shall apply.

**6.2** **Survival.** Confidentiality obligations survive termination of this Agreement for 5 years per the underlying NDA terms.

---

## 7. Fees and consideration

**7.1** **Free pilot.** During the Term, A2Z shall provide its services and Platform access free of charge. Ecobank shall provide engagement, feedback, and Bank Data access free of charge. Neither Party owes the other any cash fee for activities under this Agreement.

**7.2** **Out-of-pocket expenses.** Each Party bears its own out-of-pocket expenses (travel, communications, internal staff time). Where joint expenses arise (e.g. third-party tooling for joint testing), the Parties shall agree in writing on cost-sharing before incurring such expenses.

**7.3** **No payment-in-kind.** Neither Party owes the other any payment-in-kind, equity, royalty, or future-revenue share under this Agreement. Production deployment compensation is governed by a future MSA.

---

## 8. Liability and warranties

**8.1** **Platform "as is".** A2Z provides the Platform "as is" during the Term. A2Z makes no warranty as to fitness for production use, regulatory compliance for production deployment, or any specific operational outcome.

**8.2** **No warranty of measured outcomes.** A2Z explicitly disclaims any warranty that Platform deployment will produce specific business outcomes (revenue increase, NPL reduction, operational savings, etc.). Per the v8.27 platform state, A2Z has no production deployments and no measured outcomes; any future production deployment requires a separate MSA with appropriate warranties.

**8.3** **Ecobank disclaimer.** Ecobank provides Bank Data and engagement on a best-efforts basis. Ecobank makes no warranty as to the accuracy or completeness of Bank Data shared, and no warranty that the engagement will produce a Master Services Agreement or production deployment.

**8.4** **Liability cap.** Each Party's aggregate liability to the other under this Agreement shall not exceed `[KES 5,000,000]`, except for: (a) breaches of confidentiality; (b) breaches of data protection obligations; (c) wilful misconduct or fraud, all of which shall be uncapped.

**8.5** **Exclusion of consequential damages.** Neither Party shall be liable for indirect, incidental, consequential, or punitive damages, lost profits, or lost data, except in cases of wilful misconduct.

---

## 9. Term and termination

**9.1** **Term.** This Agreement commences on the Effective Date and continues for an initial term of `[12]` months ("**Initial Term**"), automatically renewing for successive `[6-month]` periods unless either Party gives 30 days' written notice of non-renewal.

**9.2** **Termination for convenience.** Either Party may terminate this Agreement at any time upon 30 days' written notice.

**9.3** **Termination for cause.** Either Party may terminate this Agreement immediately upon written notice if:

(a) the other Party commits a material breach and fails to cure within 30 days of written notice;
(b) the other Party becomes insolvent, enters administration, or ceases to carry on business;
(c) the other Party suffers a regulatory action that materially impairs its ability to perform under this Agreement.

**9.4** **Effects of termination.** Upon termination:

(a) A2Z shall cease all access to Bank Data and any Ecobank systems;
(b) A2Z shall destroy Bank Data per Section 3.4;
(c) A2Z's reference rights under Section 5.1 continue for 24 months unless terminated for cause due to A2Z breach;
(d) the licenses granted in Section 4.3 continue per their terms;
(e) confidentiality obligations continue per Section 6.

**9.5** **Conversion to MSA.** If the Parties agree to convert the engagement to a production deployment, this Agreement is superseded by the Master Services Agreement at execution of the MSA.

---

## 10. Notices, assignment, entire agreement, severability

**10.1** **Notices** shall be in writing and delivered per Kenyan-corporate convention (in person on delivery; registered post on third Business Day; email on delivery confirmation).

**10.2** **Assignment.** Neither Party may assign this Agreement without the other's prior written consent, except that A2Z may assign to a successor in connection with a merger, acquisition, or sale of substantially all assets, provided the successor agrees in writing to be bound. Ecobank may assign to a wholly-owned subsidiary or successor.

**10.3** **Entire agreement.** This Agreement, together with the underlying NDA, constitutes the entire agreement between the Parties concerning its subject matter.

**10.4** **Amendment.** No amendment shall be effective unless in writing signed by both Parties.

**10.5** **Severability.** If any provision is held invalid, the remaining provisions continue in full force.

**10.6** **No partnership.** Nothing in this Agreement creates a partnership, joint venture, or agency relationship between the Parties. Neither Party may bind the other.

---

## 11. Governing law and jurisdiction

**11.1** This Agreement shall be governed by the laws of the Republic of Kenya.

**11.2** The Parties submit to the exclusive jurisdiction of the courts of Nairobi, Kenya, provided that either Party may seek interim or injunctive relief in any court of competent jurisdiction.

**11.3** Any dispute may, by written agreement of the Parties, be submitted to arbitration under the Arbitration Act of Kenya 1995.

---

## 12. Counterparts and electronic signature

**12.1** This Agreement may be executed in counterparts and signatures delivered electronically (PDF, DocuSign) shall be deemed valid and binding.

---

## Signatures

**For and on behalf of** `[A2Z PARTY NAME]`:

| Field | Value |
|---|---|
| Signed | _______________________________ |
| Name | `[NAME]` |
| Title | `[TITLE]` |
| Date | `[DATE]` |

**For and on behalf of Ecobank Kenya Limited:**

| Field | Value |
|---|---|
| Signed | _______________________________ |
| Name | `[NAME]` |
| Title | `[TITLE]` |
| Date | `[DATE]` |

---

## Schedule 1 — Engagement Scope

`[Lawyer + Joshua + Ecobank to fill in. Should specify activities, deliverables, timelines, and access rights agreed for the development phase.]`

### 1.1 Activities

| # | Activity | Frequency | Lead Party |
|---|---|---|---|
| 1 | Architecture review meetings | Monthly | A2Z |
| 2 | KPI library review and adjustment | Quarterly | Ecobank |
| 3 | FLEXCUBE export data sharing for testing | As-requested | Ecobank |
| 4 | Joint deployment runbook drafting | One-time | A2Z |
| 5 | Periodic progress reviews | Monthly | Joint |

### 1.2 Deliverables (A2Z to Ecobank)

| # | Deliverable | Timeline | Status |
|---|---|---|---|
| 1 | Platform demo environment with Ecobank-themed sample data | 60 days | — |
| 2 | KPI library calibrated to Ecobank's BSC structure | 90 days | — |
| 3 | Joint deployment runbook (draft) | 120 days | — |

### 1.3 Bank Data shared (Ecobank to A2Z)

| # | Data type | Format | Anonymization | Cadence |
|---|---|---|---|---|
| 1 | Anonymized portfolio aggregates | JSON / CSV | Pseudonymized at branch + RM level | Monthly |
| 2 | FLEXCUBE configuration metadata (non-credentialed) | JSON | N/A (no personal data) | One-time + on-change |
| 3 | KPI baseline distributions | Aggregated CSV | Aggregated | Quarterly |

`[Lawyer to verify these specific data flows comply with DPA 2019 and CBK requirements.]`

---

## Drafter's commentary (REMOVE BEFORE EXECUTION)

### Why this matters
Per the v8.13 IP Strategy Plan Appendix A.2.5: as soon as any value flows in either direction (Ecobank provides data/access, A2Z provides a working pilot), there must be a written agreement. Verbal arrangements with banks in Kenya have repeatedly led to disputes.

### Honest framing in the recitals
Recitals A-D explicitly acknowledge that no production deployment exists and no measured outcomes have been produced. This is the v8.13 plan's IP-discipline applied to commercial agreements: don't overclaim. This protects A2Z if Ecobank later contends that A2Z misrepresented the platform's maturity.

### Section 5.2 restricted publications
Strict disclosure restrictions match the `case_studies.json` `may_appear_in_collateral: false` flag set in v8.12 Living Doc Phase 1. This is internally consistent — the agreement formalizes what the Living Doc system already enforces.

### Free pilot
The IP plan recommends free pilot during development. Once the engagement converts to production deployment, fees apply via MSA. This pattern aligns with industry-standard SaaS practice for early customers.

### Liability cap
KES 5M default; Ecobank may push for higher. Lawyer to advise based on Ecobank's typical negotiation patterns.

### Anonymization (Section 3.2)
Critical. Live customer data must NEVER reach A2Z under this development agreement. Real-world deployment with actual personal data requires a separate DPA per Section 41 of DPA 2019.

### What's deferred to the MSA
- Production deployment terms
- SLAs (uptime, response time)
- Production-level fees + revenue share if any
- Production data-handling provisions
- Production-grade insurance requirements
- Long-term IP licensing
- Joint marketing rights

### Lawyer to verify
- That clause 3.3 storage-in-Kenya requirement is consistent with any existing Ecobank vendor policies
- That clause 5.4 "future reference upgrade" framing doesn't accidentally create premature licensing obligations
- That Schedule 1's specific data flows comply with current DPA 2019 + CBK guidance
- That the liability cap survives any IT-systems-level breach

---

*v9.1 template — companion to docs/A2Z_IP_STRATEGY_PLAN.md Appendix A.2.5. Most negotiation-heavy of the Tier 1 templates; expect 2-3 rounds of redlines from Ecobank's legal team.*
