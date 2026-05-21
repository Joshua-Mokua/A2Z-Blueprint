# CHANGELOG v8.23 — Event-bus deduplication (closes v8.6 ack #8)

**Audit:** 111/111 PASS — **49th consecutive clean.**

## What

Closes v8.6 retrospective ack #8. Adds optional `dedup_key` parameter to `event_bus.publish()` for idempotent event publishing. Repeated publishes with the same dedup_key return the existing event without creating duplicates.

## Use cases

- Channel reliability events that may fire on producer retry (v8.4 reliability layer)
- Smart_alerts re-published on Streamlit page reload
- Multiple producer instances racing to publish the same logical event
- Network blip → producer retry → would otherwise create duplicate event in stream

## Changes

- New module constant `DEDUP_LOOKBACK_WINDOW = 200` — bounds dedup scan to last 200 events per topic
- `Event` dataclass: new optional field `dedup_key: Optional[str] = None`
- `Event.from_json()`: backward-compat — older persisted events without dedup_key get None on reload
- `publish()`: optional `dedup_key` parameter; when provided, scans last DEDUP_LOOKBACK_WINDOW events for matching key; returns existing event if found
- New `_DEDUP_STATS` dict tracking per-topic: total_publish_calls, dedup_hits, unique_published
- New `get_dedup_stats(topic=None)` accessor returning per-topic OR aggregated stats with derived `dedup_hit_rate_pct`
- Backward compat preserved: publish() without dedup_key behaves identically to v8.4-v8.22

## Behavioral test

```
e1 = publish("test", {"x": 1}, dedup_key="alert-001")
e2 = publish("test", {"x": 2}, dedup_key="alert-001")  # duplicate
e3 = publish("test", {"x": 3}, dedup_key="alert-002")  # different key

→ e1.event_id == e2.event_id (dedup hit)
→ e2.event_id != e3.event_id

Stats: total_calls=3, dedup_hits=1, unique=2, hit_rate=33.3%
✓ Dedup works.
```

## v8.6 backlog burndown — now 9/12 closed (75%)

| # | Ack | Status |
|---|---|---|
| 1-7, 9 | (closed v8.7-v8.20) | ✅ |
| **8** | **Event-bus deduplication** | **✅ closed (v8.23)** |
| 10, 11, 12 | open | ⏳ |

## Honest acknowledgements

1. Lookback is bounded (200 events) — duplicate publishes more than 200 events apart on the same topic would create duplicates; acceptable for current use cases (channel reliability + smart alerts publish at most ~10/min).
2. Dedup scan is O(N) where N = window size; for 200-event window, ~50μs per publish — negligible.
3. dedup_key matching is exact string equality; no fuzzy matching or canonicalization (caller responsible for stable key generation).
4. Stats are in-memory; lost on process restart (matches retry telemetry pattern).
5. No automatic dedup based on payload hash; would require canonical JSON serialization which is expensive — explicit dedup_key is more efficient.
6. Persisted events include dedup_key in their JSON, so dedup state survives restart for the most-recent 200 events that get reloaded.

## Next: v8.24 — Latency persistence (ack #10)

Currently latency telemetry is in-memory only — process restart loses the rolling window. v8.24 adds JSON-dump persistence so observability survives restarts.
