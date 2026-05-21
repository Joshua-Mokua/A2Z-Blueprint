# A2Z MIS 360 — CHANGELOG v5.83

**v5.83 Thirteenth Integration Batch — Channel SLA (#91 SLA)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 9th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🌐 CHANNELS AXIS COMPLETE.** Channel Performance #91 (v5.80 cost/mix/availability) + Channel SLA Monitoring (v5.83 uptime/MTBF/latency) both wired into same DFS-team page. Cumulative: **30 of 116 standards integrated.** Thirteenth integration batch.

---

## Strategic milestone — Channels axis complete

A DFS-team member opening `pages/73_channels.py` now sees:

| Tab | Type | Source |
|---|---|---|
| 📊 Overview | Daily monitoring | original |
| 📋 Channel Detail | Daily monitoring | original |
| 💳 Transactions | Daily monitoring | original |
| 🔄 Incidents | Daily logging | original (Manual Incident Log) + **NEW Channel SLA Monitoring** ⭐ |
| ⚙️ Config | Configuration | original |
| 📈 BSC | Performance | original |
| 🚀 Channel Performance (Standard #91) | **Strategic analytics** | v5.80 |

**Mirrors v5.82's pattern for Branch axis**: strategic + operational analytics together in one page.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.83 wires **`channel_sla.py`** (Standard #91 SLA component) — the engine for uptime tracking, MTBF/MTTR, latency distribution, and combined per-channel SLA severity.

---

## What was modified

### `pages/73_channels.py` — Channel SLA Monitoring sub-tab added
**480 → 864 lines (+384)**

**Top-level tab list UNCHANGED at 7** (already at G4 limit). Used **sub-tab containment pattern** (5th application after v5.73, v5.76, v5.79, v5.81) in tab[3] "🔄 Incidents":

| Sub-tab | Status |
|---|---|
| 📝 Manual Incident Log | preserved byte-for-byte |
| **📡 Channel SLA Monitoring (Standard #91 SLA)** | **NEW** |

The other 6 top-level tabs remain completely untouched.

### Channel SLA Monitoring — 5 inner tabs

**🟢 Uptime % per channel** — selectable channel from 8 CHANNELS. Engine returns:
- uptime_pct, target_pct, severity (GREEN/AMBER/RED)
- ongoing_outages_count for outages without ended_at (Rule 6 transparency)
- downtime_seconds, outage_count

Per-channel target dictionary `CHANNEL_UPTIME_TARGET_PCT` byte-for-byte:
- MOBILE/INTERNET/API: **99.9%**
- ATM/USSD/AGENT/POS: **99.5%**
- BRANCH: **99.0%**

Severity bands: `UPTIME_GREEN_GAP_MAX_PP=0.0` (must be at or above) / `UPTIME_AMBER_GAP_MAX_PP=0.5pp` / RED above.

**📈 MTBF & MTTR** — Mean Time Between Failures + Mean Time To Repair:
- MTBF requires ≥2 outages to compute intervals; single-outage = None
- MTTR requires ≥1 completed outage; 0 outages = None
- Page handles None gracefully with "—" display

**⚡ Response Time Distribution** — P50/P90/P99 vs `CHANNEL_LATENCY_TARGET_P99_MS` byte-for-byte:

| Channel | P99 target |
|---|---|
| MOBILE / INTERNET / API | 2000 ms |
| POS | 3000 ms |
| ATM / AGENT | 5000 ms |
| USSD | 8000 ms |
| BRANCH | 30000 ms |

Severity computed from P99 vs target. Surfaces `observations_excluded` for invalid response times (Rule 6).

**📊 Multi-Channel SLA Summary** — per-channel table with:
- uptime_pct + uptime_severity
- p99_ms + latency_severity
- combined_severity = worst-of(uptime, latency)
- GREEN/AMBER/RED counts at top
- Executive escalation guidance

**🌳 Engine Reference** — uptime + latency targets per channel + severity gap thresholds with business rationale (mobile/internet customers expect <2s; ATM tolerates 5s; branch ops 30s).

### Engine file — UNCHANGED
`utils/channel_sla.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 4 engine paths verified end-to-end

**Demo dataset**: 5 outages across 4 channels + 490 latency observations across MOBILE/ATM/USSD/API for the 30-day period 2026-04-01 to 2026-04-30.

**uptime_pct (4 channels):**

| Channel | Uptime | Target | Severity | Outages |
|---|---|---|---|---|
| MOBILE | 99.9653% | 99.9% | **GREEN** | 1 (30 min PARTIAL) |
| ATM | 99.3056% | 99.5% | **AMBER** | 2 (4hr FULL + 2hr PARTIAL) |
| BRANCH | 100.0% | 99.0% | **GREEN** | 0 |
| AGENT | 99.1667% | 99.5% | **AMBER** | 1 (6hr FULL) |

**MTBF/MTTR:**

| Channel | Outages | MTTR | MTBF |
|---|---|---|---|
| ATM | 2 | **180 min** | **283 hr** |
| MOBILE | 1 | 30 min | None (need ≥2) |
| BRANCH | 0 | None | None |

**response_time_distribution (4 channels):**

| Channel | Count | P50 | P99 | Target | Severity |
|---|---|---|---|---|---|
| MOBILE | 150 | 1576ms | **2470ms** | 2000ms | AMBER |
| ATM | 80 | 4170ms | **5978ms** | 5000ms | AMBER |
| USSD | 60 | 5367ms | **8737ms** | 8000ms | AMBER |
| **API** | 200 | 1074ms | **1772ms** | 2000ms | **GREEN** ⭐ |

**channel_sla_summary** — combined severity (worst-of):
- MOBILE: GREEN uptime + AMBER latency = AMBER combined
- ATM: AMBER + AMBER = AMBER combined
- AGENT: AMBER uptime + None latency = AMBER combined (latency None falls back to uptime)
- BRANCH/INTERNET/USSD/POS: GREEN combined

Distribution: 4 GREEN + 4 AMBER + 0 RED.

**Engine logic confirmed**: tier differentiation works correctly across uptime + latency dimensions; worst-of severity composition handles None cases gracefully.

---

## Critical engine API specifics documented

These were verified during build (10 findings):

1. **`ChannelOutage`** requires outage_id/channel/started_at as REQUIRED + optional ended_at + severity defaulting to "PARTIAL". Outages without ended_at treated as ongoing through period_end and counted in `ongoing_outages_count` (Rule 6).

2. **`LatencyObservation`** requires obs_id/channel/response_time_ms/observed_at — all REQUIRED, no optionals.

3. **`uptime_pct`** returns dict with `total_seconds`, `downtime_seconds`, `uptime_pct`, `target_pct`, `severity`, `ongoing_outages_count`, `outage_count`. Engine takes the FULL outages list and `channel` parameter, filters internally — no need to pre-filter.

4. **`incident_mtbf_mttr`** returns `mttr_minutes=None` and `mtbf_hours=None` when not computable (need ≥1 completed outage for MTTR, ≥2 outages for MTBF). Page displays "—" instead of None.

5. **`response_time_distribution`** returns 0 observation_count when no observations match the channel filter. Page handles with a warning.

6. **`channel_sla_summary`** returns `period_start`, `period_end`, `channels` (list). Each channel entry has `combined_severity` = worst-of(uptime_severity, latency_severity).

7. **🆕 `combined_severity` ignores latency severity when latency_severity is None** — channels without latency observations get combined_severity = uptime_severity. BRANCH in test data has no latency obs, gets GREEN combined despite N/A latency.

8. **🆕 `CHANNELS` constant in `channel_sla.py` is 8 channels** (BRANCH/ATM/MOBILE/INTERNET/USSD/AGENT/POS/API) — **DIFFERS from `channel_performance.py`** which has 10 (adds CALL_CENTER, RTGS, SWIFT). Engines authored separately with slightly different scopes.

9. **`UPTIME_GREEN_GAP_MAX_PP=0.0`** means GREEN requires being AT or above target (no slack); `UPTIME_AMBER_GAP_MAX_PP=0.5` means AMBER allows up to 0.5pp below target; > 0.5pp gap = RED.

10. For MOBILE/INTERNET/API the **99.9% target with 0.5pp AMBER gap** means uptime must be **≥99.4%** to avoid RED — extremely tight tolerance reflecting always-on digital channel expectations.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "ChannelSLA #91-SLA: uptime MOBILE 99.9653% target=99.9% severity=GREEN")
audit_log("IFRS_ENGINE_USED", uname, "ChannelSLA #91-SLA: MTBF/MTTR ATM outages=2 mttr=180.0 mtbf=283.0")
audit_log("IFRS_ENGINE_USED", uname, "ChannelSLA #91-SLA: latency MOBILE P50=1576.0ms P99=2470.3ms severity=AMBER")
audit_log("IFRS_ENGINE_USED", uname, "ChannelSLA #91-SLA: summary G=4 A=4 R=0")
```

---

## ✅ Ninth clean-first-try batch in a row

Audit clean on first attempt (after v5.74, v5.76, v5.77, v5.78, v5.79, v5.80, v5.81, v5.82). G3 + G4 lessons embedded in process. Sub-tab containment pattern proven for the 5th time.

---

## Honesty discipline visualised

- **Per-channel uptime targets surfaced** byte-for-byte from `CHANNEL_UPTIME_TARGET_PCT`
- **Per-channel latency targets surfaced** byte-for-byte from `CHANNEL_LATENCY_TARGET_P99_MS`
- **Severity gap thresholds explicit** — GREEN at-or-above, AMBER ≤0.5pp gap, RED above
- **Ongoing outages flagged** — outages without ended_at (Rule 6 transparency)
- **MTBF/MTTR None handling** — clear "—" instead of misleading values when uncomputable
- **Combined severity worst-of logic** — explicit in caption + multi-channel summary
- **None latency severity transparency** — channel without latency monitoring falls back to uptime; documented in honest acknowledgements
- **CHANNELS constant inconsistency between engines documented** — 8 vs 10 channels not hidden
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G91 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.82 pages — unchanged
- The 6 other top-level tabs in `73_channels.py` — completely untouched
- The existing manual incident logging flow — byte-for-byte preserved inside its new sub-tab wrapper
- The Channel Performance tab from v5.80 — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.82

| | v5.82 | v5.83 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **29** | **30** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 11 | **11** (re-enhances 73_channels.py from v5.80) |
| Lines added across pages this batch | +372 (branch_log) | +384 (channels) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 4-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **5-sub-tab nesting** under Channel SLA Monitoring within tab[3] which is itself one of 7 top-level tabs.

2. **30 of 116 integrated** — 86 standards remain library-only.

3. **All sub-tabs use hard-coded demo dataset** — outages and latency observations are NOT loaded from JSON files. Production deployment would need:
   - `channel_outages.json` (matching `ChannelOutage` schema)
   - `channel_latency.json` (matching `LatencyObservation`)
   
   The demo dataset is deliberately constructed to demonstrate all 4 engine paths with realistic severity bands; production data ingestion is a deferred enhancement.

4. **The new Channel SLA Monitoring sub-tab does NOT integrate with the page's existing manual `incident_log` data store** — engine outputs are computed live and audit-logged but not persisted. Manual incidents logged through the Manual Incident Log sub-tab continue to flow into the existing channels.json store separately. **The two flows are deliberately decoupled** because the engine operates on a different data shape (outages with start/end timestamps + latency obs with response_time_ms vs the manual log's free-text descriptions).

5. **🆕 CHANNELS constant differs between `channel_performance.py` (10 channels) and `channel_sla.py` (8 channels)** — channel_performance includes CALL_CENTER/RTGS/SWIFT which channel_sla excludes. Reflects different scopes (cost/mix vs uptime/latency) but creates a minor UI inconsistency: Channel Performance tab from v5.80 shows 10 channels in some dropdowns while Channel SLA from v5.83 shows 8. **Documented as known quirk; not a logic bug**. Future engine harmonization could reconcile.

6. **Latency severity is BINARY when latency_severity is None** — channels without latency observations don't get a None vs RED differentiation; combined_severity falls back to uptime_severity. Correct (cannot grade latency without data) but means a fully-functional channel with no latency monitoring will appear identical to a fully-monitored healthy channel in the summary. Production deployment should ensure latency monitoring covers all critical channels.

7. **Severity gap thresholds are tight** — GREEN requires AT or above target (0pp gap), so a channel with target 99.9% uptime is RED if it drops to 99.4% (0.5pp gap is upper AMBER). **Deliberate** — digital channels should be near-perfect — but means the GREEN bar is high. Production deployment may want to consider how often AMBER/RED triggers operational reviews.

8. **MTBF computation requires ≥2 outages** — single-outage channels return None MTBF. Page handles gracefully but newly-deployed channels with limited outage history can't have MTBF measured for some time.

---

## Strategic narrative — operational integration push complete

| Batch | Axis | Type |
|---|---|---|
| v5.80 | Branch Performance #90 | Strategic |
| v5.80 | Channel Performance #91 | Strategic |
| v5.82 | Branch Ops Excellence #92 | **Operational** |
| **v5.83** | **Channel SLA Monitoring** | **Operational** |

With v5.82 + v5.83, both Branch and Channels axes are complete. The bank's two largest user bases (35 Branch Managers + DFS team) now have engine-driven analytics for both their strategic dimensions (P&L/peer benchmarking for branches, cost/mix/availability for channels) AND their operational dimensions (wait/error/TAT/incidents for branches, uptime/MTBF/latency/SLA for channels).

**The major functional integration coverage is now in place:**
- v5.78 daily risk-management trifecta (IRRBB + LCR/NSFR + Stress)
- v5.79 people management
- v5.80 + v5.82 Branch axis complete (strategic + operational)
- v5.80 + v5.83 Channels axis complete (strategic + operational)
- v5.81 regulatory framework arc complete (PG/02 + PG/03 + ICAAP + PG/04 + BSD Returns)

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Predictive Performance | predictive_performance + performance_insights | Forward-looking analytics, complements v5.79 retrospective HR Performance |
| (2) | Project / Audit / Compliance | smaller engines | Multiple smaller integrations |
| (3) | Channel Income | channel_income | Third Channels enhancement (cost-to-serve, optimization) |
| (4) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With both Branch and Channels axes now complete, recommend **(1) Predictive Performance** for v5.84 — would shift from operational to forward-looking analytics, a different kind of value delivery for HR/management.

---

**Cumulative tally:** 116 standards delivered, **30 integrated into UI via 3 dedicated pages + 11 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🌐 **Channels axis COMPLETE** (Channel Performance #91 + Channel SLA Monitoring).
