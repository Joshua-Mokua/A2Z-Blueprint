"""Integration tests for v10.477 — Phase O3-A Channel Simulators.

5 banking channels simulated: RTGS, SWIFT, ATM, USSD, M-Pesa.
"""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Package structure ───────────────────────────────────────────────

def test_v10477_channels_package_exists():
    assert (REPO / "utils" / "channels").is_dir()
    assert (REPO / "utils" / "channels" / "__init__.py").exists()


def test_v10477_channels_init_exports_api():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import (
        ChannelStatus, ChannelRequest, ChannelResponse,
        BaseChannelSimulator, get_channel, submit_channel,
        list_channels, SUPPORTED_CHANNELS,
    )
    assert callable(submit_channel)
    assert callable(get_channel)
    assert isinstance(SUPPORTED_CHANNELS, dict)
    # v10.477 ships 5; later batches add more. At least 5 must be present.
    assert len(SUPPORTED_CHANNELS) >= 5


def test_v10477_list_channels_has_5():
    """v10.477 introduced 5; later batches add more. The 5 must all be there."""
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import list_channels
    o3a_set = {"atm", "mpesa", "rtgs", "swift", "ussd"}
    assert o3a_set.issubset(set(list_channels()))


# ── ChannelStatus enum ──────────────────────────────────────────────

def test_v10477_channel_status_has_17_values():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import ChannelStatus
    expected = {
        "success", "failed_timeout", "failed_insufficient_funds",
        "failed_limit_exceeded", "failed_invalid_payload",
        "failed_beneficiary_reject", "failed_sanctions_hit",
        "failed_rate_limited", "failed_host_unavailable", "failed_cutoff",
        "failed_card_blocked", "failed_pin_exceeded",
        "failed_dispenser_jam", "failed_session_timeout",
        "failed_network_drop", "failed_kyc_limit",
        "failed_callback_timeout", "failed_other",
    }
    actual = {s.value for s in ChannelStatus}
    assert expected.issubset(actual)


# ── RTGS ────────────────────────────────────────────────────────────

def test_v10477_rtgs_valid_high_value():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("rtgs",
        payload={"amount": 5_000_000, "debit_account": "1234567890",
                  "credit_account": "0987654321",
                  "beneficiary_bank_bic": "BARCKENX"},
        amount=5_000_000, debit_account="1234567890",
        credit_account="0987654321", reference="TEST-RTGS-001",
        actor="300011", seed=11)
    assert r.channel == "rtgs"
    # Realistic latency band
    assert 5_000 <= r.latency_ms <= 500_000


def test_v10477_rtgs_rejects_below_threshold():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("rtgs",
        payload={"amount": 50_000, "debit_account": "x", "credit_account": "y",
                  "beneficiary_bank_bic": "BARCKENX"},
        amount=50_000, reference="REJ-LOW", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD
    assert "minimum" in (r.error_message or "").lower()


def test_v10477_rtgs_produces_pacs_008_envelope():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    # Use a seed that gives success (need to try a few)
    for seed in range(20):
        r = submit_channel("rtgs",
            payload={"amount": 5_000_000, "debit_account": "1234567890",
                      "credit_account": "0987654321",
                      "beneficiary_bank_bic": "BARCKENX"},
            amount=5_000_000, debit_account="1234567890",
            credit_account="0987654321", reference=f"PACS-{seed}",
            actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert r.raw_response["MsgType"].startswith("pacs.008")
            assert "GrpHdr" in r.raw_response
            assert "CdtTrfTxInf" in r.raw_response
            return
    pytest.fail("no success in 20 seeds — failure rate too high")


# ── SWIFT ───────────────────────────────────────────────────────────

def test_v10477_swift_mt103_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r = submit_channel("swift",
        payload={"mt_type": "103", "ordering_customer": "JOHN",
                  "beneficiary_bic": "CHASUS33",
                  "beneficiary_name": "JANE", "amount": 12500.00},
        amount=12500, currency="USD", debit_account="111",
        credit_account="222", reference="MT103-TEST",
        actor="t", seed=22)
    assert r.channel == "swift"


def test_v10477_swift_rejects_unknown_mt_type():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("swift",
        payload={"mt_type": "999"},
        reference="REJ-MT", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_swift_mt103_envelope_contains_block4():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(20):
        r = submit_channel("swift",
            payload={"mt_type": "103", "ordering_customer": "JOHN",
                      "beneficiary_bic": "CHASUS33",
                      "beneficiary_name": "JANE", "amount": 12500.00},
            amount=12500, reference=f"MT103-{seed}", actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            raw = r.raw_response.get("RawMT", "")
            # Block 4 contains :20: (reference), :32A: (value date/amount)
            assert ":20:" in raw and ":32A:" in raw
            return
    pytest.fail("no SWIFT success in 20 seeds")


# ── ATM ─────────────────────────────────────────────────────────────

def test_v10477_atm_withdrawal_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 5000, "terminal_id": "T1"},
        amount=5000, currency="KES", reference="ATM-1", actor="t", seed=33)
    assert r.channel == "atm"
    # ATM fast: latency 100ms-5s
    assert 100 <= r.latency_ms <= 5_000


def test_v10477_atm_rejects_non_digit_pan():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "abc12345",
                  "amount": 5000},
        amount=5000, reference="REJ-PAN", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_atm_rejects_non_100_multiple():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 4150},
        amount=4150, reference="REJ-AMT", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_atm_envelope_is_iso8583_0200():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(20):
        r = submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                      "amount": 5000, "terminal_id": "T1"},
            amount=5000, reference=f"ATM-ENV-{seed}", actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert r.raw_response["MessageType"] == "0200"
            # PAN must be masked
            pan = r.raw_response["PrimaryAccountNumber"]
            assert "*" in pan
            return
    pytest.fail("no ATM success in 20 seeds")


