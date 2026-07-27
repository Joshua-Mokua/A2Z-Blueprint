#!/usr/bin/env python3
"""End-to-end test of bundle create: login, POST a bundled deal with deal_value=0 and two
lines (2M + 3M), and check deal_value came back as 5,000,000. No token copy-paste.
"""
import json, urllib.request, urllib.error

BASE = "http://localhost:8502"

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

st, b = req("POST", "/api/auth/login",
            body={"username": "KE1347", "password": "EcoStaff1347"})
print(f"login: {st}")
token = b.get("access_token")
if not token:
    print("no token:", b); raise SystemExit

payload = {
    "client_name": "Bundle Test Co",
    "product_type": "Bundled Loan Product",
    "deal_value": 0,                       # deliberately 0 — sum should override
    "stage": "Initiation",
    "client_type": "Individual",
    "bundle_lines": [
        {"product_type": "Personal Loan", "amount": 2000000},
        {"product_type": "Asset Finance", "amount": 3000000},
    ],
}
st, b = req("POST", "/api/pipeline/deals", token, payload)
print(f"\ncreate: HTTP {st}")
print(json.dumps(b, indent=2)[:1200])

# verdict
if st in (200, 201):
    deal = b.get("deal") or b
    dv = deal.get("deal_value")
    bl = deal.get("bundle_lines")
    print(f"\n=== VERDICT ===")
    print(f"   deal_value = {dv}  (expected 5000000)  -> {'PASS' if dv in (5000000, 5000000.0) else 'CHECK'}")
    print(f"   bundle_lines present: {bool(bl)} ({len(bl) if bl else 0} lines)")
    print(f"   product_type = {deal.get('product_type')!r}")
else:
    print("\n(create failed — the detail above tells us which field the payload is missing)")
