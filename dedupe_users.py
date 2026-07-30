#!/usr/bin/env python3
"""One-off: collapse duplicate user records in Postgres (same person under
multiple usernames — mostly staff-code shadow rows left by merge_roster_json.py
plus case-variant duplicates created afterward).

Survivor rule per staff_code group:
  1. Drop any record whose username == its own staff_code (the shadow-insert
     pattern), if at least one other record remains in the group.
  2. Among what's left, prefer a username containing '@' (real AD login).
  3. Tie-break: most non-empty profile fields, then alphabetically first.
Merges department/unit/metadata gaps and OR's is_admin/can_view_all from
losers into the survivor before deleting the losers — never silently drops
an admin grant.

    python dedupe_users.py            # dry run
    python dedupe_users.py --apply
"""
import sys
from utils.core import UserManager

apply = "--apply" in sys.argv[1:]
um = UserManager()

by_code = {}
for uname, rec in um.users.items():
    code = str(rec.get("staff_code") or "").strip().upper()
    if code:
        by_code.setdefault(code, []).append(uname)

def completeness(uname):
    rec = um.users[uname]
    return sum(1 for k in ("email", "department", "unit", "full_name") if rec.get(k))

_REAL_DOMAINS = ("@ecobank.com", "@ecobank.co.ke", "@ecobank.group")

def is_real_domain(uname):
    # Check the USERNAME's own domain first — that's what actually gets
    # typed at login. "cadewunmi@eco.com" vs "cadewunmi@ecobank.com" (same
    # person, same `email` field) must prefer the ecobank.com one, which a
    # check against the `email` field alone can't distinguish.
    u = uname.lower()
    if "@" in u:
        return any(d in u for d in _REAL_DOMAINS)
    email = str(um.users[uname].get("email") or "").lower()
    return any(d in email for d in _REAL_DOMAINS)

def pick_survivor(unames, shadow_key=None):
    candidates = ([u for u in unames if u.strip().upper() != shadow_key] if shadow_key else list(unames)) \
        or list(unames)
    if len(candidates) == 1:
        return candidates[0]
    pool = [u for u in candidates if is_real_domain(u)] or candidates
    pool = [u for u in pool if "@" in u] or pool
    pool.sort(key=lambda u: (-completeness(u), u.lower()))
    return pool[0]

merges = []
handled = set()
for code, unames in by_code.items():
    if len(unames) < 2:
        continue
    survivor = pick_survivor(unames, shadow_key=code)
    losers = [u for u in unames if u != survivor]
    merges.append((f"staff_code={code}", survivor, losers))
    handled.update(unames)

# Second pass: same full_name, not already resolved by staff_code (mostly
# empty-staff_code duplicates the first pass can't see).
by_name = {}
for uname, rec in um.users.items():
    if uname in handled:
        continue
    name = str(rec.get("full_name") or "").strip()
    if name:
        by_name.setdefault(name, []).append(uname)

for name, unames in by_name.items():
    if len(unames) < 2:
        continue
    survivor = pick_survivor(unames)
    losers = [u for u in unames if u != survivor]
    merges.append((f"full_name={name!r}", survivor, losers))
    handled.update(unames)

print(f"{len(merges)} duplicate staff_code groups\n")
for code, survivor, losers in merges:
    print(f"  {code}: keep {survivor!r}  delete {losers!r}")

if not apply:
    print("\n[DRY-RUN] re-run with --apply")
    sys.exit(0)

for code, survivor, losers in merges:
    srec = um.users[survivor]
    for loser in losers:
        lrec = um.users.get(loser, {})
        for field in ("department", "unit", "email"):
            if not srec.get(field) and lrec.get(field):
                srec[field] = lrec[field]
        for flag in ("is_admin", "can_view_all"):
            if lrec.get(flag):
                srec[flag] = True
        for mkey in ("band", "gender", "region", "reports_to", "dotted", "date_of_employment"):
            if not srec.get(mkey) and lrec.get(mkey):
                srec[mkey] = lrec[mkey]

for code, survivor, losers in merges:
    for loser in losers:
        ok, msg = um.delete_user(loser, verified_by="dedupe_users_script")
        print(f"  deleted {loser!r}: {ok} {msg}")

um.save_users()
print(f"\ndone. {sum(len(l) for _,_,l in merges)} duplicate accounts removed.")
