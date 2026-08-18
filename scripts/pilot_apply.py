#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Do everything a release needs after merging. DRY RUN by default.

WHY THIS EXISTS. A release delivers CODE. Several fixes then need a REBUILD and
a CONFIGURATION step before anybody notices a difference - and those were being
sent as a list of separate commands in a message. Some got run, some did not,
and the pilot reported the fault still there. That is not carelessness; it is
too many steps in a message.

This is one command. It is idempotent - a step already done is skipped, not
repeated - so running it twice is safe, and running it after every merge is the
intended habit.

    python scripts\\pilot_apply.py                            # shows what it WOULD do
    python scripts\\pilot_apply.py --apply                    # development side
    python scripts\\pilot_apply.py --apply --hide-modules     # the pilot

--hide-modules hides Dashboard, Initiatives, Profitability and SLA Monitor,
which the bank asked for while those are still being detailed. It is a flag
rather than a default because the same script runs on both boxes and the right
answer differs.

WHAT IT WILL NOT DO. It does not touch anything where the right answer is a
judgement rather than a fact: which products need a committee gate, which
documents belong to an analyst, and what a product flow should end with. Those
are named at the end as work for a person, because a script guessing at them
would put wrong rules into a live bank.

Run scripts\\pilot_status.py afterwards and send that output back.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.getcwd())

DID, SKIP, TODO = [], [], []


def did(what):
    DID.append(what)
    print("  DONE     %s" % what)


def skip(what, why):
    SKIP.append(what)
    print("  already  %-44s %s" % (what[:44], why))


def head(t):
    print("\n" + "-" * 74)
    print(t)
    print("-" * 74)


