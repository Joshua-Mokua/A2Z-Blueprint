# CRM & Customer Functions Module — Redundant Components Scan

**Module key:** `crm` · **Organ role:** Sensory & Interaction Systems (pipeline · customer 360 · propositions · campaigns · cross-sell · channels · NPS · behavioral intelligence · onboarding · cards · bancassurance · merchant acquiring)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `3_pipeline.py` — 5 tabs
- `5_products.py` — 0 tabs
- `16_commission.py` — 5 tabs
- `17_campaigns.py` — 5 tabs
- `27_propositions.py` — 0 tabs
- `34_customer360.py` — 7 tabs
- `38_nps.py` — 5 tabs
- `45_crosssell.py` — 7 tabs
- `47_digital_channels.py` — 6 tabs
- `48_contact_centre.py` — 4 tabs
- `49_bancassurance.py` — 5 tabs
- `66_partnerships.py` — 7 tabs
- `69_consent.py` — 7 tabs
- `73_channels.py` — 7 tabs
- `78_onboarding.py` — 7 tabs
- `79_cards.py` — 7 tabs
- `80_merchant.py` — 6 tabs
- `91_customer_behavioral_intelligence.py` — 5 tabs
- `92_propositions_workbench.py` — 0 tabs
- `94_campaigns_management.py` — 8 tabs
- `104_tf_mobile.py` — 0 tabs
- `117_propositions_hub.py` — 0 tabs

## Engine overlap

- Engines: 11
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
