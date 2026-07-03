#!/usr/bin/env python3
"""scripts/apply_legal_charging_backend.py — CA2: submit-to-legal-for-charging.

Credit Admin explicitly submits a case to Legal FOR CHARGING; it lands in the Legal
Chief's queue; the Legal Chief assigns an officer from a dropdown of THEIR legal
officers (mirrors my-analysts). Extends the existing legal_review (assign/comment/
outcome stay as-is).

- core.CreditAdminManager.submit_to_legal(case_id, by, note): status ->
  'submitted_for_charging' + stamps submitted_for_charging_at/by.
- POST /credit-admin/cases/{id}/legal/submit-for-charging
- GET  /credit-admin/legal/charging-queue   (Legal Chief / legal-role / manager)
- GET  /api/credit-admin/my-legal-officers  (legal-role staff, mirrors my-analysts)

SAFE: .pre_legalchg backups (core.py + api_credit_admin_routes.py + api.py). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "utils" / "core.py"
ROUTES = ROOT / "utils" / "api_credit_admin_routes.py"
API = ROOT / "utils" / "api.py"
CORE_BAK = CORE.with_suffix(".py.pre_legalchg")
ROUTES_BAK = ROUTES.with_suffix(".py.pre_legalchg")
API_BAK = API.with_suffix(".py.pre_legalchg")

# --- core: submit_to_legal method, inserted right before assign_legal_officer ---
def patch_core(s):
    if "def submit_to_legal" in s:
        return s, False
    anchor = "    def assign_legal_officer(self, case_id: str, officer_code: str,"
    method = '''    def submit_to_legal(self, case_id: str, by: str = "", note: str = "") -> bool:
        """CA2: Credit Admin submits the case to Legal FOR CHARGING. Sets the
        legal_review status to 'submitted_for_charging' so it appears in the Legal
        Chief's charging queue for officer assignment. Idempotent-ish: re-submitting
        just refreshes the stamp."""
        from datetime import datetime as _dt
        for case in self.cases:
            if case["id"] == case_id:
                lr = self._ensure_legal_review(case)
                lr["status"] = "submitted_for_charging"
                lr["submitted_for_charging_by"] = by
                lr["submitted_for_charging_at"] = _dt.now().isoformat(timespec="seconds")
                if note:
                    lr.setdefault("charging_notes", []).append(
                        {"by": by, "note": note, "at": lr["submitted_for_charging_at"]})
                self.save()
                return True
        return False

'''
    return s.replace(anchor, method + anchor, 1), True

# --- routes: submit-for-charging + charging-queue endpoints ---
def patch_routes(s):
    if "submit-for-charging" in s:
        return s, False
    marker = "# === CA2: LEGAL CHARGING ==="
    block = '''

# === CA2: LEGAL CHARGING ===
class _SubmitForChargingRequest(BaseModel):
    note: Optional[str] = ""
    model_config = ConfigDict(extra="allow")


@router.post("/cases/{case_id}/legal/submit-for-charging",
             response_model=CreditAdminMutationResponse)
def credit_admin_submit_for_charging(case_id: str, payload: _SubmitForChargingRequest,
                                     user: Dict[str, Any] = Depends(get_current_user)):
    """Credit Admin submits the case to Legal for charging — it enters the Legal
    Chief's charging queue. Credit-admin scope (same gate as other CA actions)."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not (user.get("is_admin") or _ca_manager_in_scope(user, case) or is_manager(user)):
        raise HTTPException(status_code=403, detail="Case not in your scope")
    ok = cam.submit_to_legal(case_id, by=str(user.get('username', '') or ''),
                             note=payload.note or "")
    if not ok:
        raise HTTPException(status_code=500, detail="submit-for-charging failed")
    audit_log("CREDIT_ADMIN_LEGAL_SUBMITTED_FOR_CHARGING",
              str(user.get('username', '') or ''), case_id)
    return {"case": cam.get(case_id), "status": "submitted_for_charging"}


