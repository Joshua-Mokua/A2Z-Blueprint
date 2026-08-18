"""Diagnostic (READ-ONLY): show how pending-validation scope changes if we move
from "entire downline" to "immediate direct reports only".

Why: today /api/pipeline/analytics computes pending_validation over
get_visible_staff_codes(user) = the user's WHOLE subtree, so the MD sees every
unvalidated active deal in the bank as "awaiting your sign-off". The intended
model is: a deal is validated ONCE by the owner's immediate line manager, then
counts as assured all the way up. That means a manager's pending queue should be
only the unvalidated active deals owned by their DIRECT reports.

This script prints, per persona, the direct-report count, the full-subtree count,
and the would-be pending count under each scope — so we can confirm the canonical
direct-report resolver returns sensible numbers against the LIVE data before we
change the validation gate. It writes NOTHING.

Run (in the project venv):
  python scripts\\diag_validation_scope.py
"""
from __future__ import annotations
import sys


def _build_user(roster, code):
    """Minimal user_data dict for a staff code, from the register."""
    import pandas as pd  # noqa: F401
    row = roster[roster["Staff Code"].astype(str).str.strip() == str(code)]
    if len(row) == 0:
        return None
    r = row.iloc[0]
    role = str(r.get("Role", "")).strip()
    return {
        "staff_code": str(code),
        "full_name": str(r.get("Staff Name", "")).strip(),
        "role": role,
        "unit": str(r.get("Unit", "")).strip(),
        "region": str(r.get("Region", "")).strip(),
        "is_admin": "managing director" in role.lower() or "chief executive" in role.lower(),
        "can_view_all": False,
    }


def main() -> None:
    try:
        from utils.core import PipelineManager, ACTIVE_STAGES
        from utils.manager_rollup import _direct_report_codes
        from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Could not import the app layer (run in the project venv): {e}")

    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        raise SystemExit("Staff roster empty — cannot diagnose.")

    pm = PipelineManager()
    deals = pm.get_deals()
    active = [d for d in deals if d.get("stage") in ACTIVE_STAGES]

    def owned_pending(codes):
        """Active + unvalidated deals owned by any of `codes`."""
        cs = set(str(c) for c in codes)
        return [d for d in active
                if str(d.get("staff_code", "")) in cs and not d.get("manager_validated")]

    # Pick personas: MD + auto-discover an Area Manager, a Branch Manager, and an RM.
    def first_code(role_substr):
        m = roster[roster["Role"].astype(str).str.contains(role_substr, case=False, na=False)]
        return str(m.iloc[0]["Staff Code"]).strip() if len(m) else None

    personas = []
    for label, code in [
        ("MD", "300001"),
        ("Area Manager", first_code("Area Manager")),
        ("Branch Manager", first_code("Branch Manager")),
        ("RM / RO", first_code("Relationship") or first_code("RO ") or "300731"),
    ]:
        if code:
            personas.append((label, code))

    print(f"Active deals: {len(active)} | "
          f"unvalidated active: {sum(1 for d in active if not d.get('manager_validated'))}\n")
    print(f"{'Persona':<16}{'Code':<9}{'Role':<34}{'#direct':>8}{'#subtree':>10}"
          f"{'pend(direct)':>14}{'pend(subtree)':>15}")
    print("-" * 106)

    for label, code in personas:
        user = _build_user(roster, code)
        if not user:
            print(f"{label:<16}{code:<9}{'(not in roster)':<34}")
            continue
        try:
            direct = set(_direct_report_codes(code))
        except Exception as e:  # noqa: BLE001
            direct = set()
            print(f"  warn: direct-report resolver failed for {code}: {e}")
        try:
            subtree = get_visible_staff_codes(user)
        except Exception as e:  # noqa: BLE001
            subtree = set()
            print(f"  warn: subtree resolver failed for {code}: {e}")

        pend_direct = owned_pending(direct)
        pend_subtree = owned_pending(subtree)
        role = (user["role"][:32] + "..") if len(user["role"]) > 33 else user["role"]
        print(f"{label:<16}{code:<9}{role:<34}{len(direct):>8}{len(subtree):>10}"
              f"{len(pend_direct):>14}{len(pend_subtree):>15}")

    print("\nInterpretation:")
    print("  pend(subtree) = today's 'Pending Validation' number (whole downline).")
    print("  pend(direct)  = the proposed number (only the manager's direct reports).")
    print("  For the MD, pend(direct) should be ~0 (chiefs rarely own deals);")
    print("  for a Branch Manager it should be their own team's unvalidated deals.")
    print("  If #direct is 0 for a manager who clearly has a team, the resolver")
    print("  needs the register-based path before we flip the gate.")


if __name__ == "__main__":
    sys.exit(main())
