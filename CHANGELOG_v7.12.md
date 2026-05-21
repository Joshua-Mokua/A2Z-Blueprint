# A2Z MIS 360 — CHANGELOG v7.12

**v7.12 Cards engine + L05 closure — last tractable loop closure (93% loops)**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS — **21st consecutive clean**
**Strategic milestone:** **🎯 v7.x ARCHITECTURAL CEILING REACHED.** 14 of 15 loops WIRED (93%). Only L14 (Channel reliability → CX alerts) remains, deferred to v8.x because it requires Kafka/CDC streaming infrastructure beyond v7.x scope.

---

## What this batch is

**Pure systems-layer expansion.** Zero new pages. Zero new audit gates. Zero composite changes.

**Two things shipped**: a brand-new `utils/cards.py` engine module that didn't previously exist, then closed feedback loop L05 (Card usage → Customer 360 enrichment) by wiring `customer_segmentation.enrich_segment_with_card_usage()` as the consumer of the new engine's outputs.

L05 was DESIGNED_NOT_WIRED for 11 batches — its registry entry pointed to `utils.cards` which didn't exist yet. **v7.12 is the first batch in v7.x where a missing engine was BUILT rather than the registry corrected** — signals a maturity transition: the registry now points to real engines.

---

## What changed

### `utils/cards.py` — new engine module (~250 lines)

`CardsEngine` class with 4 deterministic methods:

| Method | Purpose | Output classifications |
|---|---|---|
| `usage_velocity()` | Frequency + amount metrics over 30/90/365-day windows | HIGH / MEDIUM / LOW / DORMANT |
| `merchant_category_mix()` | ISO 18245 MCC distribution | top_categories + Herfindahl diversity score (0-100) + dominant_category + dominant_pct |
| `geographic_pattern()` | ISO 3166-1 country distribution | HOME_DOMINANT / SPLIT / FOREIGN_HEAVY |
| `card_usage_profile()` | Aggregator — composes 3 above | PUBLISHED_LANGUAGE payload, payload_version=1.0 |

`CardTransaction` dataclass with: txn_id + card_id + customer_id + amount_kes + txn_datetime + merchant_category_code + merchant_country + merchant_city + txn_type.

Honesty rules applied throughout (Rule 1 None for missing inputs, Rule 6 explicit `computed` flags). 35-line `self_test()` runs all 4 methods with realistic txns and asserts payload contract.

### L05 CONSUMER added to `customer_segmentation.py`

`enrich_segment_with_card_usage(base_rfm_segment, card_usage_profile)` — consumes the cards engine PUBLISHED_LANGUAGE payload (validates payload_version=1.0 + pattern marker) and produces an enriched segment.

**Strategy:**
- Segment ordering: `[HIBERNATING < LOST < AT_RISK < POTENTIAL < PROMISING < LOYAL < CHAMPIONS]`
- HIGH velocity + diversity ≥ 50 → uplift segment 1 step (e.g. LOYAL → CHAMPIONS)
- DORMANT velocity → downgrade segment 1 step (LOYAL → PROMISING)
- Orthogonal profile flags:
  - FOREIGN_HEAVY geographic → `TRAVELER_PROFILE`
  - Dominant MCC > 70% → `SPECIALIST_PROFILE`

`consumed_payload_version` stamped per Rule 6 traceability.

### L05 status flipped: DESIGNED_NOT_WIRED → WIRED

In `utils/system_flows.py` registry. Notes cite the cards engine module + segmentation consumer + strategy.

### Charter §8 updated

Wired count 13 → 14 (93%); 1 remaining unwired (L14, deferred). Narrative updated to reflect that L05 is now WIRED via a freshly built engine; only L14 remains with explicit acknowledgement that streaming infrastructure is the v8.x dependency.

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

=== Cards engine self-test ===
  ✓ 5 typical txns → LOW velocity, dominant MCC 47%, SPLIT geo
  ✓ 35 high-velocity diverse txns → HIGH velocity, 87% diversity, HOME_DOMINANT 86%

=== L05 round-trip ===
  cards.card_usage_profile(35 high-vel diverse) → segmentation.enrich(LOYAL)
    → enriched_segment: CHAMPIONS
    → modifier: high_velocity_plus_diverse_categories
  cards.card_usage_profile(1 dormant txn 120d ago) → segmentation.enrich(LOYAL)
    → enriched_segment: PROMISING (1-step downgrade)
    → modifier: card_velocity_dormant
  Invalid payload → INVALID_PAYLOAD status, base passthrough

=== Loop registry ===
  L05: WIRED
  L14: DESIGNED_NOT_WIRED (streaming infra dependency)
  Total: 14/15 = 93%
