# Translation Prep Guide — A2Z MIS 360 Customer Alerts

> **Status**: REVIEWER-READY DOCUMENT — DRAFT TRANSLATIONS REQUIRE NATIVE-SPEAKER VERIFICATION
> **Shipped in**: v9.2 (May 2026)
> **Companion to**: `utils/smart_alerts_i18n.py` (v8.26 i18n scaffold)
> **Audience**: French translator + Swahili translator engaged by Joshua

---

## What this document is

The v8.26 batch shipped an i18n scaffold for customer-facing alerts. The scaffold has English (complete), French (placeholder), and Swahili (placeholder) translations of 8 alert strings.

This document is a **reviewer-ready specification** for the translators Joshua engages to fill in the placeholders. It provides:

1. The **banking-domain context** for each string so translators understand intent
2. The **operational context** (which alert types use which strings, what channels deliver them)
3. **Format-placeholder semantics** so translators preserve variable substitution correctly
4. **Draft candidate translations** — clearly marked as machine-generated starting points
5. A **review workflow** for translators to follow

The translators' role is to:
- Verify the draft candidate translations against current French / Swahili banking conventions
- Flag any draft that misses idiom, register, or technical accuracy
- Provide finalized strings that A2Z can commit to `utils/smart_alerts_i18n.py`

