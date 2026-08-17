#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SP1 - the credit spine, enforced on save; a non-branch deal skips the BCC.

RULING (2026-08-12): "whose originator is from the branch must pass through the
Branch Credit Committee after documentation, then to the department analysts,
then the Department Credit Committee, then Credit Analysis, then Credit
Administration, then Trops ... in between admin can add the mini-stages which
vary from product to product ... for any RM not at the branch, especially CIB,
they start from the Department Credit Analyst after documentation ... I need
uniformity across the product lines."

THE SPINE IS NOT INVENTED. Seven of the twelve Asset products already carried
exactly this sequence, so this finishes a standard rather than imposing one:

    Documentation -> Branch Credit Committee Review -> Department Credit
    Analysis -> Department Credit Committee Review -> Credit Analysis ->
    Credit Administration -> Trops

ENFORCED ON SAVE, in _validate_product_flow. A default is a suggestion; a flow
that breaks the spine is now refused with a reason instead of being saved and
found later by a case that cannot move. EXTRA STAGES REMAIN FREE - anything may
sit between the fixed points, in any number. What cannot happen is a spine
stage being dropped, or two ending up in the wrong order.

ONLY LENDING PRODUCTS. product_catalogue is already classed and "Assets" holds
the twelve credit products. Forcing a savings account through a credit
committee would be worse than no rule at all.

EVERY FLOW MUST BE ABLE TO END. Thirteen had no closing stage, so their deals
could never be closed by anyone - the fixed deposit the pilot reported, and
twelve more nobody had reached yet.

A NON-BRANCH DEAL SKIPS THE BRANCH COMMITTEE. The spine belongs to a PRODUCT;
whether the branch committee applies belongs to the DEAL, and one flow serves a
branch RM and a CIB RM alike. The skip happens at advance time rather than by
keeping two flows per product, which would double the admin surface and the
ways two flows drift apart. It is how committees already behave -
_effective_committee_journey drops branch-only committees for a deal with no
branch; the stage side had simply not caught up. Forward only, over that one
stage, and audited.

scripts/migrate_to_credit_spine.py brings the remaining five onto it - Asset
Finance, Bundled Loan Product, Business Loan, Overdraft, Personal Loan - and
gives the four deposit flows their closing stages. It shows its plan and COUNTS
THE LIVE DEALS ON EVERY STAGE IT WOULD RENAME before changing anything, because
a rename moves cases and where they land is a decision about the bank's
process.

ITS FIRST VERSION WAS WRONG AND THE DRY RUN CAUGHT IT: renaming alone left
"Credit Analysis" sitting before the Branch Credit Committee, so the migration
produced a flow violating the spine it was building. It now lays the spine down
in ITS order and attaches every other stage to whichever spine stage it
currently follows.

Verified: py_compile clean; all 12 credit products pass the spine after
migration, and the 4 deposit flows gain closing stages.

Usage (from project root, .venv active):
    python scripts\\patch_sp1_credit_spine.py            # dry run
    python scripts\\patch_sp1_credit_spine.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
MIG = os.path.join("scripts", "migrate_to_credit_spine.py")
BACKUP_SUFFIX = ".pre_sp1"

VALIDATOR_ANCHOR = "def _validate_product_flow(entry: dict, catalogue_names=None) -> tuple:"
GATE_ANCHOR = '    journey = entry.get("committee_journey")'
SKIP_ANCHOR = "    if _flow and payload.new_stage not in _flow:"