```

---

## ✅ Twenty-first consecutive clean-first-try

21st batch in a row landing clean.

---

## Comparison vs v7.11

| | v7.11 | v7.12 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%, unchanged) |
| **Feedback loops WIRED** | **13 (87%)** | **14 (93%)** ⭐ |
| Engines reading from registry | 6 | 6 (unchanged) |
| **Engine modules with consumers** | **4 of 5** | **5 of 5** ⭐ (cards consumed) |
| Standards in UI | 60 | 60 (unchanged) |
| Clean-first-try streak | 20 | **21** |

---

## Strategic narrative — v7.x architectural ceiling reached

| Batch | Loops | Stocks | ACL | Composites |
|---|---|---|---|---|
| v7.0 | foundation | 0/6 | 0/6 | 3 registered |
| v7.1 | +L01 | 3/6 | 0/6 | 3 |
| v7.2 | 9/15 (60%) | 3/6 | 0/6 | 3 |
| v7.3 | 10/15 (67%) | 4/6 | 0/6 | 3 |
| v7.4 | 11/15 (73%) | 6/6 (100%) | 0/6 | 3 |
| v7.5 | 12/15 (80%) | 6/6 | 0/6 | 4 |
| v7.6 | 13/15 (87%) | 6/6 | 0/6 | 4 surfaced (page 91) |
| v7.7 | 13/15 | 6/6 | 0/6 | 4 |
| v7.8 | 13/15 | 6/6 | 0/6 | 4 + 4 per-domain |
| v7.9 | 13/15 | 6/6 | 0/6 | 4 + 4 per-domain |
| v7.10 | 13/15 | 6/6 | 3/6 (50%) | 4 + 4 per-domain |
| v7.11 | 13/15 | 6/6 | 5/6 (~85%) | 4 + 4 per-domain |
| **v7.12** | **14/15 (93%)** ⭐ | **6/6** | **5/6 (~85%)** | **4 + 4 per-domain** |

**The v7.x systems-layer expansion campaign has reached its natural architectural ceiling**:
- Every loop that can be closed without platform-level infrastructure IS closed
- Every stock that can be ACL-wired IS wired (capital_base intentionally engine-derived)
- Every composite that can be surfaced IS surfaced

**The remaining v7.x→v8.x gap is purely infrastructure**: L14 streaming, live FLEXCUBE handler implementations, CBS aggregate writer scripts.

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — cards engine + customer_segmentation consumer compile + round-trip-tested.
2. **Cards engine has no UI surface yet** — page 19 / page 34 customer 360 future candidate; v7.13+.
3. **L05 consumer applies 1-step uplift / 1-step downgrade** — intentionally conservative; banks may want 2-step for outliers.
4. **Profile flags (TRAVELER_PROFILE / SPECIALIST_PROFILE) are orthogonal to segment** — don't change RFM but enrich downstream cross-sell/churn.
5. **L14 deliberately deferred** — closure requires Kafka streaming infrastructure beyond v7.x scope.
6. **Cards engine doesn't read from system_invariants registry** — thresholds (HIGH velocity = >30 txns/30d) are bank-policy configurable; could become future invariants.
7. **Cards engine self_test is internal only** — not yet picked up by audit suite's V24 test runner (still 2211 tests).
8. **No new audit gate** — G104+G105 sufficient.
9. **CardTransaction dataclass is minimal** — production may have richer schemas; engine takes only what it needs.
10. **Diversity score uses Herfindahl-style index** — banks may prefer Shannon entropy or alternative.
11. **Velocity classification uses fixed thresholds** — banks may want band-segment-specific thresholds.
12. **5 cumulative engine corrections in v7.x — v7.12 is the FIRST batch where the registered engine was actually built** rather than corrected. Signals a maturity transition.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.13 Surface cards engine on page 34 Customer 360** | Completes L05 chain (engine + loop + UI); integration 60 → 61 |
| (2) | v7.13 Add CBS aggregate writer scripts | Populates CBS synthetic side of v7.10/v7.11 ACL |
| (3) | v7.13 Live FLEXCUBE handler implementations | v8.x readiness |
| (4) | v7.13 Add audit gate G106 'every WIRED loop has round-trip producer + consumer' | Harden v7.x pattern |
| (5) | L14 streaming infrastructure | Beyond v7.x scope |

**Strong recommendation: v7.13 = Surface cards engine on page 34 Customer 360** — completes the L05 chain (engine built v7.12, surfaced v7.13); pushes integration tally 60 → 61; final UI batch in the v7.x series before transitioning to v8.x infrastructure track.

---

🎯 **L05 closed via fresh engine module — 14 of 15 loops WIRED (93%). v7.x architectural ceiling reached.**

⭐ **21st consecutive clean-first-try. The remaining gap (L14, live FLEXCUBE, CBS writers) is infrastructure-bound and shifts to v8.x.**
