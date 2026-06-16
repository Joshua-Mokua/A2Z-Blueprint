"""One-shot diagnostic: where does the loan book live, and can we scope it?

Run in the project venv with the DB up:
    python scripts\\diag_credit.py
Prints table counts/columns + whether rm_code is present + MD visible-code
overlap with the credit rm_codes. Read-only. Paste the output back.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from utils.db import db
    except Exception as e:
        print("DB import failed:", e); return

    def count(t):
        try:
            r = db.fetch_one(f"SELECT COUNT(*) AS n FROM {t}", ())
            return dict(r).get("n")
        except Exception as e:
            return f"ERR {e}"

    def sample_cols(t):
        try:
            r = db.fetch_one(f"SELECT * FROM {t} LIMIT 1", ())
            return sorted(dict(r).keys()) if r else "(empty table)"
        except Exception as e:
            return f"ERR {e}"

    for t in ("credit_watchlist", "watchlist"):
        print(f"\n[{t}] count = {count(t)}")
        print(f"  columns = {sample_cols(t)}")
        try:
            r = db.fetch_one(f"SELECT * FROM {t} LIMIT 1", ())
            d = dict(r) if r else {}
            print(f"  has rm_code={'rm_code' in d}  region={'region' in d}  "
                  f"risk_data={'risk_data' in d}  branch_name={'branch_name' in d}")
        except Exception as e:
            print("  sample ERR", e)

    # credit_monitoring.json on disk
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "credit_monitoring.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("watchlist", [])
        print(f"\n[credit_monitoring.json] items = {len(items)}")
    except Exception as e:
        print(f"\n[credit_monitoring.json] ERR {e}")

    # MD scope vs credit rm_codes
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        md = {"staff_code": "300001", "username": "william001",
              "role": "Chief Executive & Managing Director", "can_view_all": True}
        vc = get_visible_staff_codes(md)
        print(f"\nMD visible_codes = {len(vc)} (sample {list(vc)[:5]})")
        # credit rm_codes from whichever source has them
        rmset = set()
        for t in ("credit_watchlist", "watchlist"):
            try:
                rows = db.fetch_all(f"SELECT rm_code FROM {t} LIMIT 5000", ())
                rmset = set(str(dict(r).get("rm_code") or "") for r in (rows or []))
                if rmset:
                    print(f"  rm_codes from {t}: {len(rmset)} distinct")
                    break
            except Exception:
                continue
        if rmset:
            print(f"  overlap MD∩credit_rm = {len(rmset & set(map(str, vc)))} / {len(rmset)}")
    except Exception as e:
        print("scope check ERR", e)


if __name__ == "__main__":
    main()
