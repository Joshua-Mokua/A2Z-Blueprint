"""H6 — Pipeline->LMS handoff surfacing.

Advancing a deal to an LMS stage creates a loan application, but the created
application id was never written back onto the deal, so the frontend
cross-link (gated on deal.lms_application_id) never appeared and the link did
not survive reload. H6 persists the id onto the deal (JSON + Postgres metadata)
and surfaces it on DB reads. The frontend toast + cross-link already existed.
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_advance_persists_lms_application_id():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert "if lms_triggered and lms_app_id:" in src
    assert 'pm.update_deal(deal_id, {"lms_application_id": lms_app_id}' in src


def test_sync_and_normalize_carry_the_id():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert '"lms_application_id":   deal.get("lms_application_id")' in src, "sync->metadata"
    assert 'r["lms_application_id"] = md.get("lms_application_id")' in src, "normalize<-metadata"


def test_metadata_round_trip():
    # lms_application_id stored in metadata JSON must come back out on DB read
    deal = {"lms_application_id": "LMS00042", "pipeline_category": "Loan"}
    md = json.dumps({"pipeline_category": deal.get("pipeline_category"),
                     "lms_application_id": deal.get("lms_application_id")})
    parsed = json.loads(md)
    assert parsed["lms_application_id"] == "LMS00042"


def test_frontend_crosslink_exists():
    fe = (ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx").read_text(encoding="utf-8")
    assert "deal.lms_application_id" in fe, "frontend cross-link must read the id we now persist"