def main():
    apply = "--apply" in sys.argv
    if not os.path.isdir("utils") or not os.path.isdir("data"):
        print("ABORT: run this from the project root.")
        return 1

    print("=" * 74)
    print("POST-RELEASE SETUP  %s" % ("(APPLYING)" if apply else "(DRY RUN)"))
    print("=" * 74)

    # ── 1. BRANCH COMMITTEES ────────────────────────────────────────────────
    # Created from THIS box's org_config, because the branch list and the
    # managers differ per deployment - which is why they cannot ship in a
    # release.
    head("1. BRANCH CREDIT COMMITTEES")
    cfg_path = os.path.join("data", "lms_config.json")
    org_path = os.path.join("data", "org_config.json")
    try:
        lms = json.load(open(cfg_path, encoding="utf-8")) or {}
    except Exception as exc:
        print("  ABORT: cannot read %s: %s" % (cfg_path, exc))
        return 1
    try:
        org = json.load(open(org_path, encoding="utf-8")) or {}
    except Exception as exc:
        print("  ABORT: cannot read %s: %s" % (org_path, exc))
        return 1

    cw = lms.get("credit_workflow")
    if not isinstance(cw, dict):
        cw = {}
    palette = cw.get("committee_palette")
    if not isinstance(palette, list):
        palette = []
    have = {str(c.get("branch", "")).strip().lower()
            for c in palette if str(c.get("kind", "")).lower() == "branch"}

    branches = org.get("branches") or []
    if isinstance(branches, dict):
        branches = list(branches.values())
    planned = []
    for b in branches:
        if not isinstance(b, dict) or str(b.get("type", "")).upper() == "HO":
            continue
        name = str(b.get("name", "")).strip()
        if not name or name.lower() in have:
            continue
        planned.append({
            "code": "BCC_" + str(b.get("code", name)).strip().upper().replace(" ", "_"),
            "name": "%s Branch Credit Committee" % name,
            "chaired_by": "",
            "recording_mode": "voting",
            "voting_rule": "SIMPLE_MAJORITY",
            "amount_threshold_kes": 0.0,
            "branch": name,
            # The field every branch filter looks for. Without it a committee
            # exists and is invisible to every branch journey.
            "kind": "branch",
            "members": [],
        })

    if not planned:
        skip("branch committees", "%d already exist" % len(have))
    else:
        print("  will create %d branch committee(s):" % len(planned))
        for c in planned[:6]:
            print("     %s" % c["name"])
        if len(planned) > 6:
            print("     ... and %d more" % (len(planned) - 6))
        if apply:
            shutil.copy2(cfg_path, cfg_path + ".bak")
            palette.extend(planned)
            cw["committee_palette"] = palette
            lms["credit_workflow"] = cw
            tmp = cfg_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(lms, fh, indent=2)
            os.replace(tmp, cfg_path)
            did("created %d branch committee(s)" % len(planned))

    # ── 1b. COMMITTEE MEMBERS ───────────────────────────────────────────────
    # Creating the committees is not enough: they come out EMPTY, and a voting
    # committee with no members cannot decide - a case reaching that gate stops
    # with nothing in the interface to free it. That is worse than having no
    # committees at all, so seeding members belongs in the same command.
    #
    # Drawn from THIS box's staff register, which is why it cannot ship as
    # data: chair is the branch manager, members are the service and operations
    # managers plus every relationship manager except direct sales.
    #
    # Sixteen committees is a lot of hand-assignment to get wrong once.
    head("1b. COMMITTEE MEMBERS")
    try:
        import subprocess as _sp
        _r = _sp.run([sys.executable, os.path.join("scripts", "seed_committee_members.py")]
                     + (["--apply"] if apply else []),
                     capture_output=True, text=True, timeout=300)
        for _ln in (_r.stdout or "").strip().split("\n")[-16:]:
            if _ln.strip():
                print("  %s" % _ln.rstrip()[:96])
        if apply and _r.returncode == 0:
            did("seeded committee members")
    except Exception as _exc:
        print("  could not seed members: %s" % _exc)
        print("  Run it by hand: python scripts\\seed_committee_members.py --apply")

    # ── 1c. COMMITTEE ROUTING ───────────────────────────────────────────────
    # ANOTHER STEP THAT WAS LEFT AS A SEPARATE COMMAND AND THEREFORE MISSED.
    # The pilot ran everything it was told to, the sixteen branch committees
    # correctly stopped appearing as product gates - and BCC1, the placeholder
    # they are meant to be chosen through, was never created, because the
    # script that creates it was never in this list.
    #
    # It also repoints client_type_to_dcc, which names DCC_CONS / DCC_COMM /
    # DCC_CIB - none of which exist in the palette, so every deal routes to a
    # committee that is not there.
    #
    # Anything a release cannot carry belongs in THIS command. A step sent as
    # a line in a message is a step that gets missed, and that is on whoever
    # wrote the message rather than on whoever read it.
    head("1c. COMMITTEE ROUTING")
    try:
        import subprocess as _sp2
        _r2 = _sp2.run([sys.executable, os.path.join("scripts", "fix_committee_routing.py")]
                       + (["--apply"] if apply else []),
                       capture_output=True, text=True, timeout=300)
        for _ln in (_r2.stdout or "").strip().split("\n")[-12:]:
            if _ln.strip():
                print("  %s" % _ln.rstrip()[:96])
        if apply and _r2.returncode == 0:
            did("committee routing")
    except Exception as _exc:
        print("  could not fix routing: %s" % _exc)
        print("  Run it by hand: python scripts\\fix_committee_routing.py --apply")

    # ── 2. HIDDEN MODULES ───────────────────────────────────────────────────
    # Only on a deployment that has asked for it. An empty list hides nothing,
    # so this can never take a module away from somebody who did not ask.
    head("2. MODULES HIDDEN FOR THE BANK")
    # BEHIND A FLAG, and deliberately. This script is meant to be run on BOTH
    # boxes after a merge, and hiding modules is right on the pilot and wrong
    # here - the development side keeps all of them. A step whose correct
    # answer differs per deployment must be asked for, not assumed.
    want = ["/", "/initiatives", "/profitability", "/sla"]
    cur = org.get("hidden_modules")
    if "--hide-modules" not in sys.argv:
        skip("hidden_modules", "not requested - pass --hide-modules on the pilot")
    elif isinstance(cur, list) and cur:
        skip("hidden_modules", ", ".join(cur))
    else:
        print("  will hide: Dashboard, Initiatives, Profitability, SLA Monitor")
        print("  (they stay visible on the development side)")
        if apply:
            shutil.copy2(org_path, org_path + ".bak")
            org["hidden_modules"] = want
            tmp = org_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(org, fh, indent=2)
            os.replace(tmp, org_path)
            did("set hidden_modules")

    # ── 3. THE FRONTEND ─────────────────────────────────────────────────────
    # The step most often missed, and the one that makes a correct fix look
    # unapplied: the code is right and the browser is serving the old bundle.
    head("3. FRONTEND BUILD")
    web = os.path.join("frontend", "web")
    dist, src = os.path.join(web, "dist"), os.path.join(web, "src")
    stale = True
    if os.path.isdir(dist) and os.path.isdir(src):
        ns = max((os.path.getmtime(os.path.join(b, f))
                  for b, _d, fs in os.walk(src) for f in fs), default=0)
        nd = max((os.path.getmtime(os.path.join(b, f))
                  for b, _d, fs in os.walk(dist) for f in fs), default=0)
        stale = nd < ns
    if not stale:
        skip("frontend build", "already newer than the source")
    else:
        print("  the build is older than the source - the browser is showing")
        print("  old code. This is why a merged fix can look unapplied.")
        if apply:
            print("\n  running pnpm build (this takes a minute)...")
            try:
                r = subprocess.run("pnpm build", cwd=web, shell=True,
                                   capture_output=True, text=True, timeout=900)
                if r.returncode == 0:
                    did("rebuilt the frontend")
                else:
                    print("  BUILD FAILED - last lines:")
                    for ln in (r.stderr or r.stdout).strip().split("\n")[-8:]:
                        print("     %s" % ln[:100])
                    print("\n  Stop here and send these lines back. Everything")
                    print("  above this point was applied.")
                    return 1
            except Exception as exc:
                print("  could not run pnpm build: %s" % exc)
                print("  Run it by hand:  cd frontend\\web && pnpm build")
                return 1

    # ── WHAT A PERSON STILL HAS TO DECIDE ───────────────────────────────────
    head("STILL NEEDS A PERSON")
    try:
        ps = json.load(open(os.path.join("data", "pipeline_settings.json"),
                            encoding="utf-8")) or {}
    except Exception:
        ps = {}
    flows = ps.get("product_flows") or {}

    noclose = [p for p, e in flows.items()
               if ((e or {}).get("stages")
                   and not any("closed" in str(s.get("stage", "")).lower()
                               for s in (e or {}).get("stages") or []))]
    if noclose:
        TODO.append("%d product flow(s) have NO closing stage, so their deals "
                    "can never be closed by anyone: %s"
                    % (len(noclose), ", ".join(noclose[:5])
                       + (" +%d" % (len(noclose) - 5) if len(noclose) > 5 else "")))

    gated = [p for p, e in flows.items() if (e or {}).get("committee_journey")]
    if not gated:
        TODO.append("No product routes through a committee. The committees now "
                    "exist; Admin > product flow > '+ Add committee gate' is "
                    "what turns one into a step a deal passes through.")

    assigned = sum(1 for _p, e in flows.items()
                   for d in ((e or {}).get("required_documents") or [])
                   if isinstance(d, dict)
                   and str(d.get("attached_by", "owner")) != "owner")
    if not assigned:
        TODO.append("Every required document still falls to the deal owner. "
                    "Admin > product flow: set who attaches each one, and tick "
                    "'mandatory' only on those that genuinely must block.")

    if TODO:
        for t in TODO:
            print("  * %s" % t)
        print("")
        print("  These are decisions about how the bank works, not settings a")
        print("  script should guess at - a wrong answer here puts wrong rules")
        print("  into a live system.")
    else:
        print("  nothing outstanding.")

    print("\n" + "=" * 74)
    if not apply:
        print("DRY RUN - nothing changed. Re-run with --apply.")
        return 0
    print("Applied %d change(s), skipped %d already in place." % (len(DID), len(SKIP)))
    print("")
    print("NOW RESTART THE API (uvicorn), then run:")
    print("  python scripts\\pilot_status.py")
    print("and send that whole page back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
