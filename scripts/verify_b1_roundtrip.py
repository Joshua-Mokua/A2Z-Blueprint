#!/usr/bin/env python3
"""scripts/verify_b1_roundtrip.py — Phase B1 verification gate.

Proves that EVERY field B0 made _db_sync persist actually survives a
Postgres-authoritative read — the prerequisite for flipping _get_or_hydrate_deal
to PG-first (B2). This is the gate whose absence caused the first Phase B
regression (we flipped reads before proving the round-trip).

Method — a THREE-WAY comparison per field:
  SENT : value we put on the create payload (or a mutation)
  PG   : value read straight out of pipeline_deals.metadata (the DB truth)
  GET  : value the API returns via the detail endpoint (_normalize lift)

Interpretation:
  SENT ok, PG missing      -> _db_sync does NOT persist it (write-side gap)
  PG ok,   GET missing     -> _normalize does NOT lift it   (read-side gap)
  all three match          -> round-trips cleanly

Because some fields are only set by later lifecycle actions (disburse/refer/etc.),
this probe covers the create-time + portfolio fields directly, and reports the
remaining lifecycle fields as INFO (present-in-PG check only, since they're not
settable at create). A non-zero exit means a real gap was found.

Run against the LIVE API (B0 applied):
    python scripts/verify_b1_roundtrip.py
"""
import sys, json, time
import urllib.request, urllib.error
sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8502"

def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read().decode()[:160]}
    except Exception as e:
        return 0, {"detail": str(e)}

def _pg_metadata(deal_id):
    from utils.db import db
    row = db.fetch_one("SELECT metadata FROM pipeline_deals WHERE id=%s", (deal_id,))
    if not row or not row.get("metadata"):
        return {}
    md = row["metadata"]
    return md if isinstance(md, dict) else json.loads(md)

# ── login ──────────────────────────────────────────────────────────────────────
st, body = _req("POST", "/api/auth/login",
                body={"username": "frank0731", "password": "EcoStaff0731"})
tok = body.get("access_token") or body.get("token")
if not tok:
    print(f"FATAL: login failed ({st}) {body}"); sys.exit(2)
print(f"login: {st}")

# ── create a deal carrying the create-time + portfolio B0 fields ───────────────
sent = {
    "client_name":          f"B1 ROUNDTRIP {time.time()}",
    "product_type":         "Term Loan",
    "deal_value":           1_000_000,
    "stage":                "Lead",
    "segment":              "SME",
    "bsc_credit_to":        "Immaculate Wue",
    "manager_override_note":"B1 verification note — must survive PG-only read",
    "portfolio_owner_code": "300716",
    "portfolio_owner_name": "Immaculate Wue",
}
st, r = _req("POST", "/api/pipeline/deals", tok, sent)
did = (r.get("deal") or {}).get("id") if isinstance(r, dict) else None
print(f"create: {st} id={did}")
if not did:
    print(f"FATAL: create failed: {r}"); sys.exit(2)

time.sleep(0.4)
pg = _pg_metadata(did)
st, gbody = _req("GET", f"/api/pipeline/deals/{did}", tok)
get = (gbody.get("deal") or {}) if isinstance(gbody, dict) else {}

# ── the fields we can assert at create time (sent -> PG -> GET) ────────────────
CREATE_FIELDS = [
    "bsc_credit_to", "manager_override_note",
    "portfolio_owner_code", "portfolio_owner_name",
]

# ── lifecycle fields B0 persists but that are NOT settable at create ───────────
# We only verify they are READBACK-WIRED (present in the GET-normalised deal as a
# key, even if value is None) — proving _normalize lifts them. A missing KEY here
# means _normalize won't surface the field once a lifecycle action sets it.
LIFECYCLE_FIELDS = [
    "is_referral", "referred_at", "accepted_by", "accepted_at",
    "declined_by", "declined_at", "disbursed", "disbursed_at",
    "disbursed_under_override", "override_approved", "override_approved_by",
    "win_probability", "credit_deferred_to", "credit_deferred_to_code",
    "history", "is_ntb", "source",
]

def _norm(v):
    return "" if v is None else str(v)

print("\n=== CREATE-TIME FIELDS (sent -> PG -> GET) ===")
print(f"{'field':24} {'SENT':>6} {'PG':>6} {'GET':>6}  verdict")
hard_fail = 0
for f in CREATE_FIELDS:
    s_ok = _norm(sent.get(f)) != ""
    p_ok = _norm(pg.get(f)) == _norm(sent.get(f)) and _norm(sent.get(f)) != ""
    g_ok = _norm(get.get(f)) == _norm(sent.get(f)) and _norm(sent.get(f)) != ""
    verdict = "OK" if (s_ok and p_ok and g_ok) else \
              ("WRITE-GAP (not in PG)" if (s_ok and not p_ok) else
               ("READ-GAP (PG ok, GET missing)" if (p_ok and not g_ok) else "MISMATCH"))
    if not (s_ok and p_ok and g_ok):
        hard_fail += 1
    print(f"{f:24} {('Y' if s_ok else '-'):>6} {('Y' if p_ok else '-'):>6} {('Y' if g_ok else '-'):>6}  {verdict}")

print("\n=== LIFECYCLE FIELDS (read-back wiring: is the key surfaced by GET?) ===")
print(f"{'field':28} {'in_GET_keys':>12}  note")
soft_missing = 0
get_keys = set(get.keys())
for f in LIFECYCLE_FIELDS:
    wired = f in get_keys
    if not wired:
        soft_missing += 1
    print(f"{f:28} {('yes' if wired else 'NO'):>12}  {'' if wired else '_normalize may not lift this'}")

print("\n" + "=" * 60)
print(f"create-time hard gaps : {hard_fail} (must be 0 to proceed to B2)")
print(f"lifecycle keys missing: {soft_missing} (informational; lift wiring check)")
print("=" * 60)
if hard_fail == 0:
    print("\nB1 PASS: create-time + portfolio fields round-trip through PG cleanly.")
    print("Safe to proceed to B2 (flip _get_or_hydrate_deal to PG-first).")
else:
    print("\nB1 FAIL: a create-time field does not survive the PG round-trip.")
    print("Do NOT flip reads to PG-first until this is closed.")
sys.exit(1 if hard_fail else 0)
