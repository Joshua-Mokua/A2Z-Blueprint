#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A step-by-step committee walkthrough for one branch, with real logins.

Two pilots were called at Eldoret and neither reached a recommendation. This
prints exactly who can sign in there, who sits on the committee, what each
person should see at each step, and what to do if they do not - so the same
walk can be done here before it is done in front of the bank again.

    python scripts\\walkthrough_branch.py --branch Eldoret
    python scripts\\walkthrough_branch.py --branch Eldoret --seed     # create a case
    python scripts\\walkthrough_branch.py --branch Eldoret --clean    # remove it

READ ONLY unless --seed or --clean. Passwords follow the pilot convention -
EcoStaff plus the last four of the staff code - and are shown so a walkthrough
can be done without hunting for them. This is a pilot convention, not a
credential store: it does not read or print any real password hash.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def pwd_for(code):
    """The pilot's convention: EcoStaff + the last four of the staff code."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return "EcoStaff%s" % (digits[-4:].zfill(4) if digits else "0000")


def main():
    branch = ""
    if "--branch" in sys.argv:
        i = sys.argv.index("--branch")
        if i + 1 < len(sys.argv):
            branch = sys.argv[i + 1].strip()
    if not branch:
        print("ABORT: --branch <name> is required, e.g. --branch Eldoret")
        return 1
    seed = "--seed" in sys.argv
    clean = "--clean" in sys.argv

    import utils.api as A
    from utils.core import UserManager, PipelineManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    cttee = next((c for c in pal
                  if str(c.get("branch", "")).strip().lower() == branch.lower()), None)

    users = UserManager().users or {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        staff = [{"code": str(r.get("Staff Code") or "").strip(),
                  "name": str(r.get("Staff Name") or "").strip(),
                  "role": str(r.get("Role") or "").strip(),
                  "unit": str(r.get("Unit") or "").strip()}
                 for _i, r in df.iterrows()]
    except Exception as exc:
        print("ABORT: staff register unreadable: %s" % exc)
        return 1

    here = [p for p in staff if p["unit"].strip().lower() == branch.lower()]
    if not here:
        print("ABORT: nobody in the register is at %r." % branch)
        units = sorted({p["unit"] for p in staff if p["unit"]})
        print("       Branches in the register: %s" % ", ".join(units[:12]))
        return 1

    login_by_code = {}
    for k, v in users.items():
        c = str(v.get("staff_code", "") or "").strip()
        if c:
            login_by_code[c] = k

    bar = "=" * 78
    print(bar)
    print("%s BRANCH - WHO CAN SIGN IN" % branch.upper())
    print(bar)
    print("  %-10s %-28s %-28s %s" % ("CODE", "NAME", "ROLE", "LOGIN / PASSWORD"))
    no_login = []
    for p in sorted(here, key=lambda x: x["role"]):
        lg = login_by_code.get(p["code"])
        if lg:
            cred = "%s / %s" % (lg, pwd_for(p["code"]))
        else:
            cred = "NO LOGIN"
            no_login.append(p)
        print("  %-10s %-28s %-28s %s"
              % (p["code"], p["name"][:28], p["role"][:28], cred))

    if no_login:
        print("\n  *** %d person(s) here have NO LOGIN. They cannot take part:"
              % len(no_login))
        for p in no_login[:8]:
            print("      %-10s %s" % (p["code"], p["name"]))
        print("      Create them with: python scripts\\make_demo_logins.py --apply")

    print("\n" + bar)
    print("THE COMMITTEE")
    print(bar)
    if not cttee:
        print("  *** THERE IS NO COMMITTEE FOR %s." % branch.upper())
        print("      A case here routes to nobody and appears in no queue.")
        return 1
    chair = str(cttee.get("chaired_by", "") or "").strip()
    members = [m for m in (cttee.get("members") or [])
               if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]
    quorum = cttee.get("min_quorum_count") or 2
    print("  code    %s" % cttee.get("code"))
    print("  name    %s" % cttee.get("name"))
    print("  chair   %s" % (chair or "*** NOBODY ***"))
    print("  quorum  %d" % quorum)
    print("  members %d" % len(members))
    for m in members:
        c = str(m.get("staff_code", "") or "")
        lg = login_by_code.get(c)
        print("     %-10s %-26s %-24s %s"
              % (c or "—", str(m.get("name"))[:26], str(m.get("role"))[:24],
                 ("%s / %s" % (lg, pwd_for(c))) if lg else "NO LOGIN"))

    problems = []
    if not chair and not members:
        problems.append("nobody sits on this committee - a case sent here is "
                        "invisible to everyone")
    if members and len(members) < quorum:
        problems.append("%d member(s) against a quorum of %d - it can be seen "
                        "but can never decide" % (len(members), quorum))
    voters = [m for m in members if login_by_code.get(str(m.get("staff_code", "")))]
    if len(voters) < quorum:
        problems.append("only %d member(s) can actually sign in, against a "
                        "quorum of %d" % (len(voters), quorum))
    if chair and not any(str(m.get("name", "")).strip().lower() == chair.lower()
                         or login_by_code.get(str(m.get("staff_code", "")))
                         and str(users.get(login_by_code[str(m.get("staff_code",""))], {})
                                 .get("full_name", "")).strip().lower() == chair.lower()
                         for m in members):
        problems.append("the chair %r is not among the members - their vote is "
                        "mandatory, so the committee could never complete" % chair)

    if problems:
        print("\n  *** THIS COMMITTEE CANNOT WORK AS IT STANDS:")
        for x in problems:
            print("      - %s" % x)
        print("\n      Fix: python scripts\\seed_committee_members.py --apply")
    else:
        print("\n  This committee can hear a case and reach a decision.")

    # ── The walk ────────────────────────────────────────────────────────────
    owner = next((p for p in here if "relationship" in p["role"].lower()), here[0])
    prod = "Mortgage"
    stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
    doc = next((s for s in stages if "documentation" in s.lower()), stages[0] if stages else "")
    bcc = next((s for s in stages if "branch credit committee" in s.lower()), "")

    print("\n" + bar)
    print("THE WALK - do this in order")
    print(bar)
    deal_id = "WALK_%s" % branch.upper()[:6]
    o_login = login_by_code.get(owner["code"], "(no login)")
    print("""
  1. SIGN IN AS THE OWNER
       %s / %s      (%s, %s)
     Open A2Z Sales Pro and find the deal, or create one:
       client type Consumer, product %s, any value.

  2. GET IT TO %s
     The deal must be manager-validated first - a manager validates it from
     Manager Queues > Pipeline validation. Then open the deal, go to
     Documentation and Credit Review, attach the required documents, and press
     Submit. The button should read "Submit to %s" - if it says
     "credit analysis" the label fix has not been applied.

  3. SIGN IN AS EACH COMMITTEE MEMBER AND VOTE""" % (
        o_login, pwd_for(owner["code"]), owner["name"], owner["role"],
        prod, bcc or "the committee", bcc or "the next stage"))
    for m in members:
        c = str(m.get("staff_code", "") or "")
        lg = login_by_code.get(c)
        print("       %-22s %s" % (str(m.get("name"))[:22],
                                   ("%s / %s" % (lg, pwd_for(c))) if lg else "NO LOGIN"))
    print("""     Each opens Manager Queues > Committee, or the Daily Log if they are
     not a manager. The case should be listed. Press Review, and the voting
     bench is on the Branch Credit Committee tab.

     WATCH FOR: after voting, the row should read "You: recommended" and the
     tab count should drop by one. A member who votes twice should be refused.

  4. THE DECISION MOVES IT
     Once %d member(s) have voted INCLUDING THE CHAIR, the case advances by
     itself to the department analyst. Nobody needs to press submit.

     WATCH FOR: the Case Journey should show each vote by name, then the
     committee's decision, then "advanced automatically".

  5. IF NOTHING APPEARS IN A MEMBER'S QUEUE
       python scripts\\diag_committee_queue.py --deal <id> --user <their login>
     That names the reason: not a member, wrong stage, or out of scope.
""" % quorum)

    if seed or clean:
        pm = PipelineManager()
        pm.deals[:] = [d for d in pm.deals if str(d.get("id")) != deal_id]
        if clean:
            pm._save_deals()
            print("  removed %s" % deal_id)
            return 0
        if not bcc:
            print("  cannot seed: %s has no branch committee stage." % prod)
            return 1
        pm.deals.append({
            "id": deal_id, "client_name": "%s Walkthrough" % branch,
            "product": prod, "product_type": prod, "deal_value": 7500000,
            "staff_code": owner["code"], "staff_name": owner["name"],
            "branch": branch, "unit": branch, "client_type": "Consumer",
            "stage": bcc, "manager_validated": True,
            "committee_records": {}, "committee_votes": {}, "cr": {},
        })
        pm._save_deals()
        print("  seeded %s at %r, owned by %s." % (deal_id, bcc, owner["name"]))
        print("  It should be in every committee member's queue now.")
        print("  Remove it afterwards with --clean.")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
