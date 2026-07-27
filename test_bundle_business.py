#!/usr/bin/env python3
"""Bundle create test as a BUSINESS deal (the realistic bundle case per Josh — Consumer
requires an MOU, Business needs a sector). Confirms deal_value = sum(lines)."""
import json, urllib.request, urllib.error

BASE = "http://localhost:8502"
def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE+path, data=data, method=method)
    r.add_header("Content-Type","application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

st,b = req("POST","/api/auth/login",body={"username":"KE1347","password":"EcoStaff1347"})
token = b.get("access_token"); print(f"login: {st}")

# discover a valid business sector from settings
import json as _j
from pathlib import Path
cfg = _j.loads(Path("data/pipeline_settings.json").read_text(encoding="utf-8"))
sectors = cfg.get("business_sectors") or []
sector = (sectors[0] if isinstance(sectors, list) and sectors
          else (list(sectors.keys())[0] if isinstance(sectors, dict) and sectors else "Trade"))
print(f"using business sector: {sector!r}")

payload = {
    "client_name": "Bundle Test Ltd",
    "product_type": "Bundled Loan Product",
    "deal_value": 0,
    "stage": "Initiation",
    "client_type": "Business",
    "sector": sector,
    "segment": "SME",
    "bundle_lines": [
        {"product_type": "Business Loan", "amount": 4000000},
        {"product_type": "Asset Finance", "amount": 3500000},
    ],
}
st,b = req("POST","/api/pipeline/deals", token, payload)
print(f"\ncreate: HTTP {st}")
print(json.dumps(b, indent=2)[:1200])

if st in (200,201):
    deal = b.get("deal") or b
    dv = deal.get("deal_value"); bl = deal.get("bundle_lines")
    print(f"\n=== VERDICT ===")
    print(f"   deal_value = {dv}  (expected 7500000)  -> {'PASS' if dv in (7500000,7500000.0) else 'CHECK'}")
    print(f"   bundle_lines present: {bool(bl)} ({len(bl) if bl else 0} lines)")
    print(f"   product_type = {deal.get('product_type')!r}")
    print(f"   deal id = {deal.get('id')}")
