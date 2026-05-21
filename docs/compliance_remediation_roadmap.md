# Compliance Module — Remediation Roadmap

**Module key:** `compliance` · **Organ role:** Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Module Revival Framework Phase 2 QA5. Sequenced remediation plan converting current state to certified state. Maps to v10.46x batch sequencing.

---

## Current state baseline

- Module: Compliance Module
- Organ role: Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
- Pages: 7
- Engines: 21
- Expected roles: 9
- Current doctrine health: see live module_doctrine_audit

## Remediation phases

### Sprint 1 — Phase 2 QA closeout (v10.463)
- [x] Risk assessment doc
- [x] Recovery priority matrix doc
- [x] Remediation roadmap doc (this doc)
- [x] >=3 module-specific audit gates
- [x] Cascade roles aligned with users.json

### Sprint 2 — Phase 4 deepening (planned)
- [ ] All expected_roles present in target_cascade.json
- [ ] RBAC >=80% on all module pages
- [ ] Operational outputs (st.button or form_submit_button) >=70% pages
- [ ] Workload balancing live across event_bus

### Sprint 3 — Phase 7/8 deepening (planned)
- [ ] Module-specific event publish from key pages
- [ ] Module-specific stress test scenarios beyond generic
- [ ] Module-specific capacity_plan beyond generic 5y

### Sprint 4 — Certification (planned)
- [ ] compliance_module_revival.md (criterion #12)
- [ ] compliance_capacity_plan.md doc (criterion #14)
- [ ] All 14 final-validation criteria green

## Success criteria

Module CERTIFIED when 14/14 final validation criteria met AND doctrine_health_pct >= 90% AND zero crisis flags.