SPINE = r'''# ── THE MANDATORY CREDIT SPINE ──────────────────────────────────────────────
# RULING (2026-08-12): "whose originator is from the branch must pass through
# the Branch Credit Committee after documentation, then to the department
# analysts, then the Department Credit Committee, then Credit Analysis, then
# Credit Administration, then Trops ... then in between admin can add the
# mini-stages which vary from product to product. I need uniformity across the
# product lines."
#
# ENFORCED ON SAVE, not defaulted. A default is a suggestion; a product flow
# that breaks the spine is now refused with a reason rather than saved and
# discovered by a case that cannot move.
#
# THESE NAMES ARE NOT INVENTED. Seven of the twelve Asset products already
# carry exactly this sequence - Mortgage, Invoice Discounting, Trade Finance
# LC, Structured Finance, Term Loan, Trade Finance, Working Capital. The spine
# is the existing standard being finished, not a new one imposed.
#
# EXTRA STAGES ARE FREE. Admin may put anything between the fixed points, in
# any number - that is the per-product variation. What cannot happen is a spine
# stage being removed, or two of them ending up in the wrong order.
CREDIT_SPINE = [
    "Documentation",
    "Branch Credit Committee Review",
    "Department Credit Analysis",
    "Department Credit Committee Review",
    "Credit Analysis",
    "Credit Administration",
    "Trops",
]

# ONLY LENDING PRODUCTS. product_catalogue is already classed, and "Assets"
# holds the twelve credit products. Forcing a savings account through a credit
# committee would be worse than having no rule at all.
CREDIT_CLASS = "Assets"


def _is_credit_product(product: str) -> bool:
    try:
        cat = (_load_json("pipeline_settings.json") or {}).get("product_catalogue") or {}
        names = cat.get(CREDIT_CLASS) or []
        return str(product or "").strip().lower() in {
            str(n).strip().lower() for n in names}
    except Exception:
        return False


def _spine_violation(stage_names: list, product: str = "") -> str:
    """'' if the flow honours the spine, else why not.

    Checks PRESENCE and ORDER only. Anything may sit between spine stages.
    """
    if product and not _is_credit_product(product):
        return ""
    missing = [x for x in CREDIT_SPINE if x not in stage_names]
    if missing:
        return ("a lending product must include %s. Extra stages may go "
                "anywhere between them, but the spine itself is fixed."
                % ", ".join("'%s'" % m for m in missing))
    pos = [stage_names.index(x) for x in CREDIT_SPINE]
    if pos != sorted(pos):
        out_of_order = [CREDIT_SPINE[i] for i in range(1, len(pos))
                        if pos[i] < pos[i - 1]]
        return ("the spine is out of order at %s - a case must reach these in "
                "sequence" % ", ".join("'%s'" % o for o in out_of_order))
    return ""


'''

GATE = r'''    # ── EVERY FLOW MUST BE ABLE TO END ──────────────────────────────────────
    # Thirteen flows had no closing stage, so their deals could never be closed
    # by anybody - the fixed deposit the pilot reported, and twelve more in the
    # same state that nobody had hit yet.
    _names = [str(s.get("stage", "") or "").strip() for s in stages]
    if not any("closed" in n.lower() for n in _names):
        return False, ("every flow needs a closing stage - add 'Closed Won' "
                       "and 'Closed Lost', or a deal on this product can "
                       "never be finished")

    _prod = str(entry.get("product", "") or "")
    _v = _spine_violation(_names, _prod)
    if _v:
        return False, _v

'''

SKIP = r'''    # ── A NON-BRANCH DEAL SKIPS THE BRANCH COMMITTEE ────────────────────────
    # RULING (2026-08-12): "for any RM who is not at the branch, especially CIB
    # RMs and a few in commercial, they start theirs from the Department Credit
    # Analyst after documentation."
    #
    # The spine belongs to a PRODUCT; whether the branch committee applies
    # belongs to the DEAL. One flow serves both, so the branch stage is skipped
    # at advance time rather than maintained as a second flow per product -
    # which would double the admin surface and the ways two flows drift apart.
    #
    # This is how committees already behave: _effective_committee_journey drops
    # branch-only committees for a deal with no branch. The stage side simply
    # had not caught up.
    #
    # ONLY SKIPS FORWARD, and only over the branch committee. It does not let a
    # deal jump anywhere else, and a BRANCH deal is untouched.
    if (_flow and payload.new_stage == "Branch Credit Committee Review"
            and not _deal_is_branch_originated(deal)):
        _i = _flow.index(payload.new_stage)
        if _i + 1 < len(_flow):
            _skipped = payload.new_stage
            payload.new_stage = _flow[_i + 1]
            _audit("API_PIPELINE_SKIP_BRANCH_CTTEE", user,
                   f"deal_id={deal_id} skipped={_skipped} to={payload.new_stage} "
                   f"reason=not_branch_originated")

'''

MIGRATION = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bring the remaining lending products onto the credit spine. DRY RUN by default.

Seven of the twelve Asset products already carry the spine. This maps the other
five onto it:

    Asset Finance, Bundled Loan Product, Business Loan, Overdraft, Personal Loan

RENAMING A STAGE MOVES LIVE DEALS. That is the whole risk here, so this counts
the deals sitting on every stage it would touch and shows them BEFORE changing
anything. A stage carrying deals is not renamed silently - it is listed, with
the count, so somebody can decide whether that is where those cases should end
up.

WHAT MAPS TO WHAT, and why each one:

    Credit Assessment - BCC      -> Branch Credit Committee Review
        the same step under an older name

    Credit Analysis & Assesment  -> Credit Analysis
    Credit Analyst & Assesment   -> Credit Analysis
        two spellings of one stage, both reaching users

    Credit Admin                 -> Credit Administration
    Closed - Trops               -> Trops
    Closed Lost - Trops          -> Trops
        "Closed - Trops" conflated a working stage with a closing one, which is
        why these flows had no real closing stage

