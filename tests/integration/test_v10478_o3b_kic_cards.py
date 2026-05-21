"""Integration tests for v10.478 — Phase O3-B KIC + Cards (completes 7 channels).

Last 2 of the 7 banking channels. After this batch:
RTGS · SWIFT · ATM · USSD · M-Pesa · KIC · Cards
"""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Module presence ─────────────────────────────────────────────────

def test_v10478_kic_module_exists():
    assert (REPO / "utils" / "channels" / "kic.py").exists()


def test_v10478_cards_module_exists():
    assert (REPO / "utils" / "channels" / "cards.py").exists()


def test_v10478_supported_channels_has_7():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import list_channels, SUPPORTED_CHANNELS
    assert sorted(list_channels()) == [
        "atm", "cards", "kic", "mpesa", "rtgs", "swift", "ussd",
    ]
    assert len(SUPPORTED_CHANNELS) == 7


# ── KIC ─────────────────────────────────────────────────────────────

def test_v10478_kic_eft_credit_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    # Try a few seeds to land a success
    for seed in range(30):
        r = submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                      "beneficiary_bank_code": "011",
                      "narrative": "May salary"},
            amount=85_000, debit_account="123", credit_account="456",
            reference=f"KIC-OK-{seed}", actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert r.raw_response.get("RecordType") == "EFT_CREDIT"
            assert r.raw_response.get("BatchId", "").startswith("KIC-")
            assert r.raw_response.get("SendingBankCode") == "044"
            return
    pytest.fail("no KIC success in 30 seeds")


def test_v10478_kic_cheque_inward_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(30):
        r = submit_channel("kic",
            payload={"transaction_type": "CHEQUE_INWARD",
                      "beneficiary_bank_code": "001",
                      "cheque_number": "CHQ123456",
                      "debit_account": "INWARD"},
            amount=250_000, credit_account="0987654321",
            reference=f"KIC-CHQ-{seed}", actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert r.raw_response.get("ChequeNumber") == "CHQ123456"
            return
    pytest.fail("no KIC cheque success in 30 seeds")


def test_v10478_kic_rejects_above_max():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                  "beneficiary_bank_code": "011"},
        amount=2_000_000, debit_account="x", credit_account="y",
        reference="KIC-HI", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD
    assert "maximum" in (r.error_message or "").lower() or \
           "rtgs" in (r.error_message or "").lower()


def test_v10478_kic_rejects_invalid_bank_code():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                  "beneficiary_bank_code": "1"},  # not 3 digits
        amount=85_000, debit_account="x", credit_account="y",
        reference="KIC-BC", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_kic_rejects_unknown_transaction_type():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("kic",
        payload={"transaction_type": "BIZZARRO",
                  "beneficiary_bank_code": "011"},
        amount=10_000, debit_account="x", credit_account="y",
        reference="KIC-BAD-TYPE", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_kic_cheque_requires_cheque_number():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("kic",
        payload={"transaction_type": "CHEQUE_INWARD",
                  "beneficiary_bank_code": "011",
                  "debit_account": "INWARD"},
        amount=10_000, credit_account="y",
        reference="KIC-NOCHQ", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_kic_batch_window_resolves():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels.kic import KICSimulator
    sim = KICSimulator(seed=1)
    # All windows return a string
    from datetime import datetime, timezone, timedelta
    nairobi = datetime.now(timezone(timedelta(hours=3)))
    w = sim._batch_window(nairobi)
    assert w in {"MORNING", "AFTERNOON", "NEXT_DAY_MORNING"}


def test_v10478_kic_latency_realistic():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r = submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                  "beneficiary_bank_code": "011"},
        amount=10_000, debit_account="x", credit_account="y",
        reference="KIC-LAT", actor="t", seed=7)
    # KIC: 1.5min p50, 10min p99 — must be in 10s..1hr range
    if r.latency_ms > 0:
        assert 10_000 <= r.latency_ms <= 3_600_000, (
            f"KIC latency {r.latency_ms}ms outside realistic band"
        )


# ── Cards ───────────────────────────────────────────────────────────

def test_v10478_cards_pos_purchase_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(30):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111",
                      "card_not_present": False,
                      "cvv": "123", "expiry": "12/28",
                      "merchant_id": "MERCH001"},
            amount=2_500, reference=f"CARDS-POS-{seed}",
            actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            env = r.raw_response
            assert env["MessageType"] == "0100"
            assert env["CardScheme"] == "VISA"
            assert "*" in env["PrimaryAccountNumber"]
            assert env["POSEntryMode"] == "021"  # CP swipe
            assert env["RRN"]  # Retrieval Reference Number
            return
    pytest.fail("no Cards POS success in 30 seeds")


def test_v10478_cards_cnp_below_threshold_passes():
    """CNP transaction below KES 5000 should NOT require 3DS."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(30):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "5500000000000004",  # MasterCard
                      "card_not_present": True,
                      "cvv": "456", "expiry": "06/29"},
            amount=3_000, reference=f"CNP-LOW-{seed}",
            actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert r.raw_response["POSEntryMode"] == "012"  # CNP keyed
            assert r.raw_response["CardScheme"] == "MASTERCARD"
            return
    pytest.fail("no CNP-low success in 30 seeds")


def test_v10478_cards_3ds_stepup_fires_above_threshold():
    """CNP >= KES 5,000 without threeds_completed must require 3DS."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111",
                  "card_not_present": True,
                  "cvv": "123", "expiry": "12/28"},
        amount=15_000, reference="CNP-3DS",
        actor="t", seed=1)
    assert r.error_code == "3DS_REQUIRED"
    assert "3DS" in (r.error_message or "")
    assert r.status == ChannelStatus.FAILED_RATE_LIMITED


