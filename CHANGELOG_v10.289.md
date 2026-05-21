# Changelog — v10.289 Trade Finance Mobile App (lone)

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 181/181 gates PASS = 100.0%
**G162 Rebase:** 3950 → 3959 (+9 CBK; rationale: CBK Mobile Banking reference locked across module + gate + cockpit + manifest)

---

## Summary

Lone-standard cluster — closes the v10.80-deferred ENH-279 via the
v10.283 SWIFT pattern. 15 active standards remain planned: CIMS arc
(#166–#180).

The TradeFinanceCorporatePortalEngine (ENH-271) already supports both
web and mobile clients via the same dataclass-driven Python data layer.
This batch adds the missing mobile-specific surface — session lifecycle,
device registry, push notification routing, offline draft tracking —
without duplicating any portal validation logic.

---

## Standard activated (v10.80 deferral closed)

| ID      | Name                          | Subcategory     | Risk |
|---------|-------------------------------|-----------------|------|
| ENH-279 | Trade Finance Mobile App      | trade_finance   | Cat C |

Flipped status="active", implementation_batch="v10.289".

The G137 trade_finance arc closure gate has been updated to accept
ENH-279 in either state (legacy v10.80 deferral OR v10.289 mobile
cockpit fulfillment) so the historical deferral rationale remains
valid while the new active path is now explicitly recognized.

---

## Engine module

### `utils/trade_finance_mobile.py` (#279)

`TradeFinanceMobileEngine` — mobile session + device + push
notification + offline draft registry. Thin wrapper; never
replicates portal validation logic.

Byte-for-byte invariants:
- `MOBILE_SESSION_STATES` (5: INITIATED, AUTHENTICATED, ACTIVE, EXPIRED, REVOKED) — Rule 4 (EXPIRED + REVOKED terminal)
- `DEVICE_PLATFORMS` (4: IOS, ANDROID, REACT_NATIVE, PROGRESSIVE_WEB_APP)
- `DEVICE_STATES` (3: REGISTERED, REVOKED, BLOCKED)
- `PUSH_NOTIFICATION_TYPES` (5: LC_AMENDMENT_DECISION, DOCUMENT_REQUEST, MESSAGE_FROM_BANK, INSTRUMENT_STATUS_CHANGE, SECURITY_ALERT)
- `PUSH_DELIVERY_OUTCOMES` (4: DELIVERED, FAILED, EXPIRED, SUPPRESSED)
- `DRAFT_TYPES` (4: LC_APPLICATION, AMENDMENT_REQUEST, DOCUMENT_UPLOAD, CORPORATE_MESSAGE)
- `DRAFT_STATES` (4: DRAFT, SYNCED, SUBMITTED, DISCARDED) — Rule 4 (SUBMITTED + DISCARDED terminal)
- `DEFAULT_SESSION_TIMEOUT_MINUTES = 15`
- `DEFAULT_DEVICE_REGISTRATION_TTL_DAYS = 90`
- `DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS = 30`
- `DEFAULT_OFFLINE_DRAFT_TTL_HOURS = 72`
- `CBK_MOBILE_BANKING_REFERENCE = "CBK Guidance Note on Mobile Banking"`
- `DPA_MOBILE_REFERENCE = "Data Protection Act 2019"`

Key methods:
- `register_mobile_session`, `transition_session_state`
- `register_device`, `revoke_device`
- `record_push_notification` (validates type and outcome)
- `record_offline_draft`
- `session_metrics(days=30)` — sessions + notification delivery rate
- `active_sessions_for_user(username)` — sessions in AUTHENTICATED or ACTIVE

---

## Page

### `pages/104_tf_mobile.py`

5 tabs (well within G4 ceiling):
1. Sessions — register + lifecycle + active-for-user listing
2. Devices — register + revoke
3. Push notifications — record outcomes per device
4. Offline drafts — queue tracking with state transitions
5. Metrics — session counts, notification delivery rate, revocation rate alert

Canonical imports throughout (G177):
```python
from utils.core_audit import audit_log
from pages._access import require_access
require_access("trade_finance.tf_mobile")
```

---

## Audit gate

### G181 — `gate_trade_finance_mobile_registered`

Locks the engine + 7 enum tuples + 4 default constants + 2 regulatory references byte-for-byte.

Checks:
1. `utils.trade_finance_mobile` imports and exposes `TradeFinanceMobileEngine`.
2. All 7 enum tuples byte-for-byte against the spec above.
3. `ALLOWED_SESSION_TRANSITIONS["EXPIRED"]` and `["REVOKED"]` are `()` (Rule 4).
4. `ALLOWED_DRAFT_TRANSITIONS["SUBMITTED"]` and `["DISCARDED"]` are `()` (Rule 4).
5. All 4 default spec constants match.
6. Two regulatory reference strings: CBK Guidance Note on Mobile Banking + Data Protection Act 2019.
7. ENH-279 is active and tagged v10.289.
8. Page 104 exists on disk.

### G137 — `gate_trade_finance_arc_closed` (updated)

Now accepts ENH-279 in either state:
- `planned` with documented `DEFERRED` marker (legacy v10.80 deferral) OR
- `active` with `implementation_batch="v10.289"` and `pages/104_tf_mobile.py` present (v10.289 fulfillment)

Both paths preserve the trade_finance arc closure ratchet. Historical reasoning for the v10.80 deferral remains valid; the v10.289 fulfillment is now the canonical state.

---

## G162 ratchet

```
Before:    3950 (established_in v10.288)
After:     3959 (established_in v10.289)
Delta:     +9 (all CBK)
Scope history entries: 43
```

The 9 new CBK tokens come from `CBK_MOBILE_BANKING_REFERENCE = "CBK Guidance Note on Mobile Banking"` being locked in the engine module, echoed in G181's summary, the cockpit caption, the Tier 49 admin entry, and the manifest description.

---

## Tier registration

`Tier 49 — Trade Finance Mobile (v10.289, Phase 2B)` added to `pages/7_admin.py` with the engine documented.

---

## Manifest entry

`104_tf_mobile.py` registered with all 7 required fields:
- `department_primary`: "trade_finance"
- `module_path`: "trade_finance.tf_mobile"
- `current_module_key`: "tf_mobile"
- `icon`: "📱"

---

## Files in this release

```
utils/trade_finance_mobile.py                 NEW (#279, ~430 lines)
utils/standards_registry.py                   flipped ENH-279 to active
scripts/audit.py                              +G181 + G137 update for ENH-279 fulfillment
pages/7_admin.py                              +Tier 49
pages/104_tf_mobile.py                        NEW (5-tab cockpit)
pages/_manifest.json                          +104 entry
data/audit_baselines.json                     g162 rebase to 3959
CHANGELOG_v10.289.md                          NEW (this document)
```

---

## Audit summary

```
  Score: 181/181 gates = 100.0% — PASS
```

315 of 330 standards active. Only the CIMS arc (#166–#180, 15 standards) remains planned.

Next batch: **v10.290 — CIMS arc batch 1 (4 standards from #166–#180)**. The CIMS arc is the largest cluster left in Phase 2B and will run across 4 batches (v10.290–v10.293).