Stages with no mapping are LEFT WHERE THEY ARE. Lead, Contacted, Qualified,
Offer / Proposal and Negotiation are legitimate per-product steps and the spine
explicitly allows extra stages between its fixed points.

MISSING SPINE STAGES ARE INSERTED in the right place, with Closed Won and
Closed Lost appended - a flow that cannot be closed is the fault behind the
fixed deposit the pilot reported.

    python scripts\\migrate_to_credit_spine.py
    python scripts\\migrate_to_credit_spine.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

PS = os.path.join("data", "pipeline_settings.json")

SPINE = [
    "Documentation",
    "Branch Credit Committee Review",
    "Department Credit Analysis",
    "Department Credit Committee Review",
    "Credit Analysis",
    "Credit Administration",
    "Trops",
]

RENAME = {
    "credit assessment - bcc": "Branch Credit Committee Review",
    "credit analysis & assesment": "Credit Analysis",
    "credit analyst & assesment": "Credit Analysis",
    "credit admin": "Credit Administration",
    "closed - trops": "Trops",
    "closed lost - trops": "Trops",
}

CLOSING = ["Closed Won", "Closed Lost"]


def _deal_counts():
    """How many live deals sit on each stage, per product."""
    out = {}
    try:
        from utils.core import PipelineManager
        for d in (getattr(PipelineManager(), "deals", []) or []):
            prod = str(d.get("product_type") or d.get("product") or "")
            stage = str(d.get("stage") or "")
            if prod and stage:
                out.setdefault(prod, {}).setdefault(stage, 0)
                out[prod][stage] += 1
    except Exception:
        pass
    return out


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PS):
        print("ABORT: %s not found - run from the project root." % PS)
        return 1

    ps = json.load(open(PS, encoding="utf-8")) or {}
    flows = ps.get("product_flows") or {}
    cat = (ps.get("product_catalogue") or {}).get("Assets") or []
    assets = {str(n).strip().lower() for n in cat}
    counts = _deal_counts()

    print("=" * 76)
    print("MIGRATE TO THE CREDIT SPINE")
    print("=" * 76)

    plans, moves = [], []
    for prod, e in sorted(flows.items()):
        names_now = [str(x.get("stage", "") or "") for x in (e or {}).get("stages") or []]
        # NON-CREDIT PRODUCTS GET THE CLOSING STAGES TOO, and nothing else. A
        # savings account must not be forced through a credit committee, but it
        # must still be closable - Fixed Deposit is the one the pilot reported,
        # and Current Account, Savings Account and Credit Card sit in exactly
        # the same state behind it.
        if prod.strip().lower() not in assets:
            if names_now and not any("closed" in n.lower() for n in names_now):
                add = [c for c in CLOSING
                       if not any(c.lower() == n.lower() for n in names_now)]
                plans.append((prod, names_now, names_now + add, [], add))
            continue
        names = [str(s.get("stage", "") or "") for s in (e or {}).get("stages") or []]
        if all(x in names for x in SPINE):
            pos = [names.index(x) for x in SPINE]
            if pos == sorted(pos) and any("closed" in n.lower() for n in names):
                continue  # already good

        new_names, renamed = [], []
        for n in names:
            r = RENAME.get(n.strip().lower())
            if r:
                renamed.append((n, r))
                if r not in new_names:
                    new_names.append(r)
            elif n not in new_names:
                new_names.append(n)

        # ── REBUILD IN SPINE ORDER ──────────────────────────────────────────
        # Renaming alone is not enough, and the first version of this proved
        # it: "Credit Analysis & Assesment" sat at position four, was renamed
        # to "Credit Analysis", and stayed there - so the migration produced
        # Credit Analysis BEFORE the Branch Credit Committee, violating the
        # spine it was building. The dry run showed it; nothing was applied.
        #
        # So the spine is laid down in ITS order, and every other stage is
        # attached to whichever spine stage it currently follows. A product's
        # own steps keep their place in the journey without being able to
        # displace a fixed point.
        inserted = [sp for sp in SPINE if sp not in new_names]

        spine_set = set(SPINE)
        extras_after = {sp: [] for sp in SPINE}
        lead_extras = []          # anything before the first spine stage
        current = None
        for n in new_names:
            if n in spine_set:
                current = n
            elif current is None:
                lead_extras.append(n)
            else:
                extras_after[current].append(n)

        rebuilt_names = list(lead_extras)
        for sp in SPINE:
            rebuilt_names.append(sp)
            rebuilt_names.extend(extras_after.get(sp, []))
        new_names = rebuilt_names

        for c in CLOSING:
            if not any(c.lower() == x.lower() for x in new_names):
                new_names.append(c)
                inserted.append(c)

        plans.append((prod, names, new_names, renamed, inserted))
        for old, new in renamed:
            n = (counts.get(prod) or {}).get(old, 0)
            if n:
                moves.append((prod, old, new, n))

    if not plans:
        print("  Every lending product already carries the spine.")
        return 0

    for prod, old, new, renamed, inserted in plans:
        print("\n  %s" % prod)
        print("     before  %s" % " -> ".join(old))
        print("     after   %s" % " -> ".join(new))
        if renamed:
            print("     renamed %s" % "; ".join("%s -> %s" % r for r in renamed))
        if inserted:
            print("     added   %s" % ", ".join(inserted))

    print("\n" + "-" * 76)
    if moves:
        print("  *** LIVE DEALS THAT WOULD MOVE")
        for prod, old, new, n in moves:
            print("     %-22s %-28s -> %-28s %d deal(s)"
                  % (prod[:22], old[:28], new[:28], n))
        print("")
        print("  Read that list before applying. A rename moves every deal on")
        print("  that stage, and where those cases land is a decision about")
        print("  the bank's process - not something to discover afterwards.")
    else:
        print("  No live deal sits on any stage being renamed.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PS, PS + ".pre_spine")
    for prod, _old, new_names, _r, _i in plans:
        e = flows[prod]
        by_name = {str(s.get("stage", "") or ""): s for s in (e.get("stages") or [])}
        rebuilt = []
        for n in new_names:
            src = by_name.get(n)
            if src is None:
                # A stage that was renamed keeps its original target_days.
                for o, r in RENAME.items():
                    if r == n:
                        src = next((v for k, v in by_name.items()
                                    if k.strip().lower() == o), None)
                        if src:
                            break
            rebuilt.append({"stage": n,
                            "target_days": (src or {}).get("target_days", 3),
                            "win_probability": (src or {}).get("win_probability")})
        e["stages"] = rebuilt
        flows[prod] = e
    ps["product_flows"] = flows
    tmp = PS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ps, fh, indent=2)
    os.replace(tmp, PS)

    print("\nmigrated %d product(s) (backup: %s)"
          % (len(plans), os.path.basename(PS + ".pre_spine")))
    print("Restart uvicorn, then confirm nothing is stranded:")
    print("  python scripts\\audit_deal_journey.py")
    print("  python scripts\\pilot_status.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    api = open(API, encoding="utf-8").read()
    if "CREDIT_SPINE" in api:
        print("ABORT: SP1 looks applied.")
        return 1
    for name, needle in (("validator", VALIDATOR_ANCHOR), ("gate", GATE_ANCHOR),
                         ("skip", SKIP_ANCHOR)):
        if api.count(needle) != 1:
            print("ABORT: the %s anchor matched %d times." % (name, api.count(needle)))
            return 1

    api = api.replace(VALIDATOR_ANCHOR, SPINE + VALIDATOR_ANCHOR, 1)
    api = api.replace(GATE_ANCHOR, GATE + GATE_ANCHOR, 1)
    api = api.replace(SKIP_ANCHOR, SKIP + SKIP_ANCHOR, 1)
    print("  ok  spine, closing-stage rule, non-branch skip")

    if "CREDIT_CLASS" not in SPINE or "_is_credit_product" not in SPINE:
        print("ABORT: the spine is not limited to lending products - a savings")
        print("       account would be forced through a credit committee.")
        return 1
    if "sorted(pos)" not in SPINE:
        print("ABORT: the check does not test ORDER, so it would either forbid")
        print("       extra stages or allow the spine out of sequence.")
        return 1
    if "_deal_is_branch_originated" not in SKIP:
        print("ABORT: the skip does not check whether the deal has a branch.")
        return 1
    if "Branch Credit Committee Review" not in SKIP:
        print("ABORT: the skip is not limited to the branch committee - a deal")
        print("       could jump an arbitrary stage.")
        return 1
    if "_i + 1" not in SKIP:
        print("ABORT: the skip is not forward-only.")
        return 1
    print("  ok  post-checks: credit only, order tested, skip is narrow")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s" % API)
    if not os.path.exists(MIG):
        open(MIG, "w", encoding="utf-8", newline="").write(MIGRATION)
        print("CREATED %s" % MIG)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("The spine is enforced on every product-flow SAVE from now on.")
    print("Existing flows are untouched until migrated - five lending products")
    print("and four deposit ones still need it:")
    print("  python scripts\\migrate_to_credit_spine.py")
    print("")
    print("Read the plan AND the live-deal counts before --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