The translators' role is **NOT** to:
- Translate from scratch (the scaffold structure is fixed)
- Review code (Joshua's lawyer + engineering team handle that)
- Provide cultural-localization beyond translation (UI direction, color symbolism, etc. — those are v9.x candidates)

---

## What this document is NOT

1. **Not finalized translations.** Every French and Swahili string in this document is a machine-generated draft requiring native-speaker review.
2. **Not legally binding.** Customer-facing alerts may have regulatory implications (CBK consumer protection guidelines); translator should flag any phrasing that creates legal ambiguity.
3. **Not a complete localization.** Currency formatting, number formatting, date/time formats, RTL support, and other localization concerns are out of scope for this batch.
4. **Not exhaustive.** v8.26 ships 8 alert keys; future feature work may add more. Each addition triggers a new translation cycle.
5. **Not a substitute for in-context testing.** Translators should review final strings in the rendering context (mobile app, USSD, SMS) where possible.

---

## Banking-domain context

A2Z customer alerts are sent when banking channels experience operational issues. The alert system runs in the bank's operations center; alerts go to:

- **Customers** via SMS, USSD, mobile app push notifications, or email
- **Bank operations staff** via dashboard, email, or pager

The 8 strings in this batch are for the **customer-facing** flow. They should:

- Use the **register** (formality level) appropriate for a regulated commercial bank communicating with retail customers in Kenya / East Africa
- Be **concise** — SMS limit is 160 characters; USSD screens are typically 120-160 characters
- Be **factually accurate** — never overpromise resolution time or under-state severity
- Be **brand-neutral** — the strings work regardless of which Ecobank branch / region / channel is affected

---

## The 8 translation keys

Each entry below specifies:
- **Key**: the identifier in `utils/smart_alerts_i18n.py`
- **Use case**: when this string is rendered
- **English (canonical)**: the source-of-truth English text
- **Format placeholders**: variables that get substituted at render time
- **Length budget**: target character count
- **Draft FR**: machine-generated French candidate
- **Draft SW**: machine-generated Swahili candidate
- **Translator notes**: domain-specific guidance

---

### Key 1: `headline_outage`

| Field | Value |
|---|---|
| Use case | Top-of-alert when a channel is fully unavailable |
| English | `{channel} outage detected at {location}` |
| Placeholders | `{channel}` (e.g. ATM, USSD, MOBILE APP), `{location}` (branch name / region / "system-wide") |
| Length budget | ≤80 characters |
| Draft FR | `Panne {channel} détectée à {location}` |
| Draft SW | `Hitilafu ya {channel} imegunduliwa katika {location}` |

**Translator notes**:
- "outage" in banking-customer-facing context typically translates to the strongest available term ("panne" in French, "hitilafu" or "kushindwa" in Swahili)
- Verify the placeholder positioning works grammatically with all expected channel names; some Bantu languages prefer pre-noun modifiers
- For Swahili: confirm `imegunduliwa` (passive past) is the appropriate aspect; alternatives include `ipo` (current state) or `imetokea` (has occurred)

---

### Key 2: `headline_degraded`

| Field | Value |
|---|---|
| Use case | Top-of-alert when a channel is operational but slow / intermittent |
| English | `{channel} performance degraded at {location}` |
| Placeholders | `{channel}`, `{location}` |
| Length budget | ≤80 characters |
| Draft FR | `Performance {channel} dégradée à {location}` |
| Draft SW | `Utendaji wa {channel} umeshuka katika {location}` |

**Translator notes**:
- "degraded" implies partial functioning — not "broken"; pick a verb that conveys reduced quality without alarm
- For Swahili: `umeshuka` (has dropped) is acceptable but `umepungua` (has decreased) is also valid; translator picks per banking convention

---

### Key 3: `headline_sla_breach`

| Field | Value |
|---|---|
| Use case | Top-of-alert when an SLA threshold has been crossed (e.g. response time exceeds commitment) |
| English | `{channel} SLA breach at {location}` |
| Placeholders | `{channel}`, `{location}` |
| Length budget | ≤80 characters |
| Draft FR | `Violation SLA {channel} à {location}` |
| Draft SW | `Ukiukaji wa SLA ya {channel} katika {location}` |

**Translator notes**:
- "SLA" (Service Level Agreement) is typically retained as English acronym in Francophone Africa banking; verify
- For Swahili: customers may not recognize "SLA"; consider whether to translate as "ahadi ya huduma" (service promise) or retain English; translator's call based on Ecobank's customer-communication norms
- "breach" carries legal weight; use a term that conveys the threshold has been exceeded without implying customer harm

---

### Key 4: `headline_default`

| Field | Value |
|---|---|
| Use case | Generic fallback headline when alert type doesn't match other categories |
| English | `{channel} alert at {location}` |
| Placeholders | `{channel}`, `{location}` |
| Length budget | ≤60 characters |
| Draft FR | `Alerte {channel} à {location}` |
| Draft SW | `Tahadhari ya {channel} katika {location}` |

**Translator notes**:
- "alert" is intentionally general — a neutral notification term
- French: `alerte` is fine; could also be `notification` but `alerte` matches the urgency tone
- Swahili: `tahadhari` is the standard banking term for warnings/alerts

---

### Key 5: `body_default`

| Field | Value |
|---|---|
| Use case | Body text appended after the headline; describes severity + scope + resolution status |
| English | `Severity: {severity}. Estimated affected customers: {affected}. Engineering team is investigating.` |
| Placeholders | `{severity}` (DEGRADED / OUTAGE / SLA_BREACH), `{affected}` (numeric count) |
| Length budget | ≤200 characters |
| Draft FR | `Sévérité: {severity}. Clients affectés estimés: {affected}. L'équipe technique enquête.` |
| Draft SW | `Kiwango: {severity}. Wateja walioathirika: {affected}. Timu ya uhandisi inachunguza.` |

**Translator notes**:
- The `{severity}` value comes through as English uppercase (DEGRADED/OUTAGE/SLA_BREACH); should those be translated too? **DECISION REQUIRED**: either (a) translate severity values as separate keys, or (b) display English severity values transliterated. For v9.2 the recommendation is (a) — add 3 new keys (`severity_degraded`, `severity_outage`, `severity_sla_breach`) so the displayed severity is in the customer's language. Translator to draft these.
- "Engineering team is investigating" is bank-internal jargon; in customer-facing context, consider "Our team is working on it" or equivalent. French: `Notre équipe enquête` is more natural than `L'équipe technique enquête`. Translator's call.

---

### Key 6: `ack_button_label`

| Field | Value |
|---|---|
| Use case | Label on the "I have read this alert" button in mobile app / dashboard |
| English | `Acknowledge` |
| Placeholders | none |
| Length budget | ≤20 characters |
| Draft FR | `Accuser réception` (formal) or `Confirmer` (shorter/casual) |
| Draft SW | `Thibitisha` |

**Translator notes**:
- Two French options provided — translator picks based on Ecobank's app tone; `Confirmer` fits better in mobile UI buttons
- Swahili: `Thibitisha` is the standard "confirm" verb; alternatives include `Kubali` (accept) but `Thibitisha` is more neutral

---

### Key 7: `tier_urgent_prefix`

| Field | Value |
|---|---|
| Use case | Prefix added to alert headline for highest-priority alerts |
| English | `[URGENT]` |
| Placeholders | none |
| Length budget | ≤15 characters |
| Draft FR | `[URGENT]` (no translation — URGENT is universally understood in French banking) |
| Draft SW | `[HARAKA]` or `[DHARURA]` — translator picks |

**Translator notes**:
- French: `URGENT` is identical in French; no translation needed
- Swahili: `HARAKA` (immediate) and `DHARURA` (emergency) are both candidates. `HARAKA` is more common in operational banking context; `DHARURA` connotes risk to life or property which may overstate the customer-impact level
- Square brackets retained as-is (these are visual markers, not language)

---

### Key 8: `tier_high_prefix`

| Field | Value |
|---|---|
| Use case | Prefix for second-highest-priority alerts (between URGENT and normal) |
| English | `[HIGH]` |
| Placeholders | none |
| Length budget | ≤15 characters |
| Draft FR | `[ÉLEVÉ]` |
| Draft SW | `[JUU]` or `[KUBWA]` — translator picks |

**Translator notes**:
- French: `ÉLEVÉ` (elevated) is standard banking-French for high priority
- Swahili: `JUU` (high) and `KUBWA` (large) both work; `JUU` matches priority connotation better

---

## Proposed additional keys (not in v8.26 scaffold; v9.2 recommendations)

Per the translator notes for `body_default`, severity values currently come through as English uppercase. To support full localization, add these 3 keys:

| Key | English | Draft FR | Draft SW |
|---|---|---|---|
| `severity_degraded` | DEGRADED | DÉGRADÉ | UMESHUKA |
| `severity_outage` | OUTAGE | PANNE | HITILAFU |
| `severity_sla_breach` | SLA BREACH | VIOLATION SLA | UKIUKAJI WA SLA |

If the translators agree, these get added to `TRANSLATIONS` dict in v8.26 scaffold, and `smart_alerts.py` updates to use `t("severity_" + severity_lowercase)` instead of raw severity strings.

---

## Review workflow for translators

1. **Read this entire document.** Understand the banking domain context and the operational use cases.

2. **Review each draft translation.** For each of 8 keys (+ 3 proposed), either:
   - **Confirm**: write "CONFIRMED — [your initials]" next to the draft
   - **Modify**: write the corrected version + brief rationale
   - **Reject**: explain why no acceptable translation exists in the language and propose alternative approach

3. **Address open questions** flagged in translator notes:
   - Whether to translate severity values (recommendation: yes; see proposed additional keys)
   - Whether to retain "SLA" English acronym or translate (recommendation: retain in French, translator's call in Swahili)
   - Mobile button length constraints (verify `Confirmer` / `Thibitisha` fit in Ecobank's app UI)

4. **Test in context.** Where possible, view a sample alert in each rendering channel:
   - SMS (≤160 char limit)
   - Mobile app push notification
   - USSD screen
   - Email

5. **Sign off.** Provide a signed declaration (PDF or wet ink) confirming that the finalized translations are professional-quality and suitable for customer-facing use.

6. **Deliver.** Send the finalized translations as a markdown table or JSON snippet that A2Z can paste directly into `utils/smart_alerts_i18n.py`. Format:

```python
"fr": {
    "headline_outage": "<finalized French>",
    "headline_degraded": "<finalized French>",
    # ... etc.
},
"sw": {
    "headline_outage": "<finalized Swahili>",
    # ... etc.
},
```

---

## Compensation reference

Per the v8.13 IP plan budget framework, professional translation work for 8-12 short banking strings typically costs:

- **Kenya-based translator (Swahili)**: KES 5,000-15,000
- **France-based or West-Africa-based translator (French)**: EUR 50-200 / KES 7,000-30,000

Higher rates apply for: certified translators, banking-domain specialists, or rush turnaround.

---

## Honest acknowledgements

1. **Draft translations are machine-generated.** They may contain errors, awkward phrasing, or domain-inappropriate register. They are starting points, not finalized text.
2. **No banking-domain localization beyond translation.** Cultural concerns (right-to-left for some Swahili speakers, French banking conventions in Francophone Africa vs. France-French, etc.) are translator territory.
3. **No A/B testing of customer comprehension.** The translations are best-efforts; if Ecobank wants to validate that customers actually understand the alerts, that's separate UX research.
4. **Swahili is treated as a single language.** In reality, Kenyan Swahili (Kiswahili sanifu) differs from coastal Swahili. Translator should clarify which variant Ecobank's customers expect.
5. **No translation memory or terminology database.** Each future translation cycle starts fresh; if Ecobank standardizes banking-domain terminology across translators, that's a v9.x candidate (translation TM file).
6. **Format-placeholder bugs are tested in code, not translation.** If a translator's finalized string omits a `{placeholder}`, format-string substitution will fail at runtime; A2Z's tests catch this.
7. **No accessibility review** (screen reader compatibility, font size, contrast in app rendering). Out of scope for translation prep.
8. **No regulatory review of customer-communication phrasing.** CBK Consumer Protection Guidelines may impose specific disclosure language requirements; A2Z's lawyer should review final strings against those before deployment.

---

## What ships in v9.2 vs v9.x future

| Item | v9.2 status | Future status |
|---|---|---|
| Translation prep document (this file) | ✅ shipped | — |
| Banking-domain context for each string | ✅ shipped | — |
| Draft candidate translations FR + SW | ✅ shipped | Replaced by translator-finalized strings |
| Proposed additional keys (severity values) | ✅ proposed | Translator confirms; A2Z implements |
| Translator engagement | ⏳ Joshua's responsibility | — |
| Finalized French translations | ⏳ requires translator | Lands in v8.26 scaffold |
| Finalized Swahili translations | ⏳ requires translator | Lands in v8.26 scaffold |
| Per-customer locale detection | ⏳ requires schema work | v9.x candidate |
| Locale-aware delivery channel selection | ⏳ requires deployment context | v9.x candidate |
| Translation memory file | ⏳ scope tbd | v9.x candidate |
| Additional locales (Arabic, Amharic, Portuguese) | ⏳ scope tbd | v9.x+ candidate per market |

---

*v9.2 — Translation prep guide. Companion to utils/smart_alerts_i18n.py (v8.26). The reviewer-ready document that makes translator engagement materially cheaper and more accurate.*
