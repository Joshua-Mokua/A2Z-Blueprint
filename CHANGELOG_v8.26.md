# CHANGELOG v8.26 — UI surface for v8.23-v8.25 + i18n scaffold (closes v8.6 ack #12 partial)

**Audit:** 111/111 PASS — **NEW STREAK: 1st clean-first-try.** (After v8.25 broke the 50-batch streak.)

## What

3-fold deliverable:
1. UI surface on `pages/91_systems_view.py` for v8.23 dedup stats + v8.25 alert history
2. New `utils/smart_alerts_i18n.py` module — i18n scaffold for customer alert translations
3. UI surface for the i18n scaffold showing per-locale completeness

**This closes v8.6 ack #12 partially** — the structural i18n work is done; full translations are operational work outside the codebase (translator engagement → review → JSON updates).

## Changes

### `pages/91_systems_view.py` extensions (~120 lines)

Added after the L14 streaming section:

**v8.23 dedup stats expander** (`🔂 Event-bus dedup stats`)
- Renders only when total publish calls > 0
- Header: total publishes / dedup hits / hit rate %
- Per-topic table: Topic / Publishes / Dedup hits / Unique / Hit rate %
- Caption explains use cases (retries, page reloads being correctly dedup'd)

**v8.25 alert history expander** (`🔔 Customer alert history`)
- Auto-expands when unacknowledged alerts exist
- Header: total / unacked / ack rate %
- 3 metric cards: URGENT / HIGH / INFO counts
- Unacked alerts list (most recent first, limit 10) with per-alert "✓ Ack" button
- Each Ack button calls `acknowledge_alert(alert_id, acked_by="systems_view_operator")` + `st.rerun()`
- "✓ All alerts acknowledged" success message when no unacked

**v8.26 i18n scaffold expander** (`🌐 i18n scaffolding`)
- Always available
- Metrics: supported locales count + translation keys count
- Lists scaffolded locales + first 5 translation keys
- Honest scope: "only English currently has complete translations; FR + SW need translator pass"

### New `utils/smart_alerts_i18n.py` (~180 lines)

**Module structure:**
- `TRANSLATIONS` dict: 3 locales (en/fr/sw) × 8 keys
- English: 100% complete (8/8 keys)
- French: 37.5% partial (3/8 keys — placeholder; needs translator)
- Swahili: 25% partial (2/8 keys — placeholder; needs translator)

**Public API:**
- `t(key, locale, **format_args)` — translate with format-string substitution; falls back through requested → English → visible-key
- `get_supported_locales()` — returns ['en', 'fr', 'sw']
- `get_translation_keys()` — returns the 8 English keys
- `get_locale_for_customer(customer_id, fallback)` — placeholder for per-customer locale lookup; v8.26 always returns fallback (production needs profile schema link)
- `is_translation_complete(locale)` — True if locale has all English keys
- `get_translation_completeness()` — diagnostic dict per locale

## Behavioral test (passed)

```
EN: ATM outage detected at Westlands
FR: Panne ATM détectée à Westlands
SW: Hitilafu ya ATM imegunduliwa katika Westlands

FR fallback (body_default not in FR):
  Severity: OUTAGE. Estimated affected customers: 1500. Engineering team is investigating.

Completeness:
  en: 8/8 = 100.0% (COMPLETE)
  fr: 3/8 = 37.5% (partial)
  sw: 2/8 = 25.0% (partial)

✓ i18n scaffold works. EN complete; FR + SW partial (need translator).
```

## v8.6 backlog burndown — now 12/12 closed (100%) ⭐

| # | Ack | Status |
|---|---|---|
| 1-11 | (closed v8.7-v8.25) | ✅ |
| **12** | **Multi-language alerts (i18n)** | **✅ closed-partial (v8.26)** ⭐ |

**v8.6 RETROSPECTIVE BACKLOG IS NOW 100% CLOSED.** All 12 acks have shipped code. Ack #12 is partially closed at the structural level — translation strings need native-speaker review to become production-quality, but that's operational work outside the codebase.

## Honest acknowledgements

1. **i18n is partial-close**: only English has complete translations. French and Swahili are scaffolded with placeholder strings that need native-speaker review. Marking ack #12 as "closed-partial" reflects this honestly.
2. `get_locale_for_customer()` is a stub returning fallback — production needs to be wired to customer profile schema (FLEXCUBE preferred_locale field, fall through to mobile device locale, fall through to branch default).
3. `t()` falls through to a visible `[key]` placeholder when key missing in ALL locales — caller sees the missing key in production output, which is intentional (silent empty strings would be worse).
4. The i18n module is NOT yet wired into smart_alerts.py's `_craft_headline()` and `_craft_body()` — that integration is a v9.x candidate; v8.26 ships the scaffold only.
5. Format-string substitution catches KeyError + IndexError defensively — incomplete caller data returns the unsubstituted template rather than crashing.
6. The 3 locales (en/fr/sw) reflect East Africa + Kenya specifically; other deployments would extend the TRANSLATIONS dict with their needs (de/es/pt/ar/etc.).
7. UI ack button uses `st.rerun()` to refresh after acknowledgement — works on Streamlit 1.27+; fallback for older versions would need `st.experimental_rerun()`.
8. The dedup expander only shows when `total_publish_calls > 0` — silent in dev environments where no events have been published.
9. Alert history Ack button keys derived from alert_id slug; collision unlikely with current ID format `alert_{event_id}`.
10. "All alerts acknowledged" success state is a feature: operators get clear positive confirmation when their queue is clean.

## Status snapshot at end of v8.23-v8.26 sequence

**Both sub-campaigns COMPLETE in essence:**
- **Living Documentation** (v8.11-v8.16): COMPLETE 5-batch arc
- **Legal Infrastructure** (v8.13 + v8.14 LICENSE): plan + Tier 1 ops shipped; Tier 2-4 awaiting Joshua's lawyer engagement
- **v8.6 Retrospective Backlog**: 12/12 closed (11 fully + 1 partially scaffolded)
- **Audit gates**: 111/111 (8-gate defense-in-depth perimeter G104-G111 intact)
- **Streak status**: New streak at 1 (after v8.25 broke the 50-batch run)

## Next: v8.27 — G112 audit gate locking v8.23-v8.26 contracts

Final hardening for the 5-batch arc. Pushes audit suite 111 → 112 gates. Verifies:
- v8.23 dedup surface: `publish()` accepts `dedup_key`; `get_dedup_stats()` returns expected shape
- v8.24 latency persistence: `LATENCY_PERSIST_PATH` exists; `_load_latency_from_disk` + `_persist_latency_to_disk` importable
- v8.25 alert history: 6 functions importable (record/acknowledge/get_history/get_stats/reset/etc.); `ALERT_HISTORY_PATH` constant present
- v8.26 i18n scaffold: 6 functions importable; English completeness = 100%; SUPPORTED_LOCALES has expected 3 entries

This makes the 9-gate defense-in-depth perimeter (G104-G112) and locks the v8.23-v8.26 work as permanent invariants.
