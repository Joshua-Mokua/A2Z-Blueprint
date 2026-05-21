# CHANGELOG v10.169 — AML/Compliance MODULE CLOSURE CEREMONY

**Status:** **11th module closure in platform history** (after Treasury v10.155). Closes the AML/Compliance arc that opened with v10.160 ENH-191 KYC/KYB Onboarding. All 9 standards (ENH-191..ENH-199) are status='active'; the closure ceremony locks the module against regression with two new audit gates.

**Audit:** `Score: 153/153 gates = 100.0% — PASS` (audit count 151 → 153, +2 closure gates). G142 anti-drift floor 84→86 (+2 closure standards). Active standards 186→188. v10.169 closure tests 22/22 pass.

---

## Headline: AML/Compliance MODULE FULLY CLOSED

The matching bookend to Treasury v10.155 closure. Same architectural pattern: module cockpit + module API + Tier 4 admin marker + 2 closure audit gates. Same regulator-grade artifact production. Same honest deferral discipline.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `pages/27_compliance_arc_cockpit.py` | ~470 | NEW. 7 thematic tabs over 9 engines |
| `utils/api_compliance.py` | ~370 | NEW. 16 GET endpoints with JWT + audit logging |
| `pages/7_admin.py` (Tier 4D added) | +50 | AML/Compliance Arc Closure marker |
| `scripts/audit.py` (G152 + G153) | +180 | Two new closure gates |
| `app.py` (1 line) | +1 | Cockpit registration in _audit_grp |
| `tests/test_compliance_arc_closure_v10_169.py` | ~330 | NEW. 22 closure tests |
| `docs/Master_Prompt_v3.62.md` | ~1100 | Anti-drift sync v3.61 → v3.62 |
| `SCOPE_LEDGER.md` | updated | v10.169 closure row |
| `CHANGELOG_v10.169.md` | this file | This document |

---

## The cockpit — pages/27_compliance_arc_cockpit.py

7 thematic tabs grouping all 9 engines per workflow logic (G4 ≤7 tab limit):

| Tab | Engines |
|---|---|
| 📊 Dashboard | Cross-engine board pack + ENH-198 enterprise risk score headline |
| 👤 KYC + Screening | ENH-191 KycOnboardingEngine + ENH-192 ScreeningOrchestrator |
| 🚨 AML Monitoring | ENH-193 AmlMonitoringEngine alerts + escalations |
| 📋 SAR Filings | ENH-194 SarFilingEngine + POCAMLA §44 deadline surface |
| 📊 Risk Assessment | ENH-198 ComplianceRiskAssessmentEngine 5-dim scorecard |
| 📑 Reg + Policy | ENH-195 RegulatoryChangeEngine + ENH-196 PolicyManagementEngine |
| 🎓 Training + Examiner | ENH-197 ComplianceTrainingEngine + ENH-199 ExaminerReportingEngine |

**Examiner reporting co-located with Training** because both produce regulator-facing artifacts (the 9 engines fit into 7 tabs without skipping any surface).

Design discipline carried forward from v10.155 Treasury cockpit:
1. Streamlit/import fallback at top — module loads even when Streamlit not installed
2. `require_access("compliance")` — inherits AML/Compliance role group RBAC
3. Real `audit_log` signature (action, username, detail, module)
4. `@st.cache_resource` engine instance caching at session level
5. Read-only display — state-mutating workflows go through explicit FastAPI POST endpoints

**Honest deferrals visible in the cockpit**: every engine's "Honest deferrals" expander surfaces the relevant `*_status` field — operators reading the cockpit see what the platform doesn't do, not what's fabricated.

---

## The API — utils/api_compliance.py

**16 GET endpoints, all JWT-protected, all audit-logged:**

```
GET /api/compliance/board                            # cross-engine pack (HEADLINE)
GET /api/compliance/kyc/board                        ENH-191
GET /api/compliance/screening/board                  ENH-192
GET /api/compliance/aml/board                        ENH-193
GET /api/compliance/sar/board                        ENH-194
GET /api/compliance/risk/board                       ENH-198
GET /api/compliance/examiner/board                   ENH-199
GET /api/compliance/regulatory-change/board          ENH-195
GET /api/compliance/policy/board                     ENH-196
GET /api/compliance/training/board                   ENH-197
GET /api/compliance/sar/overdue                      operator-actionable
GET /api/compliance/regulatory-change/overdue        operator-actionable
GET /api/compliance/policy/overdue                   operator-actionable
GET /api/compliance/training/overdue                 operator-actionable
GET /api/compliance/training/expiring                30-day cert expiry window
GET /api/compliance/risk/latest                      latest enterprise score
GET /api/compliance/regulatory-change/{change_id}    single change
GET /api/compliance/policy/{policy_id}/{version_id}  single policy version
GET /api/compliance/policy/by-change/{change_id}     ENH-195→ENH-196 reverse-lookup
GET /api/compliance/training/by-change/{change_id}   ENH-195→ENH-197 reverse-lookup
GET /api/compliance/training/by-policy/{policy_id}   ENH-196→ENH-197 reverse-lookup
```

