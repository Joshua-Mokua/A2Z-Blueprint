# A helper the bundle runs: set every DEPARTMENT committee to quorum 1,
# SINGLE_APPROVER, chair not required. One recommendation moves a case.
import json, os, shutil, sys
from datetime import datetime
CFG = os.path.join("data", "lms_config.json")

def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("  %s not found." % CFG); return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    # A department committee is one whose code is not a generated branch one.
    dept = [c for c in pal
            if not str(c.get("code", "")).upper().startswith("BCC_BRN")]
    print("  committees            %d" % len(pal))
    print("  department committees %d\n" % len(dept))
    plan = []
    for c in dept:
        want = {}
        if c.get("min_quorum_count") != 1:
            want["min_quorum_count"] = 1
        if (c.get("voting_rule") or "SIMPLE_MAJORITY") != "SINGLE_APPROVER":
            want["voting_rule"] = "SINGLE_APPROVER"
        if c.get("chair_vote_required", True):
            want["chair_vote_required"] = False
        if want:
            plan.append((c, want))
    if not plan:
        print("  Every department committee already moves on one recommendation.")
        return 0
    print("  %-6s %-40s %s" % ("CODE", "NAME", "CHANGES"))
    for c, want in plan:
        print("  %-6s %-40s %s"
              % (c.get("code"), str(c.get("name"))[:40],
                 ", ".join("%s=%s" % kv for kv in want.items())))
    print("\n  One person recommends and the case moves. That is the design;")
    print("  the quorum floor of 2 was stopping it.")
    if not apply:
        print("\n  Dry run.")
        return 0
    bak = CFG + ".pre_deptq_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    for c, want in plan:
        c.update(want)
        c["quorum_note"] = ("department committee: one recommendation moves a "
                            "case, set deliberately")
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\n  Written. Backup: %s" % os.path.basename(bak))
    return 0

if __name__ == "__main__":
    sys.exit(main())
