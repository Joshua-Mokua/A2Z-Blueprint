# CHANGELOG v8.25 — Alert-history persistence (closes v8.6 ack #11)

**Audit:** 111/111 PASS — **STREAK BROKEN: first-try audit FAILED at G2** (caught legitimate new I/O before FOUNDATIONAL allowlist was updated; passes after fix).

⚠️ **Honest acknowledgement of streak interruption**: the 50-batch clean-first-try streak ended at v8.24. v8.25 required two audit runs to land — first run failed at G2 direct_io because the new persistence I/O in `utils/smart_alerts.py` wasn't allowlisted; second run passed after extending FOUNDATIONAL. Per the strict convention this breaks the streak. **v8.26+ rebuilds from streak count 1.** The discipline working as designed: G2 correctly flagged unclassified I/O before letting it ship.

## What

Closes v8.6 retrospective ack #11. Alert history (which alerts fired, when, who acked them) now persists to disk so it survives process restarts. Same persistence pattern as v8.24 (latency state) applied to a different surface.

## Changes to `utils/smart_alerts.py`

### New module-level state
- `ALERT_HISTORY_PATH = Path("smart_alerts_data") / "alert_history.json"`
- `ALERT_HISTORY_MAX_ENTRIES = 500` — rolling window
- `_ALERT_HISTORY` in-memory list + `_ALERT_HISTORY_LOCK` + `_ALERT_HISTORY_LOADED` one-shot flag

### New functions
- `_load_alert_history()` — defensive JSON loader; silently degrades on errors
- `_persist_alert_history()` — atomic write via tmp+replace
- `record_alert_history(alert)` — append + persist; **idempotent on alert_id** (matches v8.23 dedup pattern)
- `acknowledge_alert(alert_id, acked_by)` — mark as acked with timestamp + actor; idempotent
- `get_alert_history(limit, only_unacknowledged)` — read accessor; newest-first
- `get_alert_history_stats()` — total / acked / unacked / acknowledgement_rate_pct / by_tier breakdown
- `reset_alert_history()` — admin clear; deletes disk file

### Hooked into SmartAlertsConsumer
- `consume()` now calls `record_alert_history(alert.to_dict())` after each alert is generated
- Idempotent on alert_id so repeat-consume of same event doesn't duplicate history

### FOUNDATIONAL allowlist extended
- Added `utils/event_bus.py` (was missing — pre-existing v8.4 persistence I/O actually was unallowlisted but G2's I/O detection apparently didn't trigger on the v8.4 write pattern)
- Added `utils/smart_alerts.py` (new in v8.25)
- These join the existing 26 entries

## Behavioral test (passed)

```
=== Record 4 alerts (3 unique + 1 duplicate alert_id) ===
  total=3 (dedup'd to 3, not 4) ✓
  by_tier={'URGENT': 1, 'HIGH': 1, 'INFO': 1}

=== Acknowledge alert_2 ===
  acked=1, unacked=2 ✓

=== Simulate process restart (clear in-memory + reset _ALERT_HISTORY_LOADED) ===

=== Verify reload from disk ===
  total=3 (preserved) ✓
  acked=1 (ack state preserved) ✓
  unacknowledged: ['alert_3', 'alert_1']  ←  alert_2 ack survived restart

✓ Alert history persists across restart. Ack state preserved.
```

## v8.6 backlog burndown — now 11/12 closed (92%)

| # | Ack | Status |
|---|---|---|
| 1-10 | (closed v8.7-v8.24) | ✅ |
| **11** | **Alert-history persistence** | **✅ closed (v8.25)** |
| 12 | Multi-language alerts (i18n) | ⏳ |

**Only 1 ack remains open.**

## Honest acknowledgements

1. **The streak break**: v8.25 was first-try-FAIL → fixed → PASS. Per strict convention, this breaks the 50-batch clean-first-try streak. The audit working correctly (catching unclassified I/O) is a feature, not a bug; my workflow miss (ran audit before allowlist update) is the failure. **Recorded honestly per Charter §6 + Rule 6 honesty discipline.**
2. Idempotency on `alert_id` matches the v8.23 event_bus dedup pattern at a different layer — both layers preventing duplicate work for the same logical event.
3. 500-entry rolling window covers ~1 month at typical alert rates (1-2/hour); operators wanting longer history can persist to external sink.
4. `acknowledge_alert()` returns True even if already acknowledged — caller doesn't need to handle the race; idempotency-friendly.
5. No automatic deletion of acknowledged alerts (they roll out of the window naturally as new alerts come in); future enhancement could segregate acked-vs-unacked retention.
6. `record_alert_history()` is hooked into `SmartAlertsConsumer.consume()` — every consume() call persists newly-generated alerts; if a caller bypasses consume() and directly creates CustomerAlert objects, history won't capture those (acceptable since direct creation is for testing only).
7. Disk format matches v8.24 (saved_at_iso + entries dict for future-proofing additional metadata).
8. No multi-process write coordination — last-writer-wins on concurrent processes; acceptable for telemetry/observability layer.

## Next: v8.26 — UI surface for v8.23-v8.25 + i18n scaffold (ack #12 partial)

Render dedup stats + alert history on admin systems-view + scaffold i18n for alert messages (loading translation strings from JSON). i18n won't be fully functional in v8.26 (would need full translation work) but the SCAFFOLD will close ack #12's structural part.