@router.get("/legal/charging-queue")
def credit_admin_legal_charging_queue(user: Dict[str, Any] = Depends(get_current_user)):
    """Cases submitted to Legal for charging — the Legal Chief's queue. Visible to
    admin / legal-role / manager-tier users."""
    if not _can_perform_legal(user):
        raise HTTPException(status_code=403,
                            detail="Legal Officer or manager authority required")
    cam = _cam()
    out = []
    for c in cam.cases:
        lr = c.get("legal_review") or {}
        if str(lr.get("status", "") or "") != "submitted_for_charging":
            continue
        out.append({
            "case_id": c.get("id"),
            "client_name": c.get("client_name") or c.get("borrower_name"),
            "amount": c.get("amount") or c.get("facility_amount") or c.get("loan_amount"),
            "submitted_at": lr.get("submitted_for_charging_at"),
            "submitted_by": lr.get("submitted_for_charging_by"),
            "assigned_officer_code": lr.get("assigned_officer_code"),
            "assigned_officer_name": lr.get("assigned_officer_name"),
        })
    out.sort(key=lambda x: str(x.get("submitted_at") or ""))
    return {"cases": out, "count": len(out)}
# === END CA2 ===
'''
    return s.rstrip() + "\n" + block + "\n", True

# --- api.py: my-legal-officers (mirror my-analysts) ---
def patch_api(s):
    if "my-legal-officers" in s:
        return s, False
    marker = "# === END MY ANALYSTS DROPDOWN ==="
    block = '''

# === MY LEGAL OFFICERS DROPDOWN (CA2) ===
def _is_legal_role(role: str) -> bool:
    """A legal-officer role (for the charging-assignment dropdown)."""
    r = str(role or "").lower()
    return "legal" in r


@app.get("/api/credit-admin/my-legal-officers", tags=["credit-admin"])
def get_my_legal_officers(user: dict = Depends(get_current_user)):
    """Assignable legal officers for the Legal Chief's charging-assignment dropdown.
    Legal chiefs / managers see the full legal pool; others fall back to their scope.
    Mirrors my-analysts."""
    from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster
    roster = get_staff_roster()
    role_l = str(user.get("role", "") or "").lower()
    full = bool(user.get("is_admin")) or ("legal" in role_l and (
        "chief" in role_l or "head" in role_l or "manager" in role_l)) or is_manager(user)
    visible = set() if full else get_visible_staff_codes(user)
    officers = []
    try:
        for _, row in roster.iterrows():
            code = str(row.get("Staff Code", "") or "").strip()
            role = str(row.get("Role", "") or "")
            if not code:
                continue
            if not full and code not in visible:
                continue
            if _is_legal_role(role):
                officers.append({
                    "staff_code": code,
                    "name": str(row.get("Staff Name", "") or ""),
                    "role": role,
                    "unit": str(row.get("Unit", "") or ""),
                })
    except Exception as exc:
        logger.warning("my-legal-officers: roster scan failed: %s", exc)
    officers.sort(key=lambda a: a["name"])
    return {"officers": officers, "count": len(officers)}
# === END MY LEGAL OFFICERS DROPDOWN ===
'''
    return s.replace(marker, marker + block, 1), True

def revert():
    for bak, tgt in ((CORE_BAK, CORE), (ROUTES_BAK, ROUTES), (API_BAK, API)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    c = CORE.read_text(encoding="utf-8")
    r = ROUTES.read_text(encoding="utf-8")
    a = API.read_text(encoding="utf-8")
    c_new, c_ch = patch_core(c)
    r_new, r_ch = patch_routes(r)
    a_new, a_ch = patch_api(a)
    print(f"  core.py (submit_to_legal): {'change' if c_ch else 'skip'}")
    print(f"  api_credit_admin_routes.py (submit+queue): {'change' if r_ch else 'skip'}")
    print(f"  api.py (my-legal-officers): {'change' if a_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if c_ch:
        if not CORE_BAK.exists(): CORE_BAK.write_text(c, encoding="utf-8")
        CORE.write_text(c_new, encoding="utf-8")
    if r_ch:
        if not ROUTES_BAK.exists(): ROUTES_BAK.write_text(r, encoding="utf-8")
        ROUTES.write_text(r_new, encoding="utf-8")
    if a_ch:
        if not API_BAK.exists(): API_BAK.write_text(a, encoding="utf-8")
        API.write_text(a_new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
