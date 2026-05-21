# Changelog — v10.280 Command Centre Cluster

**Date:** 2026-05-08  
**Phase:** 2A — Active-standards expansion  
**Cluster:** Command Centre (Standards #311-#320)  
**Audit:** 173/173 gates PASS = 100.0%  
**G162 Rebase:** 3803 → 3818 (+15)

---

## Summary

Phase 2A v10.280 ships the **Command Centre cluster** — 8 engines covering 10 standards (#311-#320). This is the executive workbench layer for MD/CEO/CFO/CRO/COO/Board roles: real-time dashboards, severity-based alert routing, driver-based forecasting with what-if + tornado sensitivity, natural-language query, mobile briefing packs, secure board portal, crisis playbook + incident command, strategic initiative tracking with BSC linkage, and centralized stakeholder communications.

This is the **17th closed cluster** in Phase 2A and the **77th consecutive clean batch** since v10.193.

---

## Standards delivered

| Standard | Title | Engine |
|----------|-------|--------|
| ENH-311 | Strategic Pulse Dashboard | command_centre_dashboard |
| ENH-312 | Executive Alerts & Intelligent Notifications | command_centre_alert_routing |
| ENH-313 | Predictive Forecasting | command_centre_forecasting |
| ENH-314 | What-If Scenario Simulator | command_centre_forecasting |
| ENH-315 | Natural-Language Query Interface | command_centre_nl_query |
| ENH-316 | Mobile Executive Briefing | command_centre_mobile_board |
| ENH-317 | Crisis Playbook & Incident Command | command_centre_crisis |
| ENH-318 | Strategic Initiative Tracking + BSC | command_centre_strategic_initiatives |
| ENH-319 | Stakeholder Communications | command_centre_stakeholder_comms |
| ENH-320 | Secure Board Portal | command_centre_mobile_board |

10 standards across 8 engines (#313+#314 share forecasting; #316+#320 share mobile_board).

---

## Files changed

### New engines (8 modules, 4,280 lines including page)

```
utils/command_centre_dashboard.py                333 lines
utils/command_centre_alert_routing.py            485 lines
utils/command_centre_forecasting.py              457 lines
utils/command_centre_nl_query.py                 402 lines
utils/command_centre_mobile_board.py             583 lines
utils/command_centre_crisis.py                   526 lines
utils/command_centre_strategic_initiatives.py    576 lines
utils/command_centre_stakeholder_comms.py        475 lines
pages/95_command_centre.py                       443 lines
```

### Modified

```
utils/standards_registry.py    — ENH-311..320 status="active", batch="v10.280"
scripts/audit.py               — gate_command_centre_registered as G173
pages/7_admin.py               — Tier 42 entries for 8 engines
pages/_manifest.json           — 95_command_centre.py with department_primary
data/audit_baselines.json      — G162 rebase 3803 → 3818, scope_history append
```

---

## Audit gate G173 — command_centre_registered

Locks 17+ invariant categories byte-for-byte across all 8 modules:

- **Dashboard:** DASHBOARD_WIDGET_TYPES (8: KPI_TILE/TREND_CHART/HEATMAP/ALERT_LIST/DRILL_TABLE/MAP_VIEW/GAUGE/TEXT_BRIEFING) + WIDGET_PRIORITIES (4: TOP/HIGH/MEDIUM/LOW) + REFRESH_INTERVALS_SECONDS (5: 30/60/300/900/3600)
- **Alert routing:** EXEC_ALERT_SEVERITIES (5: CRITICAL/HIGH/MEDIUM/LOW/INFO) + EXEC_ROUTING_TARGETS (6: MD/CEO/CFO/CRO/COO/BOARD) + ROUTING_RULE_STATES (3) Rule 4 + SUPPRESSION_REASONS (5) + DEFAULT_DEDUPE_WINDOW_MINUTES=15 + DEFAULT_DAILY_QUOTA_PER_ROLE=50
- **Forecasting:** FORECAST_TARGETS (5: REVENUE/NPL_RATIO/DEPOSITS/CHURN_RATE/COST_INCOME_RATIO) + FORECAST_HORIZONS_PERIODS (4: 1/3/6/12) + FORECAST_MODEL_STATES (4) Rule 4 + DEFAULT_CONFIDENCE_PCT=80 + DEFAULT_BAND_WIDTH_PCT=15 + SPEC_DEVIATION_NOTE
- **NL Query:** QUERY_INTENT_TYPES (8) + QUERY_FEEDBACK_OUTCOMES (3) + DEFAULT_FALLBACK_CONFIDENCE_PCT=30 + HIGH_CONFIDENCE_THRESHOLD_PCT=70 + SPEC_DEVIATION_NOTE
- **Mobile/Board:** BRIEFING_PACK_STATES (4) + BRIEFING_SECTION_TYPES (5) + BOARD_MEETING_STATES (5) + BOARD_VOTE_OUTCOMES (4: APPROVE/REJECT/ABSTAIN/RECUSED) + BOARD_PAPER_TYPES (6) + ACTION_ITEM_STATES (4)
- **Crisis:** INCIDENT_SEVERITIES (4: SEV1-4) + INCIDENT_STATES (6) Rule 4 + PLAYBOOK_TYPES (8) + DECISION_TYPES (5) + STAKEHOLDER_TYPES (6)
- **Initiatives:** INITIATIVE_RAG_STATES (3) + INITIATIVE_PHASES (5) Rule 4 + MILESTONE_STATES (4) Rule 4 + BSC_PERSPECTIVES (4)
- **Comms:** STAKEHOLDER_COMM_TYPES (6) + COMM_CHANNELS (5) + COMM_STATES (5) Rule 4 + TEMPLATE_STATES (3) Rule 4 + RESPONSE_OUTCOMES (5)

Result: **0 violations.**

---

## G162 rebase 3803 → 3818 (+15)

8th consecutive Phase 2A rebase (v10.271 +36, v10.273 +13, v10.274 +20, v10.276 +9, v10.277 +29, v10.278 +4, v10.279 +29, v10.280 +15).

**Token movements:**
- FLEXCUBE +1 (core-banking-system reference in standards_registry description)
- Kenya +1 (country reference in standards_registry description)
- CBK +37 (Kenyan-regulator test fixtures in stakeholder_comms self-tests + G173 docstring + Tier 42 admin description + ENH-311..320 Standard() metadata)
- KES -20 (net reduction; Command Centre is currency-neutral by design)

All increases are byte-for-byte regulatory citation + jurisdiction-bound test fixture references locked under G173. Same precedent as v10.271 (+28 CBK SLA citations).

---

## Key API surfaces

**Dashboard (#311):**
```python
dash.register_kpi_widget({widget_id, widget_name, widget_type, priority,
                          refresh_seconds, visible_to_roles}, actor, reason)
dash.dashboard_snapshot(role) -> {widgets, stale_count}
```

**Alert Routing (#312):**
```python
alerts.register_routing_rule({rule_id, rule_name, min_severity,
                              target_roles, dedupe_window_minutes,
                              daily_quota_per_role}, actor, reason)
alerts.route_alert({alert_id, severity, alert_type}) ->
    {routed, recipients, suppression_reason}
```

**Forecasting (#313+#314):**
```python
fc.forecast(model_id, horizon_periods, drivers={driver: pct}) ->
    {baseline, lower_band, upper_band, confidence_pct}
fc.what_if(model_id, shocks={driver: pct}, horizon_periods=1) ->
    {baseline_outcome, shocked_outcome, delta, delta_pct}
fc.sensitivity_tornado(model_id, shock_pct=10) ->
    {rows sorted by abs_range desc}
```

**NL Query (#315):**
```python
nlq.submit_query(query_text, requester_role) ->
    {answer, confidence_pct, intent, structured_query, fallback_used}
```

**Mobile/Board (#316+#320):**
```python
mb.publish_pack(pack_id, actor, reason)
mb.fetch_pack_for_role(pack_id, viewer_role) -> {available, sections}
mb.record_vote(meeting_id, paper_id, board_member, vote, actor)  # rejects duplicate, non-member
```

**Crisis (#317):**
```python
crisis.activate_incident({incident_id, title, severity}, playbook_id,
                         actor, reason)
crisis.transition_incident_state(incident_id, new_state, actor, reason)
crisis.record_after_action_review(incident_id, {summary, lessons,
                                                  improvements}, actor, reason)
```

**Initiatives (#318):**
```python
init.update_initiative_rag(initiative_id, new_rag, actor, reason)
    # auto-promotes phase to AT_RISK on RAG=RED + IN_PROGRESS
init.link_to_bsc(initiative_id, bsc_perspective, kpi_id, actor, reason)
init.portfolio_summary() -> {total, active, rag_distribution,
                              phase_distribution, at_risk_count}
```

**Stakeholder Comms (#319):**
```python
comms.send_communication({comm_id, stakeholder_type, subject, body,
                           channel}, actor)
comms.record_response(comm_id, {response_id, outcome, received_at}, actor)
    # auto-transitions SENT → ACKNOWLEDGED
```

---

## Streamlit page (pages/95_command_centre.py)

7 top-level tabs covering all 10 standards (G4-compliant 7-tab limit):

1. **📊 Dashboard + Briefing** (#311 + #316) — nested sub-tabs Live Dashboard / Briefing Pack
2. **🚨 Alert Routing** (#312)
3. **📈 Forecasting & What-If** (#313 + #314)
4. **💬 NL Query** (#315)
5. **⚠️ Crisis & Incidents** (#317)
6. **🎯 Initiatives & BSC** (#318)
7. **🏛️ Comms + Board** (#319 + #320) — nested sub-tabs Stakeholder Comms / Board Portal

`audit_log()` calls present on all 6 register_* form submissions (G3 compliant).

---

## Next batches

- **v10.281** IT/Digital pt1 (#291-295)
- **v10.282** IT/Digital pt2 (#296-300)
- **v10.283** SWIFT (#272 — Trade Finance lone)
- **v10.284** QA Map document for Ecobank presentation
- **v10.285** Phase 2A retrospective + master prompt update + memory rebaseline
