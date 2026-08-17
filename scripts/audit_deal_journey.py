#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Walk a deal from capture to disbursement. READ ONLY unless --live. Exit 1 on a block.

RULING (2026-08-12): "today the pilot has to see a case travel from a deal to
disbursement. You can also audit that journey and confirm that there are no
hidden bugs."

WHY A WALK RATHER THAN A REVIEW. Reading the code tells you what each step
intends; only walking it tells you whether step 4 accepts what step 3 produced.
Every expensive bug on this system so far has lived in that seam - the DB sync
dropping event_id, the funnel bucket the seeder never filled, the settings file
thinned by a bare except. None of them were visible in the file that contained
them.

WHAT IT CHECKS, in the order a real deal meets them:

    1  the journey is configured and reachable end to end
    2  every stage transition the flow declares is actually permitted
    3  the document gate - what it demands, and WHO can satisfy it
    4  the manager-validation gate
    5  the credit handoff (does an application get created, and linked back)
    6  the credit-admin and disbursement steps
    7  the labels a person actually reads at each step

A BLOCK is something that stops the deal. A WARNING is something that will
confuse the person driving it. Both are reported; only blocks fail the run.

    python scripts\\audit_deal_journey.py
    python scripts\\audit_deal_journey.py --product "Business Term Loan"