**The headline `/board` endpoint** bundles all 9 engines' `board_summary()` into one JSON response — single round-trip, full enterprise compliance posture. **The demo-closing argument for the Ecobank vendor evaluation panel.**

**The trio of reverse-lookup endpoints** completes the bidirectional ENH-195↔ENH-196↔ENH-197 linkage at the API surface — examiner can query: "this CBK PG/15 amendment came in last quarter — show me the full downstream impact" and get the regulatory-change → policy-update → training-completion chain in three calls.

Design discipline matches v10.155 Treasury API:
1. Every endpoint requires JWT — `Depends(get_current_user)`
2. Audit logging via `_audit_compliance(action, user, detail)`
3. Read-only contract — POST endpoints deferred to follow-up increment with proper Pydantic models for the frozen dataclasses across all 9 engines
4. fastapi import fallback shim — module loads in test/sandbox environments without fastapi installed

---

## G152 + G153 — closure gates

**G152 `compliance_module_closed`** (mirrors Treasury G150):
- Verifies all 9 ENH-191..199 are status='active' in registry
- Verifies each named engine file exists in utils/
- Returns: `v10.169 AML/Compliance module closure: 9/9 standards active (100%) — PASS`

**G153 `compliance_arc_ui_integrated`** (mirrors Treasury G151):
- Verifies `pages/27_compliance_arc_cockpit.py` exists and imports all 8 named engine classes (ScreeningOrchestrator is conditionally imported and not required for cockpit operation)
- Verifies `utils/api_compliance.py` exists with `router = APIRouter` and `Depends(get_current_user)`
- Returns: `v10.169 AML/Compliance UI integration: 8/8 engines integrated — PASS`

The two new gates added to the GATES tuple at the end:

```python
("G150", gate_treasury_module_closed),                # v10.155 Phase 2
("G151", gate_treasury_arc_ui_integrated),            # v10.155 Phase 2
("G152", gate_compliance_module_closed),              # v10.169 Phase 3
("G153", gate_compliance_arc_ui_integrated),          # v10.169 Phase 3
```

**Audit count: 151 → 153.** `Score: 153/153 gates = 100.0% — PASS`.

---

## Tier 4D admin marker — pages/7_admin.py

Added immediately after Treasury Tier 4C — same nesting, same description shape. Contains the complete v10.160-v10.169 build narrative: which standard shipped in which drop, which engines compose, what's deferred and why. The admin marker becomes the institutional memory for the AML/Compliance arc.

---

## End-to-end probe — the matching bookend to Treasury

Started clean. Built all 4 closure files (cockpit + API + admin Tier 4D + audit gates) + tests. First audit run came back **152/153 with G149 violation**:

```
❌ [G149] cockpits_registered_in_app v10.153 cockpit nav registration:
   10/11 cockpits registered in app.py; 1 unregistered
   • v10.153: 27_compliance_arc_cockpit.py exists on disk but is not
     registered in app.py
```

The G149 ratchet from v10.153 doing exactly what it's designed to do — catch closures that ship a cockpit on disk but forget to wire it into app.py nav. Fixed with one-line _pg() entry in `_audit_grp`:

```python
_pg("pages/27_compliance_arc_cockpit.py", "Compliance Arc Cockpit",
    "🛡️", "compliance"),
```

Rerun: **`Score: 153/153 gates = 100.0% — PASS`**. Closure complete.

---

## Tests — 22 across 8 classes