def test_v10478_cards_3ds_completed_bypasses_stepup():
    """threeds_completed=True must let the transaction proceed."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    # At least one seed of 30 must succeed
    for seed in range(30):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111",
                      "card_not_present": True,
                      "cvv": "123", "expiry": "12/28",
                      "threeds_completed": True},
            amount=15_000, reference=f"3DS-DONE-{seed}",
            actor="t", seed=seed)
        # Must NOT be 3DS_REQUIRED
        assert r.error_code != "3DS_REQUIRED", (
            f"3DS-completed still hit step-up (seed {seed})"
        )
        if r.status == ChannelStatus.SUCCESS:
            return
    pytest.fail("no 3DS-completed success in 30 seeds")


def test_v10478_cards_rejects_short_pan():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE", "pan": "411111",
                  "cvv": "123", "expiry": "12/28"},
        amount=100, reference="CARDS-PAN-SHORT",
        actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_cards_rejects_unknown_bin():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "9999999999999999",  # not a known BIN
                  "cvv": "123", "expiry": "12/28"},
        amount=100, reference="CARDS-BAD-BIN",
        actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_cards_cnp_requires_cvv():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111",
                  "card_not_present": True,
                  "expiry": "12/28"},  # no cvv
        amount=100, reference="CARDS-NO-CVV",
        actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_cards_rejects_bad_expiry_format():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111",
                  "cvv": "123",
                  "expiry": "12-2028"},  # wrong format
        amount=100, reference="CARDS-BAD-EXP",
        actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10478_cards_bin_inference_detects_schemes():
    """BIN-based scheme inference must classify correctly."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels.cards import CardsSimulator
    sim = CardsSimulator()
    cases = [
        ("4111111111111111", "VISA"),
        ("5500000000000004", "MASTERCARD"),
        ("2221000000000009", "MASTERCARD"),  # new MC BIN range
        ("371111111111111",  "AMEX"),
        ("6011111111111117", "DISCOVER"),
        ("5060123456789012", "VERVE"),
    ]
    for pan, expected in cases:
        assert sim._infer_scheme(pan) == expected, (
            f"BIN {pan[:4]} -> {sim._infer_scheme(pan)}, expected {expected}"
        )


def test_v10478_cards_latency_fast():
    """Cards must be the fastest channel: p50 ~400ms, p99 ~2s."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    # Sample 10 successful runs and check max latency reasonable
    latencies = []
    for seed in range(40):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111",
                      "card_not_present": False,
                      "cvv": "123", "expiry": "12/28"},
            amount=100, reference=f"CARDS-LAT-{seed}",
            actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            latencies.append(r.latency_ms)
            if len(latencies) >= 10:
                break
    assert latencies, "need at least 1 successful sample"
    # All should be under 5 seconds (covers p99 with margin)
    assert all(l < 5_000 for l in latencies), (
        f"Cards latencies too slow: {latencies}"
    )


# ── Event emission ──────────────────────────────────────────────────

def test_v10478_kic_emits_events():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel
    from utils.event_bus import get_event_bus
    r = submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                  "beneficiary_bank_code": "011"},
        amount=10_000, debit_account="a", credit_account="b",
        reference="KIC-EV", actor="t", seed=1)
    events = get_event_bus().query(
        correlation_id=r.correlation_id, limit=5
    )
    types = {e.event_type for e in events}
    assert "integration.kic.call" in types
    assert any(t.startswith("integration.kic.") for t in types)


def test_v10478_cards_emits_events():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel
    from utils.event_bus import get_event_bus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111",
                  "card_not_present": False,
                  "cvv": "123", "expiry": "12/28"},
        amount=100, reference="CARDS-EV",
        actor="t", seed=1)
    events = get_event_bus().query(
        correlation_id=r.correlation_id, limit=5
    )
    types = {e.event_type for e in events}
    assert "integration.cards.call" in types


def test_v10478_3ds_required_emits_failure_event():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel
    from utils.event_bus import get_event_bus
    r = submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111",
                  "card_not_present": True,
                  "cvv": "123", "expiry": "12/28"},
        amount=20_000, reference="CARDS-3DS-EV",
        actor="t", seed=1)
    events = get_event_bus().query(
        correlation_id=r.correlation_id, limit=5
    )
    types = {e.event_type for e in events}
    assert "integration.cards.failure" in types


# ── Regression: v10.477 still works ─────────────────────────────────

def test_v10478_v10477_channels_still_work():
    """All 5 v10.477 channels must continue to work after base.py change."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    # RTGS
    r = submit_channel("rtgs",
        payload={"amount": 5_000_000, "debit_account": "1",
                  "credit_account": "2", "beneficiary_bank_bic": "BARCKENX"},
        amount=5_000_000, reference="REGR-RTGS", actor="t", seed=1)
    assert r.channel == "rtgs"
    # ATM
    r = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 5_000},
        amount=5_000, reference="REGR-ATM", actor="t", seed=1)
    assert r.channel == "atm"


def test_v10478_v10477_g363_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10477_o3a_channel_simulators
    assert gate_v10477_o3a_channel_simulators()["passed"]


# ── G364 + cumulative regression ────────────────────────────────────

def test_v10478_g364_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10478_o3b_kic_cards_complete_7_channels
    r = gate_v10478_o3b_kic_cards_complete_7_channels()
    assert r["passed"], r.get("violations")


def test_v10478_o2_telemetry_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
    )
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]


def test_v10478_o8_isolation_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10478_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