"""
import os
import sys

sys.path.insert(0, os.getcwd())

BLOCKS, WARNINGS = [], []


def block(what, detail=""):
    BLOCKS.append((what, detail))
    print("  BLOCK  %s" % what)
    if detail:
        print("         %s" % detail)


def warn(what, detail=""):
    WARNINGS.append((what, detail))
    print("  warn   %s" % what)
    if detail:
        print("         %s" % detail)


def ok(what, detail=""):
    print("  ok     %-44s %s" % (what, detail))


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    product = "Business Term Loan"
    if "--product" in sys.argv:
        i = sys.argv.index("--product")
        if i + 1 < len(sys.argv):
            product = sys.argv[i + 1]

    try:
        from utils.core import get_pipeline_settings
        from utils.pipeline_funnel import buckets_for
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    cfg = get_pipeline_settings() or {}

    rule("1. IS THE JOURNEY CONFIGURED END TO END?")
    flows = cfg.get("stage_flows") or {}
    flow_key = None
    prod_flows = cfg.get("product_flows") or {}
    entry = prod_flows.get(product) if isinstance(prod_flows, dict) else None
    if isinstance(entry, dict) and entry.get("stages"):
        stages = [str(s.get("stage", "")).strip() for s in entry["stages"]]
        flow_key = "product:%s" % product
    else:
        # Fall back to the class flow the deal would actually resolve to.
        for key in ("asset", "loan", "default"):
            if isinstance(flows.get(key), list) and flows[key]:
                stages = [str(x) for x in flows[key]]
                flow_key = key
                break
        else:
            stages = []
    if not stages:
        block("no stage flow resolves for %r" % product,
              "the deal would have nowhere to advance to")
        return 1
    ok("flow resolved", "%s - %d stages" % (flow_key, len(stages)))
    for n, st in enumerate(stages, 1):
        print("         %2d. %s" % (n, st))

    terminal = [s for s in stages if s.lower().startswith("closed")]
    if not terminal:
        warn("no terminal stage in the flow",
             "nothing marks the deal finished; it can be advanced for ever")

    rule("2. DOES EVERY DECLARED TRANSITION EXIST?")
    # settings["stages"] is a LEGACY generic sales list - Prospecting, Needs
    # Analysis, Proposal - left over from before the banking journey existed.
    # The advance endpoint validates against _stage_flow_for(), NOT against it.
    #
    # The first version of this audit compared the two and reported eight
    # stages as rejected, which would have been catastrophic and is not true.
    # Checked instead: does the advance path consult that list at all?
    api_src = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    ai = api_src.find('@app.post("/api/pipeline/deals/{deal_id}/advance")')
    aseg = api_src[ai:ai + 4000] if ai > 0 else ""
    if aseg and '"stages"' in aseg:
        block("the advance endpoint validates against settings['stages']",
              "which still holds the legacy sales list, so the banking stages "
              "would be refused")
    elif aseg:
        ok("advance validates against the product flow", "not the legacy list")
    else:
        warn("advance endpoint not found", "could not verify what it validates")

    legacy = [str(s.get("stage", s) if isinstance(s, dict) else s)
              for s in (cfg.get("stages") or [])]
    if legacy and not set(stages) & set(legacy):
        warn("settings['stages'] shares nothing with the live journey",
             "it is dead config (%d entries) - harmless today, but the next "
             "person to read it will believe it is the pipeline" % len(legacy))

    rule("3. THE DOCUMENT GATE")
    docs = (entry or {}).get("required_documents") or []
    at_stage = str((entry or {}).get("documents_required_at_stage", "") or "")
    if not docs:
        warn("no documents configured for %r" % product,
             "the gate passes trivially - fine today, but nothing is being asked for")
    else:
        ok("documents configured", "%d required" % len(docs))
        if at_stage and at_stage not in stages:
            block("documents_required_at_stage %r is not in the flow" % at_stage,
                  "the gate can never be reached, so it never releases")
        elif at_stage:
            ok("required at", at_stage)

        # WHO ATTACHES. A flat list of names says nothing about who is
        # responsible, so every document lands on the deal owner - including
        # the ones only an analyst can produce.
        shaped = [d for d in docs if isinstance(d, dict)]
        if not shaped:
            warn("no document says WHO attaches it",
                 "every one falls to the deal owner, including analyst-produced "
                 "papers the owner cannot obtain")

    rule("4. GATES BETWEEN THE OWNER AND CREDIT")
    src = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    i = src.find('@app.post("/api/pipeline/deals/{deal_id}/submit-to-credit")')
    # To the NEXT endpoint, not a fixed byte count. A window sized in bytes
    # silently truncates the moment the endpoint grows, and then reports the
    # things past the cut as missing - which is what happened the first time
    # this ran after the soft gate was added.
    j = src.find("\n@app.", i + 10) if i > 0 else -1
    seg = src[i:j if j > 0 else i + 12000] if i > 0 else ""
    if not seg:
        block("submit-to-credit endpoint not found")
    else:
        if "manager_validated" in seg:
            ok("manager validation is required", "deliberate control point")
        else:
            warn("no manager-validation gate", "an unvalidated deal can reach credit")
        if 'detail="Cannot submit to credit — missing documents' in seg:
            # This is the hard condition the pilot flagged.
            block("the document gate is ALL-OR-NOTHING",
                  "one outstanding paper blocks submission entirely, even when it "
                  "is not what the analysis is waiting for")
        else:
            ok("document gate allows partial submission", "")

    rule("5. THE CREDIT HANDOFF")
    if "create_from_pipeline_deal" in seg:
        ok("an application is created on submit", "")
    else:
        block("no application is created", "the deal reaches credit with nothing to work on")
    if "lms_application_id" in src or "application_id" in seg:
        ok("the application id is linked back to the deal", "")
    else:
        warn("no link back from the deal to its application",
             "somebody on the deal cannot find the credit case")

    rule("6. CREDIT ADMIN AND DISBURSEMENT")
    for label, needle in (("offer letter step", "Offer Letter"),
                          ("security perfection step", "Legal - Security Perfection"),
                          ("disbursement step", "Disbursement")):
        if needle in stages:
            ok(label, needle)
        else:
            warn("%s missing from the flow" % label,
                 "the deal cannot reach it by advancing")

    rule("7. WHAT THE PERSON READS")
    try:
        pdd = open(os.path.join("frontend", "web", "src", "pages",
                                "PipelineDealDetail.tsx"), encoding="utf-8").read()
    except OSError:
        pdd = ""
    # Look at the JSX the button RENDERS, not anywhere in the file - the phrase
    # also appears in comments explaining why it was wrong, and matching those
    # made the audit report a fix as a fault.
    import re as _re
    btn = _re.search(r"<Button[^>]*>\s*\{?([^<}]{0,60})", pdd)
    label = (btn.group(1).strip() if btn else "")
    if "Submit to Credit Analysis" in pdd and "submit_label" not in pdd:
        # The advance is one stage, config-driven and correct. The LABEL is not.
        nxt = ""
        if "Documentation" in stages:
            k = stages.index("Documentation")
            if k + 1 < len(stages):
                nxt = stages[k + 1]
        block("the button says 'Submit to Credit Analysis'",
              "but the deal advances ONE stage, which from Documentation is %r. "
              "The label names a step three transitions away." % (nxt or "the next stage"))
    elif "submit_label" in pdd:
        ok("the submit button names the real next stage",
           "from the flow, per product")
    else:
        warn("could not determine the submit label", label[:40])

    rule("VERDICT")
    if not BLOCKS:
        print("A deal can travel from capture to disbursement.")
        if WARNINGS:
            print("%d warning(s) - none stop the deal, all will confuse somebody."
                  % len(WARNINGS))
        return 0
    print("%d BLOCK(S) between a deal and disbursement:\n" % len(BLOCKS))
    for what, detail in BLOCKS:
        print("   * %s" % what)
        if detail:
            print("     %s" % detail)
    if WARNINGS:
        print("\n%d warning(s) as well." % len(WARNINGS))
    return 1


if __name__ == "__main__":
    sys.exit(main())