- **TestCockpitShape** (3) — exists/parses / 8 named engine imports / 7 thematic tabs
- **TestApiShape** (5) — exists/parses / APIRouter / JWT auth / **headline /board endpoint** / all 8 engines imported
- **TestRegistryClosure** (1) — all 9 ENH-191..199 active with non-empty affected_engines
- **TestAdminClosureMarker** (1) — Tier 4D marker present
- **TestAuditGates** (6) — G152 registered / G153 registered / **count 153** / all gates pass / G152 returns 9/9 / G153 returns 8/8
- **TestAppRegistration** (1) — cockpit registered in app.py nav
- **TestEndToEndAPI** (2) — module imports cleanly / engine singletons reachable
- **TestNoRegression** (3) — v10.168 training / v10.167 policy / **Treasury G150+G151 unchanged**

All 22 pass.

---

## Honest deferrals — preserved through closure

Every honest deferral from the v10.160-v10.168 build trail is preserved at the closure surface:

| Engine | Deferral surface | Status field |
|---|---|---|
| ENH-193 AML Monitoring | ML alert prioritization | `ml_layer_status` DEFERRED |
| ENH-194 SAR Filing | Wire-level FRC submission | `submission_method` MANUAL_PORTAL |
| ENH-198 Compliance Risk | Trend / Industry / ML | 3 status fields DEFERRED/PARTIAL |
| ENH-199 Examiner Reporting | FFIEC PDF + CBK XML renderers | `export_format_status` STRUCTURED_JSON |
| ENH-195 Regulatory Change | CBK/KRA/FRC programmatic feeds | `automated_feed_status` DEFERRED |
| ENH-195 Regulatory Change | Bidirectional policy linkage | `policy_linkage_status` PARTIAL |
| ENH-196 Policy Management | Document storage | `document_storage_status` META_ONLY |
| ENH-196 Policy Management | E-signature verification | `esignature_verification_status` DEFERRED |
| ENH-197 Compliance Training | LMS integration | `lms_integration_status` DEFERRED |
| ENH-197 Compliance Training | Course content storage | `course_content_status` META_ONLY |

The cockpit displays each in dedicated "Honest deferrals" expanders. The API exposes each in the relevant `/board` endpoint response. **Operators reading the platform see what's missing, not what's fabricated** — same discipline maintained from v10.154's vocabulary endpoint through to closure.

---

## Apply order

After v10.168:

```
1. pages/27_compliance_arc_cockpit.py                     → pages/  (NEW)
2. utils/api_compliance.py                                 → utils/  (NEW)
3. pages/7_admin.py                                        → pages/  (REPLACES — Tier 4D added)
4. scripts/audit.py                                        → scripts/ (REPLACES — G152+G153)
5. app.py                                                  → root    (REPLACES — cockpit registered)
6. tests/test_compliance_arc_closure_v10_169.py            → tests/  (NEW)
7. docs/Master_Prompt_v3.62.md                             → docs/
8. SCOPE_LEDGER.md                                         → root
9. CHANGELOG_v10.169.md                                    → root
```

`git add -A && git commit -m "v10.169 AML/Compliance MODULE CLOSURE — 11th module closure"`. Then `python scripts/audit.py` should print:

```
✅ [G152] compliance_module_closed v10.169 AML/Compliance module closure: 9/9 standards active (100%) — PASS
✅ [G153] compliance_arc_ui_integrated v10.169 AML/Compliance UI integration: 8/8 engines integrated — PASS
Score: 153/153 gates = 100.0% — PASS
```

---

## Phase 3 complete

| Phase | Module | Drops | Closure |
|---|---|---|---|
| 1 | (foundational) | many | various closure ratchets |
| 2 | Treasury | v10.130-v10.155 | v10.155 G150+G151 |
| 3 | AML/Compliance | v10.160-v10.169 | **v10.169 G152+G153** |
| 4 | (next) | TBD | TBD |

**Phase 3 complete.** Phase 4 candidates:
- **Customer/CRM module** — completes the customer lifecycle from onboarding (ENH-191) through ongoing engagement
- **Credit module** — already has many active engines; needs closure ratchet
- Joshua selects.

---

## Summary — fifteen-drop session arc

This session shipped:

| Drop | Theme |
|---|---|
| v10.154-v10.159 | Treasury API completion (post-v10.155 closure follow-up) |
| **v10.160-v10.168** | **AML/Compliance arc build (9 standards across 9 drops)** |
| **v10.169** | **AML/Compliance module closure ceremony** |

**Treasury fully closed (G150+G151) at v10.155.** **AML/Compliance fully closed (G152+G153) at v10.169.** The matching bookends. 

**Quoting the audit script directly:** `Score: 153/153 gates = 100.0% — PASS`. **22/22 closure tests pass.** **AML/COMPLIANCE MODULE FORMALLY CLOSED.**
