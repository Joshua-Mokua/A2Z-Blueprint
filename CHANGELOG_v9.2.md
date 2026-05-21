# CHANGELOG v9.2 — Native-speaker translation prep guide

**Audit:** 112/112 PASS — **55th consecutive clean.**

## What

Ships `docs/translations/TRANSLATION_PREP_GUIDE.md` — reviewer-ready document for the French + Swahili translators Joshua engages to fill in v8.26 i18n scaffold placeholders. Provides banking-domain context for each of 8 translation keys + 3 proposed additional keys (severity values).

## What it includes

- Banking-domain context for each of 8 translation strings (where used, target customer audience, regulatory framing)
- Format-placeholder semantics (channel/location/severity/affected variables)
- Length budgets per channel (SMS ≤160 char, USSD ≤120-160 char, mobile push ≤80 char)
- Draft candidate translations FR + SW for each key — clearly marked "machine-generated requires native-speaker review"
- 3 proposed additional keys (severity_degraded / severity_outage / severity_sla_breach) for full localization
- Per-string translator notes (idiom guidance, register choice, term-of-art alternatives)
- Review workflow with sign-off requirements
- Compensation reference (KES 12-45K total budget)

## Honest acknowledgements

1. **Draft translations are machine-generated.** May contain errors, awkward phrasing, or domain-inappropriate register. Starting points only.
2. **Document doesn't validate translations** — it provides context for translators to do that work.
3. **Swahili treated as single language.** Real-world Kenyan Kiswahili sanifu vs coastal differences are translator territory.
4. **No A/B testing of customer comprehension** — translators provide professional-quality output; UX research is separate.
5. **No regulatory review of customer-communication phrasing** — CBK Consumer Protection Guidelines may impose specific disclosure language; A2Z's lawyer reviews finalized strings before deployment.
6. **No translation memory or terminology database.** v9.x candidate.
7. **Operational close depends on Joshua engaging translators** — guide alone doesn't change `utils/smart_alerts_i18n.py`; translators deliver, A2Z commits, then v8.26 ack #12 closes operationally (currently closed structurally).

## Next: v9.3

Patent strategy execution Phase 1 — pre-filing technical disclosure briefs for INV-008 + INV-009.
