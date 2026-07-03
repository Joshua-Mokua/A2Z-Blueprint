#!/usr/bin/env python3
"""scripts/sim_end_to_end.py — CA3 end-to-end simulation (v2, real flow).

Walks ONE facility toward disbursement against the LIVE API, following the REAL,
document-gated flow (v10.574: LMS handoff is an explicit POST /submit-to-credit, not a
side-effect of advancing to Compliance). Logs in per role, drives each real gate it
can, and reports the checklist state at each gate so you SEE exactly what a real case
needs. Creates ONE test deal ("SIM E2E Client Ltd").

Run with the API up on :8502. Roles (pass the ones you have; omit to skip a hop):
  --rm USER PASS         deal owner (e.g. frank...)  — REQUIRED to create/drive
  --manager USER PASS    validates the deal + can refer to committee
  --md USER PASS         CEO/MD — convening queue
  --analyst USER PASS    credit analyst
  --creditadmin USER PASS
  --legal USER PASS
  --trops USER PASS

Example (smoke test — RM + manager + MD):
  python scripts\\sim_end_to_end.py --rm frank004 EcoStaff0004 ^
     --manager robert002 EcoStaff0002 --md william001 EcoStaff0001
"""
import argparse, json, sys, urllib.request, urllib.error

def _req(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return e.code, json.loads(raw)
        except Exception: return e.code, {"detail": raw[:300]}
    except Exception as e:
        return 0, {"detail": str(e)}

class Sim:
    def __init__(self, base):
        self.base = base.rstrip("/"); self.n_pass = self.n_fail = self.n_info = 0
    def ok(self, cond, label, extra=""):
        if cond: self.n_pass += 1; tag = "PASS"
        else: self.n_fail += 1; tag = "FAIL"
        print(f"  [{tag}] {label}" + (f" — {extra}" if extra else "")); return cond
    def info(self, label, extra=""):
        self.n_info += 1; print(f"  [INFO] {label}" + (f" — {extra}" if extra else ""))
    def login(self, u, p):
        st, b = _req("POST", f"{self.base}/api/auth/login", body={"username": u, "password": p})
        return (b.get("access_token"), b) if st == 200 else (None, b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--amount", type=float, default=3_000_000)
    for r in ("rm","analyst","manager","md","creditadmin","legal","trops"):
        ap.add_argument(f"--{r}", nargs=2, metavar=("USER","PASS"), default=None)
    a = ap.parse_args()
    sim = Sim(a.base)
    print(f"\n=== A2Z end-to-end simulation @ {sim.base}  (amount KES {a.amount:,.0f}) ===\n")

    tok = {}
    for r in ("rm","analyst","manager","md","creditadmin","legal","trops"):
        creds = getattr(a, r)
        if creds:
            t, b = sim.login(*creds)
            sim.ok(bool(t), f"login {r} ({creds[0]})", "" if t else str(b.get("detail", b))[:120])
            if t: tok[r] = t

    rm = tok.get("rm")
    if not rm:
        print("\nPass at least --rm USER PASS (the deal owner). Stopping."); sys.exit(1)

    # 1. create deal
    st, b = _req("POST", f"{sim.base}/api/pipeline/deals", token=rm, body={
        "client_name": "SIM E2E Client Ltd", "deal_value": a.amount,
        "product_type": "Business Loan", "stage": "Lead", "client_type": "Business"})
    deal = (b.get("deal") or b) if isinstance(b, dict) else {}
    deal_id = deal.get("id")
    if not sim.ok(st in (200,201) and bool(deal_id), "create pipeline deal",
                  f"id={deal_id}" if deal_id else str(b)[:160]):
        sys.exit(1)

    # 2. read the credit checklist to discover the REAL required stage + docs
    st, chk = _req("GET", f"{sim.base}/api/pipeline/deals/{deal_id}/credit-checklist", token=rm)
    if st == 200:
        sim.info("credit-checklist read",
                 f"stage_required={chk.get('stage_required') or '(none)'} required_docs={chk.get('required')} cr_required={chk.get('cr_required')}")
    else:
        sim.ok(False, "credit-checklist read", str(chk)[:120])

    # 3. advance to the required stage (discover the real ladder by trying, in order)
    ladder = ["Contacted","Qualified","Application","Credit Assessment","Proposal","Negotiation"]
    target = (chk.get("stage_required") or "").strip() if st == 200 else ""
    reached = False
    for stg in ladder:
        st2, b2 = _req("POST", f"{sim.base}/api/pipeline/deals/{deal_id}/advance",
                       token=rm, body={"new_stage": stg})
        if st2 == 200:
            sim.info(f"advance -> {stg}")
            if target and stg == target: reached = True; break
        # if this stage isn't valid for the ladder, just skip it silently
    if target:
        sim.ok(reached or (chk.get("current_stage") == target),
               f"reached submit stage '{target}'", "" if reached else "may need a different ladder")
    else:
        sim.info("no product stage gate — submission allowed from any stage")

    # 4. re-read checklist; report each gate honestly
    st, chk = _req("GET", f"{sim.base}/api/pipeline/deals/{deal_id}/credit-checklist", token=rm)
    if st == 200:
        sim.info("gates", f"stage_ok={chk.get('stage_ok')} cr_ok={chk.get('cr_ok')} "
                          f"missing_docs={chk.get('missing')} can_submit={chk.get('can_submit')}")

    # 5. provide any missing docs (the required list) + complete CR (best-effort)
    required = chk.get("required", []) if st == 200 else []
    if required:
        st5, b5 = _req("POST", f"{sim.base}/api/pipeline/deals/{deal_id}/submit-to-credit",
                       token=rm, body={"documents_provided": required})
        # this call also attempts submit; capture its gate message
        if st5 == 200:
            sim.ok(True, "submit-to-credit (docs provided inline)")
        else:
            sim.info("submit-to-credit gate", str(b5.get("detail", b5))[:160])

    # 6. manager validates the deal (needed before submit)
    if tok.get("manager"):
        stv, bv = _req("POST", f"{sim.base}/api/pipeline/deals/{deal_id}/validate",
                       token=tok["manager"], body={"approved": True})
        sim.ok(stv == 200, "manager validates deal", "" if stv == 200 else str(bv.get("detail", bv))[:120])
        # retry submit after validation
        st6, b6 = _req("POST", f"{sim.base}/api/pipeline/deals/{deal_id}/submit-to-credit",
                       token=rm, body={"documents_provided": required})
        sim.ok(st6 == 200, "submit-to-credit -> creates LMS application",
               "" if st6 == 200 else str(b6.get("detail", b6))[:160])

    # 7. find the LMS application
    lms_tok = tok.get("manager") or tok.get("md") or rm
    st, b = _req("GET", f"{sim.base}/api/lms/applications", token=lms_tok)
    apps = b.get("applications", []) if isinstance(b, dict) else []
    app = next((x for x in apps if x.get("client_name") == "SIM E2E Client Ltd"), None)
    app_id = app.get("id") if app else None
    sim.ok(bool(app_id), "LMS application present", f"app={app_id}" if app_id else "not created (see submit gate above)")

    # 8. committee path for a large amount
    if app_id and a.amount >= 50_000_000 and tok.get("md"):
        st, b = _req("POST", f"{sim.base}/api/lms/applications/{app_id}/committee/refer",
                     token=tok.get("manager") or tok["md"], body={})
        sim.ok(st == 200, "refer to committee", "" if st == 200 else str(b.get("detail", b))[:120])
        st, b = _req("GET", f"{sim.base}/api/lms/committee/convening-queue", token=tok["md"])
        sim.ok(st == 200, "MD convening queue reachable", f"awaiting={b.get('awaiting')}" if st == 200 else str(b)[:120])

    # 9. department visibility hops (the CA fixes)
    if tok.get("creditadmin"):
        st, b = _req("GET", f"{sim.base}/api/credit-admin/cases", token=tok["creditadmin"])
        sim.ok(st == 200, "credit-admin sees cases (CA3a)", f"count={b.get('count')}" if st == 200 else str(b.get('detail', b))[:120])
    if tok.get("legal"):
        st, b = _req("GET", f"{sim.base}/api/credit-admin/my-legal-officers", token=tok["legal"])
        sim.ok(st == 200, "legal-officer pool (CA2)", f"officers={b.get('count')}" if st == 200 else str(b.get('detail', b))[:120])
        st, b = _req("GET", f"{sim.base}/api/credit-admin/legal/charging-queue", token=tok["legal"])
        sim.ok(st == 200, "legal charging queue (CA2)", f"count={b.get('count')}" if st == 200 else str(b.get('detail', b))[:120])
    if tok.get("trops"):
        st, b = _req("GET", f"{sim.base}/api/credit-admin/troops/queue", token=tok["trops"])
        sim.ok(st == 200, "trops disbursement queue (CA1)", f"count={b.get('count')}" if st == 200 else str(b.get('detail', b))[:120])

    print(f"\n=== RESULT: {sim.n_pass} passed, {sim.n_fail} failed, {sim.n_info} info ===")
    print("INFO lines are gate states (docs/CR/stage), not failures — they show what a real")
    print("case needs. Cancel the 'SIM E2E Client Ltd' deal from the pipeline when done.\n")
    sys.exit(1 if sim.n_fail else 0)

if __name__ == "__main__":
    main()
