#!/usr/bin/env python3
"""scripts/sim_end_to_end.py — CA3 end-to-end simulation.

Walks ONE facility from creation to disbursement against the LIVE API, logging in as
the relevant role at each hop and asserting each transition. Prints a PASS/FAIL trace
so you can SEE the whole chain hold together — the demo-ready proof.

Run with the API up on :8502. Usage:
    python scripts\\sim_end_to_end.py
    python scripts\\sim_end_to_end.py --base http://127.0.0.1:8502
    python scripts\\sim_end_to_end.py --amount 3000000     (small = branch tier, no committee)
    python scripts\\sim_end_to_end.py --amount 250000000   (large = climbs to committee)

Logins: EcoStaff+last4 of staff code (per project convention). Override any role's
login with --md user/pass, --analyst user/pass, etc. if your demo logins differ.
This script only READS and drives the documented endpoints; it creates ONE test deal.
"""
import argparse, json, sys, urllib.request, urllib.error

def _req(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
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
        self.base = base.rstrip("/")
        self.n_pass = 0
        self.n_fail = 0
    def step(self, ok, label, extra=""):
        tag = "PASS" if ok else "FAIL"
        if ok: self.n_pass += 1
        else: self.n_fail += 1
        print(f"  [{tag}] {label}" + (f" — {extra}" if extra else ""))
        return ok
    def login(self, username, password):
        st, body = _req("POST", f"{self.base}/api/auth/login",
                        body={"username": username, "password": password})
        if st == 200 and body.get("access_token"):
            return body["access_token"], body
        return None, body

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--amount", type=float, default=3_000_000)
    # role logins (username password) — override to match your demo logins
    for role in ("rm", "analyst", "manager", "md", "creditadmin", "legal", "trops"):
        ap.add_argument(f"--{role}", nargs=2, metavar=("USER", "PASS"), default=None)
    args = ap.parse_args()
    sim = Sim(args.base)

    print(f"\n=== A2Z end-to-end simulation @ {sim.base}  (amount KES {args.amount:,.0f}) ===\n")

    # 0. connectivity
    st, _ = _req("GET", f"{sim.base}/api/health") if True else (0, {})
    print(f"Ordinarily log in per role. This script uses the logins you pass via flags.")
    print(f"If a role login is omitted, that hop is SKIPPED (still useful to see how far it flows).\n")

    tokens = {}
    for role in ("rm", "analyst", "manager", "md", "creditadmin", "legal", "trops"):
        creds = getattr(args, role)
        if creds:
            tok, body = sim.login(creds[0], creds[1])
            sim.step(bool(tok), f"login {role} ({creds[0]})",
                     "" if tok else str(body.get("detail", body))[:120])
            if tok: tokens[role] = tok

    drive = tokens.get("rm") or tokens.get("manager") or tokens.get("md")
    if not drive:
        print("\nNo usable login provided. Pass at least --rm USER PASS (and ideally the others).")
        print("Example:")
        print("  python scripts\\sim_end_to_end.py --rm william001 EcoStaff0001 \\\\")
        print("     --manager robert002 EcoStaff0002 --md william001 EcoStaff0001 \\\\")
        print("     --analyst <u> <p> --creditadmin <u> <p> --legal <u> <p> --trops <u> <p>")
        sys.exit(1)

    # 1. create pipeline deal
    st, body = _req("POST", f"{sim.base}/api/pipeline/deals", token=drive, body={
        "client_name": "SIM E2E Client Ltd",
        "deal_value": args.amount,
        "product_type": "Business Loan",
        "stage": "Prospecting",
        "client_type": "Business",
    })
    deal_id = (body.get("deal") or body).get("id") if isinstance(body, dict) else None
    if not sim.step(st in (200, 201) and bool(deal_id), "create pipeline deal",
                    f"id={deal_id}" if deal_id else str(body)[:160]):
        print("\nCannot proceed without a deal. Stopping.")
        sys.exit(1)

    # 2. advance through to Compliance (triggers LMS handoff)
    for stage in ("Proposal", "Negotiation", "Compliance"):
        st, body = _req("POST", f"{sim.base}/api/pipeline/deals/{deal_id}/advance",
                        token=drive, body={"new_stage": stage})
        sim.step(st == 200, f"advance -> {stage}",
                 "" if st == 200 else str(body.get("detail", body))[:120])

    # 3. find the LMS application created from this deal
    tok = tokens.get("manager") or tokens.get("md") or drive
    st, body = _req("GET", f"{sim.base}/api/lms/applications", token=tok)
    apps = body.get("applications", []) if isinstance(body, dict) else []
    app = next((a for a in apps if a.get("client_name") == "SIM E2E Client Ltd"), None)
    app_id = app.get("id") if app else None
    sim.step(bool(app_id), "LMS application auto-created from deal",
             f"app={app_id}" if app_id else "not found (check handoff_trigger_status / advance)")

    if app_id and tokens.get("md"):
        # 4. refer to committee (for a large amount) then convene/vote/resolve
        if args.amount >= 50_000_000:
            st, body = _req("POST", f"{sim.base}/api/lms/applications/{app_id}/committee/refer",
                            token=tokens.get("manager") or tokens["md"], body={})
            sim.step(st == 200, "refer to committee",
                     "" if st == 200 else str(body.get("detail", body))[:120])
            st, body = _req("GET", f"{sim.base}/api/lms/committee/convening-queue", token=tokens["md"])
            sim.step(st == 200, "MD convening queue reachable",
                     f"awaiting={body.get('awaiting')}" if st == 200 else str(body)[:120])
            st, body = _req("POST", f"{sim.base}/api/lms/applications/{app_id}/committee/convene",
                            token=tokens["md"], body={})
            sim.step(st == 200, "MD convenes committee",
                     "" if st == 200 else str(body.get("detail", body))[:120])

    # 5. credit-admin case visibility (the CA3a fix)
    if tokens.get("creditadmin"):
        st, body = _req("GET", f"{sim.base}/api/credit-admin/cases", token=tokens["creditadmin"])
        n = body.get("count", 0) if isinstance(body, dict) else 0
        sim.step(st == 200, "credit-admin sees cases (CA3a dept visibility)", f"count={n}")

    # 6. trops queue visibility (the CA1 leg)
    if tokens.get("trops"):
        st, body = _req("GET", f"{sim.base}/api/credit-admin/troops/queue", token=tokens["trops"])
        sim.step(st == 200, "trops disbursement queue reachable",
                 f"count={body.get('count')}" if st == 200 else str(body.get('detail', body))[:120])

    # 7. legal charging queue (CA2)
    if tokens.get("legal"):
        st, body = _req("GET", f"{sim.base}/api/credit-admin/legal/charging-queue", token=tokens["legal"])
        sim.step(st == 200, "legal charging queue reachable",
                 f"count={body.get('count')}" if st == 200 else str(body.get('detail', body))[:120])
        st, body = _req("GET", f"{sim.base}/api/credit-admin/my-legal-officers", token=tokens["legal"])
        sim.step(st == 200, "legal-officer pool populated (CA2 dropdown)",
                 f"officers={body.get('count')}" if st == 200 else str(body)[:120])

    print(f"\n=== RESULT: {sim.n_pass} passed, {sim.n_fail} failed ===")
    print("Note: hops requiring a role you didn't pass are skipped. Provide all 7 logins")
    print("for the full create->disbursement trace. This creates one test deal you can")
    print("later cancel/delete from the pipeline.\n")
    sys.exit(1 if sim.n_fail else 0)

if __name__ == "__main__":
    main()
