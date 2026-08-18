"""Diagnose why a freshly-created pipeline deal may be invisible.

Checks the three possible causes at once:
  1. JSON <-> Postgres divergence  (deal in the JSON store but not in the
     DB that the list/analytics read first -> best-effort sync failed)
  2. Cascade scope                 (deal owner outside the viewer's scope)
  3. Draft flag                    (drafts are hidden from analytics)

Usage:
    python scripts\\diag_pipeline_store.py [viewer_username]
        viewer_username defaults to william0001 (whole-bank view).

Read-only. Touches no data.
"""
import os
import sys

# Allow running as `python scripts\diag_pipeline_store.py` from the repo root:
# put the project root (parent of scripts/) on sys.path so `utils` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    viewer = sys.argv[1] if len(sys.argv) > 1 else "william0001"

    # 1) JSON store — the canonical create target.
    from utils.core import PipelineManager
    pm = PipelineManager()
    json_deals = pm.get_deals()
    print(f"\n=== JSON store (where create writes first): {len(json_deals)} deal(s) ===")
    for d in json_deals:
        print(f"  {str(d.get('id')):<10} stage={str(d.get('stage')):<14} "
              f"owner={d.get('staff_code')}/{d.get('staff_name')} "
              f"draft={bool(d.get('draft'))} "
              f"cat={d.get('pipeline_category') or d.get('deal_category')} "
              f"val={d.get('deal_value')}")
    json_ids = {str(d.get("id")) for d in json_deals}

    # 2) Postgres — the source the list + analytics read first.
    db_ids = set()
    try:
        from utils.api import _db_available
        if _db_available():
            from utils.db import db as _db
            rows = _db.fetch_all(
                "SELECT id, stage, staff_code, amount "
                "FROM pipeline_deals ORDER BY id", ())
            print(f"\n=== Postgres pipeline_deals (DB-first read source): "
                  f"{len(rows)} row(s) ===")
            for r in rows:
                rid = r["id"] if isinstance(r, dict) else r[0]
                print(f"  {r}")
                db_ids.add(str(rid))
        else:
            print("\n=== Postgres: NOT available -> reads fall back to JSON ===")
    except Exception as e:
        print(f"\n=== Postgres query FAILED: {e} ===")

    # 3) Divergence report.
    print("\n=== Divergence ===")
    only_json = sorted(json_ids - db_ids)
    only_db = sorted(db_ids - json_ids)
    print("  In JSON but NOT in DB  (invisible to the DB-first list/analytics):",
          only_json or "none")
    print("  In DB but NOT in JSON  (invisible to the validation queue):",
          only_db or "none")

    # 4) Cascade scope + draft check for the viewer.
    print(f"\n=== Scope + drafts for viewer '{viewer}' ===")
    try:
        from utils.core import UserManager
        from utils.api_pipeline_scope import get_visible_staff_codes
        um = UserManager()
        u = dict(um.users.get(viewer) or {})
        if not u:
            print(f"  user '{viewer}' not found in users.json")
        else:
            u.setdefault("username", viewer)
            codes = get_visible_staff_codes(u)
            print(f"  viewer staff_code={u.get('staff_code')} "
                  f"role={u.get('role')} "
                  f"can_view_all={u.get('can_view_all')} "
                  f"is_admin={u.get('is_admin')}")
            print(f"  visible staff codes: {len(codes)}")
            out_of_scope = [d.get("id") for d in json_deals
                            if str(d.get("staff_code")) not in codes]
            print(f"  JSON deals OUTSIDE this viewer's scope: "
                  f"{out_of_scope or 'none'}")
            drafts = [d.get("id") for d in json_deals if d.get("draft")]
            print(f"  JSON deals that are DRAFTS (hidden from analytics): "
                  f"{drafts or 'none'}")
    except Exception as e:
        print(f"  scope check failed: {e}")

    print("\n=== Read this as ===")
    print("  - 2nd deal in 'In JSON but NOT in DB'  -> DB sync failed; fix is JSON-first reads.")
    print("  - 2nd deal in 'OUTSIDE viewer's scope' -> owner/scope issue; check the deal's owner.")
    print("  - 2nd deal in 'DRAFTS'                 -> it was saved as a draft.")


if __name__ == "__main__":
    main()
