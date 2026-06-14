"""Hardening Batch H1 — Create/Refer Deal: server-authoritative identity.

Root cause of the Create-Deal failure: validate_create_payload requires
staff_code + staff_name, but get_current_user yields only JWT claims
(username/role) — not identity. The routes now re-fetch the caller's record
from users.json and inject staff_code/staff_name when the client omits them.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── source-scan (always runs) ───────────────────────────────────────────
def test_create_and_refer_inject_identity():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    # both routes must re-derive identity from users.json
    assert src.count("server-authoritative caller identity") >= 1
    assert "the server is authoritative for caller identity" in src
    assert src.count("_UM_id().users.get(") >= 2, \
        "both create and refer must inject identity from users.json"


# ── behavioral (needs utils importable) ─────────────────────────────────
def test_validate_create_contract():
    from utils.api_pipeline_mutations import validate_create_payload
    base = {
        "client_name": "Acme", "deal_value": 1000,
        "product_type": "Business Loan", "stage": "Lead",
    }
    # missing identity -> rejected (this is the failure the fix prevents)
    ok, reason = validate_create_payload(dict(base))
    assert not ok and "staff_code" in reason

    # with identity injected -> accepted
    ok, _ = validate_create_payload({**base, "staff_code": "0001",
                                     "staff_name": "William Mwangi"})
    assert ok
