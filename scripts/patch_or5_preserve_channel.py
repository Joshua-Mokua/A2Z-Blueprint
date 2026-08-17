#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
OR5 - a referred event deal is still an EVENT deal.

RULING (2026-08-11): "a deal can originate from an event as own, or it can be
referred - same as the rest."

OR3 stamped origin=referral whenever a deal travelled through the referral
engine, which DESTROYED the channel. A deal captured at a roadshow and then
handed to another RM stopped being an event deal, and "what did that roadshow
produce" became unanswerable - which is the whole reason origin exists.

That also contradicted the earlier ruling: SINGLE ORIGIN, BUT BRANCH AS IT
PROGRESSES. The referral is the branch, not a new origin.

THE FIX. should_stamp() refuses to overwrite a channel the deal already
carries. A system origin is stamped only when the deal is still on the default:

    an EVENT deal, then referred        -> stays events
    a PARTNERSHIP deal, then referred   -> stays partnership
    a SELF deal, then referred          -> becomes referral
    no origin, then referred            -> becomes referral

WAREHOUSE IS ALWAYS STAMPED, deliberately: a prospect claimed off the shelf did
not come from anywhere else. There was no earlier channel to protect, because
the deal did not exist until the claim.

NOBODY LOSES CREDIT. Verified: an event deal referred and accepted still credits
the referrer 3.0 in the daily log. The credit reads referral_chain and
referral_status, never origin - the two mechanisms were already independent, so
preserving the channel costs nothing.

THE ACCEPTED TRADE-OFF (ruling: "leave it as built"). Filtering the ranking by
"Referral" now shows only deals that ENTERED by referral. Referred event deals
sit under Events. Total referral-driven business remains answerable from the
chain, which records every hop - a referral is a movement, not a source, and
origin answers "where from".

Verified: py_compile clean; all five cases above behave as listed.

REQUIRES OR3.

Usage (from project root, .venv active):
    python scripts\patch_or5_preserve_channel.py            # dry run
    python scripts\patch_or5_preserve_channel.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deal_origin.py")
BACKUP_SUFFIX = ".pre_or5"

ANCHOR = '''def stamp(deal: dict, origin_key: str, party_code: str = "",
          party_name: str = "") -> dict:'''

GUARD_OLD = '''    k = str(origin_key or "").strip()
    if not is_known(k):
        return deal
    deal["origin"] = k'''

GUARD_NEW = '''    k = str(origin_key or "").strip()
    if not is_known(k):
        return deal
    if not should_stamp(deal, k):
        # Keep the channel; the referral is recorded in referral_chain and the
        # referrer is credited by the referral engine regardless.
        return deal
    deal["origin"] = k'''

SEGMENT = r'''def should_stamp(deal: dict, origin_key: str) -> bool:
    """Would stamping this origin DESTROY a better answer already on the deal?

    RULING (2026-08-11): "a deal can originate from an event as own, or it can
    be referred - same as the rest."

    So the channel and the route are different questions. A deal captured at a
    roadshow and then handed to another RM is STILL an event deal; the referral
    is the branch, not a new origin. Overwriting it would make "what did that
    roadshow produce" unanswerable, which is the whole reason origin exists.

    A system origin is therefore stamped only when the deal carries nothing
    better - it is still on the default. The referral itself is never lost: it
    lives in referral_chain, which records every hop, and the referrer is still
    credited through the referral engine's own rules.

    WAREHOUSE IS DIFFERENT and is always stamped: a prospect claimed off the
    shelf did not come from anywhere else. There was no earlier channel to
    protect, because the deal did not exist until the claim.
    """
    k = str(origin_key or "").strip()
    if k == "warehouse":
        return True
    current = str(deal.get("origin") or "").strip()
    return current in ("", DEFAULT_ORIGIN)


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found - apply patch_or1_deal_origin.py first." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "def should_stamp(" in s:
        print("ABORT: should_stamp already present - OR5 looks applied.")
        return 1
    if "def stamp(" not in s:
        print("ABORT: apply patch_or3_origin_evidence.py first.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: stamp anchor matched %d times." % s.count(ANCHOR))
        return 1
    if s.count(GUARD_OLD) != 1:
        print("ABORT: stamp body matched %d times." % s.count(GUARD_OLD))
        return 1

    s = s.replace(ANCHOR, SEGMENT + ANCHOR, 1)
    s = s.replace(GUARD_OLD, GUARD_NEW, 1)
    print("  ok  stamp preserves an existing channel")

    # The warehouse must still stamp, or a claimed prospect keeps whatever
    # origin it was given before the deal existed.
    if 'if k == "warehouse":' not in SEGMENT:
        print("ABORT: the warehouse exemption is missing - a claimed prospect")
        print("       would keep an origin from before the deal existed.")
        return 1
    if "DEFAULT_ORIGIN" not in SEGMENT:
        print("ABORT: should_stamp does not treat the default as replaceable.")
        return 1
    if s.count("def should_stamp(") != 1 or s.count("def stamp(") != 1:
        print("ABORT: post-check - duplicate definitions.")
        return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)

    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    sys.path.insert(0, os.getcwd())
    try:
        import importlib
        import utils.deal_origin as _do
        importlib.reload(_do)
        ev = {"origin": "events"}
        _do.stamp(ev, "referral", "KE343", "Nancy")
        sf = {"origin": "self"}
        _do.stamp(sf, "referral", "KE343", "Nancy")
        print("  ok  event deal referred  -> %s" % ev.get("origin"))
        print("  ok  self deal referred   -> %s" % sf.get("origin"))
        if ev.get("origin") != "events" or sf.get("origin") != "referral":
            print("  *** behaviour is not as expected")
            return 1
    except Exception as exc:
        print("  could not verify at runtime: %s" % exc)

    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