# ── USSD ────────────────────────────────────────────────────────────

def test_v10477_ussd_valid_session():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r = submit_channel("ussd",
        payload={"ussd_code": "*334#", "msisdn": "254712345678",
                  "text": "1*1*5000*1234"},
        reference="USSD-1", actor="t", seed=44)
    assert r.channel == "ussd"


def test_v10477_ussd_rejects_missing_terminator():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("ussd",
        payload={"ussd_code": "*334", "msisdn": "254712345678"},
        reference="REJ-USSD", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_ussd_payload_over_182_rejected():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("ussd",
        payload={"ussd_code": "*334#", "msisdn": "254712345678",
                  "text": "x" * 200},
        reference="REJ-LONG", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


# ── M-Pesa ──────────────────────────────────────────────────────────

def test_v10477_mpesa_stk_push_valid():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 1500,
                  "paybill": "174379"},
        amount=1500, currency="KES", reference="MPESA-1",
        actor="t", seed=55)
    assert r.channel == "mpesa"


def test_v10477_mpesa_rejects_non_kenya_msisdn():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "447712345678", "amount": 1500,
                  "paybill": "174379"},
        amount=1500, reference="REJ-MSISDN", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_mpesa_rejects_above_single_txn_limit():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    r = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 200_000,
                  "paybill": "174379"},
        amount=200_000, reference="REJ-LIMIT", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD


def test_v10477_mpesa_envelope_has_checkout_request_id():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    for seed in range(20):
        r = submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"MPESA-ENV-{seed}",
            actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            assert "CheckoutRequestID" in r.raw_response
            assert r.raw_response["CheckoutRequestID"].startswith("ws_CO_")
            return
    pytest.fail("no M-Pesa success in 20 seeds")


# ── Event bus integration ───────────────────────────────────────────

def test_v10477_each_channel_emits_call_event():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel
    from utils.event_bus import get_event_bus

    submit_channel("rtgs",
        payload={"amount": 5_000_000, "debit_account": "1", "credit_account": "2",
                  "beneficiary_bank_bic": "BARCKENX"},
        amount=5_000_000, reference="EV-RTGS", actor="t", seed=1)
    submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 100},
        amount=100, reference="EV-ATM", actor="t", seed=1)
    submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 100, "paybill": "1"},
        amount=100, reference="EV-MPESA", actor="t", seed=1)

    bus = get_event_bus()
    for chan in ("rtgs", "atm", "mpesa"):
        events = bus.query(event_type=f"integration.{chan}.call", limit=5)
        assert events, f"no integration.{chan}.call events emitted"


def test_v10477_success_emits_success_event():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    from utils.event_bus import get_event_bus

    # Try until we get a success
    for seed in range(30):
        r = submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                      "amount": 100},
            amount=100, reference=f"SUCC-{seed}", actor="t", seed=seed)
        if r.status == ChannelStatus.SUCCESS:
            bus = get_event_bus()
            corr_chain = bus.query(correlation_id=r.correlation_id, limit=5)
            types = {e.event_type for e in corr_chain}
            assert "integration.atm.call" in types
            assert "integration.atm.success" in types
            return
    pytest.fail("no ATM success in 30 seeds")


def test_v10477_failure_emits_failure_event():
    for k in list(sys.modules):
        if "channels" in k or "event_bus" in k: del sys.modules[k]
    from utils.channels import submit_channel, ChannelStatus
    from utils.event_bus import get_event_bus

    # Force a validation failure
    r = submit_channel("rtgs",
        payload={"amount": 50_000},  # below threshold
        amount=50_000, reference="FAIL-EV", actor="t", seed=1)
    assert r.status == ChannelStatus.FAILED_INVALID_PAYLOAD
    bus = get_event_bus()
    chain = bus.query(correlation_id=r.correlation_id, limit=5)
    types = {e.event_type for e in chain}
    assert "integration.rtgs.failure" in types


# ── Deterministic seeding ───────────────────────────────────────────

def test_v10477_same_seed_produces_same_outcome():
    for k in list(sys.modules):
        if "channels" in k: del sys.modules[k]
    from utils.channels import submit_channel
    r1 = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 5000},
        amount=5000, reference="SEED-A", actor="t", seed=999)
    r2 = submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111111111111111",
                  "amount": 5000},
        amount=5000, reference="SEED-B", actor="t", seed=999)
    assert r1.status == r2.status


# ── G363 + regression ──────────────────────────────────────────────

def test_v10477_g363_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10477_o3a_channel_simulators
    r = gate_v10477_o3a_channel_simulators()
    assert r["passed"], r.get("violations")


def test_v10477_o2_complete_preserved():
    """Phase O2 gates (G361 + G362) must still pass."""
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
    )
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]


def test_v10477_o8_isolation_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10477_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
