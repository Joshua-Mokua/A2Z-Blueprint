"""H7 — DB-first detail + mutation hydration for pipeline deals.

The list read was DB-first but detail + mutation routes read only JSON, so the
294 Postgres-seeded deals 404'd on open and could not be advanced. H7 adds
_get_or_hydrate_deal: JSON-first, else load from Postgres and register on the
request-scoped manager so PipelineManager mutations operate on it (then H5
syncs back to the DB).
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_helper_exists_and_is_not_recursive():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert "def _get_or_hydrate_deal" in src
    # body must call pm.get_deal, never itself (recursion guard)
    start = src.index("def _get_or_hydrate_deal")
    body = src[start:start + 1400]
    assert "deal = pm.get_deal(deal_id)" in body
    # only the def line references the helper name inside its own block
    assert body.count("_get_or_hydrate_deal") == 1, "helper must not call itself"


def test_all_six_routes_hydrate():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    # detail, update, advance, validate, cancel-request, cancel-approve
    assert src.count("deal = _get_or_hydrate_deal(pm, deal_id)") == 6
    # the old JSON-only first-read must be gone from those routes
    assert "    deal = pm.get_deal(deal_id)\n" not in src.replace(
        "    deal = pm.get_deal(deal_id)\n    if deal:\n        return deal", "")  # helper line ok
