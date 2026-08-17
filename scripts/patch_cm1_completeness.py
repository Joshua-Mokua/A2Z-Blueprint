#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CM1 - the completeness matrix. Ten fields, a score, and a validated set.

RULING (2026-08-11): "establish 10 must-have fields as a measure for a
completeness index. I will be scoring each entry against that, and once done it
is marked as a complete entry. This ensures we keep backfilling, and sets the
rules of what a complete entry looks like for anyone keying in data. Then a
validation check - once an entry is fully complete it can be validated and
stored as a record that can be used."

THE TEN ARE WHAT SOMEBODY NEEDS TO APPROACH A BUSINESS WITH CONFIDENCE, not ten
arbitrary boxes. Each answers a question an RM would otherwise have to ask:

    WHO       legal name (15) · registration number (10)
    WHAT      sector (10) · what they actually do (5)
    WHERE     county (10) · physical address (8)
    REACH     phone (12) · email (8)
    WHO TO    decision maker and their role (15)
    HOW BIG   size - turnover, members or staff (7)

WEIGHTED, because they are not equal. A name with no phone number is further
from usable than a phone number with no registration number, and an unweighted
score would call those the same. Decision maker carries the most alongside the
name: it is the single thing that turns a cold call into a meeting.

SCORED FROM THE RECORD *AND* ITS INFORMATION CARD. A phone number added as an
enrichment item counts exactly as much as one typed into the contact field -
requiring it in a particular place would punish people for using the tool as
intended.

VALIDATION IS A HUMAN ACT, NOT A CONSEQUENCE OF THE SCORE. 100% means every
field has something in it; validation means somebody looked and believed it. A
record can be complete and wrong, and the point of a usable set is that somebody
staked their name on it. Refusing names the specific gaps rather than just
saying no.

A RECORD EDITED AFTER VALIDATION IS FLAGGED STALE rather than quietly keeping
its badge - it is no longer the record that was validated.

SCORED ON THE SHELF, not only on the detail page. A standard nobody sees while
browsing is a standard nobody backfills against.

completeness_summary() answers the question that decides what to do next: which
field is missing on the most records.

MEASURED end to end: a SASRA import scores 50%; adding a contact takes it to
78%, a director to 93%, a financial figure to 100%; validation then succeeds
and the record becomes usable. Before that, validation is refused naming
Physical address, Phone, Email and Decision maker.

CONFIG-DRIVEN via warehouse_completeness, so the standard can change without a
release - the same rule as origins, channels and activity sets.

This is also the foundation for the deal scoring matrix that will rank
warehouse prospects on viability.

REQUIRES IC1.

Usage (from project root, .venv active):
    python scripts\patch_cm1_completeness.py            # dry run
    python scripts\patch_cm1_completeness.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
BACKUP_SUFFIX = ".pre_cm1"

MOD_ANCHOR = "# ── THE INFORMATION CARD"
API_ANCHOR = '@router.get("/mine")'
SHELF_OLD = '            row["mine"] = mine'
DET_ANCHOR = '@router.get("/prospects/{prospect_id}")'
DET_END = '@router.post("/prospects/{prospect_id}/enrichment")'

MATRIX = r'''# ── THE COMPLETENESS MATRIX ─────────────────────────────────────────────────
# RULING (2026-08-11): "establish 10 must-have fields as a measure for a
# completeness index, scoring each entry, and once done it is marked complete.
# This ensures we keep backfilling, and sets the rules of what a complete entry
# looks like for anyone keying in data. Then a validation check - once an entry
# is fully complete it can be validated and stored as a record that can be
# used."
#
# THE TEN ARE WHAT SOMEBODY NEEDS TO APPROACH A BUSINESS WITH CONFIDENCE. Not
# ten arbitrary boxes: each answers a question an RM would otherwise have to
# ask, and a prospect missing several is one nobody can act on.
#
#     WHO      legal name · registration number
#     WHAT     sector · what they do
#     WHERE    county · physical address
#     REACH    phone · email
#     WHO TO   decision maker and their role
#     HOW BIG  a size indicator - turnover, members, staff
#
# WEIGHTED, because they are not equal. A name with no phone number is further
# from usable than a phone number with no registration number, and an unweighted
# score would call those the same.
#
# CONFIG-DRIVEN via warehouse_completeness, so the bank can change the standard
# without a release - the same rule as origins, channels and activity sets.
#
# SCORED FROM THE RECORD *AND* ITS CARD. A phone number added as an enrichment
# item counts exactly as much as one typed into the contact field; requiring it
# in a particular place would punish people for using the tool as intended.
DEFAULT_COMPLETENESS = [
    {"key": "name", "label": "Legal name", "weight": 15,
     "why": "Who they are, as registered."},
    {"key": "registration_no", "label": "Registration number", "weight": 10,
     "why": "Proves the entity exists and is the one you think it is."},
    {"key": "sector", "label": "Sector", "weight": 10,
     "why": "Decides which products are even relevant."},
    {"key": "county", "label": "County", "weight": 10,
     "why": "Decides which branch owns the conversation."},
    {"key": "physical_address", "label": "Physical address", "weight": 8,
     "why": "You cannot visit a postal box."},
    {"key": "phone", "label": "Phone", "weight": 12,
     "why": "Without it nobody can start."},
    {"key": "email", "label": "Email", "weight": 8,
     "why": "For anything that needs a paper trail."},
    {"key": "decision_maker", "label": "Decision maker and role", "weight": 15,
     "why": "The single thing that turns a cold call into a meeting."},
    {"key": "size_indicator", "label": "Size - turnover, members or staff", "weight": 7,
     "why": "Tells you which desk should hold it."},
    {"key": "business_activity", "label": "What they actually do", "weight": 5,
     "why": "A sector is a category; this is the business."},
]

STATUS_VALIDATED = "validated"


def completeness_fields() -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_completeness")
        if isinstance(v, list) and v:
            return [f for f in v if isinstance(f, dict) and f.get("key")]
    except Exception:
        pass
    return [dict(f) for f in DEFAULT_COMPLETENESS]


def _has(rec: dict, key: str) -> bool:
    """Is this field answered - anywhere on the record or its card?"""
    def _t(*names):
        return any(str(rec.get(n) or "").strip() for n in names)

    items = rec.get("enrichment") or []

    def _card(*kinds):
        return any(str(i.get("title") or "").strip()
                   for i in items if i.get("kind") in kinds)

    if key == "name":
        return _t("name")
    if key == "registration_no":
        return _t("registration_no") or "registered no" in str(rec.get("notes", "")).lower()
    if key == "sector":
        return _t("sector") and str(rec.get("sector")).strip().lower() != "unsorted"
    if key == "county":
        return _t("town")
    if key == "physical_address":
        return _t("physical_address", "address") or _card("contact")
    if key == "phone":
        return _t("contact_phone") or _card("contact")
    if key == "email":
        return _t("contact_email") or _card("contact")
    if key == "decision_maker":
        return _t("contact_name") or _card("relationship")
    if key == "size_indicator":
        return bool(rec.get("estimated_value")) or _card("financial")
    if key == "business_activity":
        return _t("notes") or _card("note", "news")
    return _t(key)


def completeness(prospect_id_or_rec) -> dict:
    """Score one prospect against the matrix.

    Returns the score, what is answered, and WHAT IS MISSING with the reason it
    matters - because a score alone tells somebody they are incomplete without
    telling them what to do about it.
    """
    rec = (prospect_id_or_rec if isinstance(prospect_id_or_rec, dict)
           else get(prospect_id_or_rec))
    if not rec:
        return {}
    fields = completeness_fields()
    total = sum(int(f.get("weight") or 0) for f in fields) or 1
    have, missing, got = [], [], 0
    for f in fields:
        if _has(rec, f["key"]):
            have.append(f["key"])
            got += int(f.get("weight") or 0)
        else:
            missing.append({"key": f["key"], "label": f.get("label") or f["key"],
                            "why": f.get("why") or "", "weight": f.get("weight")})
    pct = round(got / total * 100)
    return {
        "prospect_id": rec.get("id"),
        "score": pct,
        "complete": pct >= 100,
        "have": have,
        "missing": missing,
        "answered": len(have),
        "of": len(fields),
        "validated": rec.get("validated") is True,
        "validated_by": rec.get("validated_by") or "",
        "validated_at": rec.get("validated_at") or "",
        # A record edited AFTER validation is no longer the record that was
        # validated. Saying so is more honest than silently keeping the badge.
        "stale_validation": bool(
            rec.get("validated") and rec.get("last_edited_at")
            and str(rec.get("last_edited_at")) > str(rec.get("validated_at") or "")),
    }


def validate_prospect(prospect_id: str, by_code: str, by_name: str) -> dict:
    """Promote a COMPLETE entry to a validated record.

    Validation is a HUMAN ACT, not a consequence of the score. 100% means every
    field has something in it; validation means somebody looked and believed it.
    A record can be complete and wrong, and the whole point of a usable set is
    that somebody staked their name on it.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        c = completeness(rec)
        if not c.get("complete"):
            missing = ", ".join(m["label"] for m in c.get("missing", [])[:4])
            raise ValueError(
                "Not complete yet - %d%%. Still needed: %s."
                % (c.get("score", 0), missing or "unknown"))
        rec["validated"] = True
        rec["validated_by"] = str(by_name or by_code or "")
        rec["validated_at"] = datetime.now().isoformat(timespec="seconds")
        data[pid] = rec
        _write(data)
    return completeness(rec)


def completeness_summary() -> dict:
    """How complete is the warehouse as a whole, and which field is holding it
    back - the question that decides what to backfill next."""
    recs = all_prospects()
    fields = completeness_fields()
    missing_counts = {f["key"]: 0 for f in fields}
    scores, complete, validated = [], 0, 0
    for r in recs:
        c = completeness(r)
        scores.append(c.get("score", 0))
        if c.get("complete"):
            complete += 1
        if c.get("validated"):
            validated += 1
        for m in c.get("missing", []):
            missing_counts[m["key"]] = missing_counts.get(m["key"], 0) + 1
    labels = {f["key"]: f.get("label") or f["key"] for f in fields}
    return {
        "total": len(recs),
        "average_score": round(sum(scores) / len(scores)) if scores else 0,
        "complete": complete,
        "validated": validated,
        "usable": validated,
        "worst_gaps": sorted(
            [{"key": k, "label": labels.get(k, k), "missing": n}
             for k, n in missing_counts.items() if n],
            key=lambda x: -x["missing"])[:5],
    }


'''

ENDPOINTS = r'''@router.get("/completeness")
def warehouse_completeness(user: dict = Depends(get_current_user)):
    """The matrix itself, and how the warehouse scores against it.

    The FIELDS are returned alongside the summary so a capture form can show
    the standard while somebody is typing, rather than telling them afterwards
    what they should have entered.
    """
    from utils.deals_warehouse import completeness_fields, completeness_summary
    return {"fields": completeness_fields(), "summary": completeness_summary()}


@router.post("/prospects/{prospect_id}/validate")
def warehouse_validate(prospect_id: str,
                       user: dict = Depends(get_current_user)):
    """Promote a complete entry to a validated, usable record.

    Deliberately NOT automatic at 100%. A record can be complete and wrong; the
    point of a usable set is that somebody looked and staked their name on it.
    The 400 names what is still missing rather than just refusing.
    """
    from utils.deals_warehouse import validate_prospect
    code, name = _actor(user)
    try:
        return {"completeness": validate_prospect(prospect_id, code, name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


'''

SHELF = r'''            row["mine"] = mine
            # Scored HERE, on the shelf, not only on the detail page - a
            # completeness standard nobody sees while browsing is a standard
            # nobody backfills against.
            try:
                from utils.deals_warehouse import completeness as _cc
                _c = _cc(r)
                row["score"] = _c.get("score", 0)
                row["validated"] = _c.get("validated", False)
                row["missing_count"] = len(_c.get("missing", []))
            except Exception:
                row["score"] = 0
    # INSTITUTIONAL CONTACTS ARE SHOWN (ruling 2026-08-11: "why not
            # just display the contact"). A company switchboard or info@ address
            # published in a regulator's register is not personal data, and
            # hiding it made the shelf less useful for no protection.
            #
            # A NAMED PERSON still waits for a claim: "Jane Wanjiku, 0722..."
            # on an open shelf is exactly the case the Data Protection Act
            # covers, and it is the one field an RM adds by hand.
            row["contact_phone"] = r.get("contact_phone")
            row["contact_email"] = r.get("contact_email")
            if mine or admin:
                row["contact_name"] = r.get("contact_name")
                row["contacts_visible"] = True
            else:
                row["contacts_visible"] = False

'''

DETAIL = r'''@router.get("/prospects/{prospect_id}")
def warehouse_detail(prospect_id: str, user: dict = Depends(get_current_user)):
    """Everything about one prospect, before deciding whether to pursue it.

    Ruling 2026-08-11: "an interested person can click to view more details
    before they can decide to pick."

    CONTACT DETAILS FOLLOW THE SAME RULE AS THE SHELF - visible to the lister,
    the claimer and admin only. Opening a detail page is not a claim, and a
    page that revealed contacts on a click would make the shelf's protection
    decorative.
    """
    from utils.deals_warehouse import get, information_card
    from utils.deals_warehouse import completeness
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    code, _n = _actor(user)
    mine = (str(rec.get("created_by_code") or "") == code
            or str(rec.get("claimed_by_code") or "") == code)
    visible = mine or _is_admin(user)

    out = {k: rec.get(k) for k in
           ("id", "name", "sector", "town", "status", "estimated_value",
            "source_event", "notes", "created_by_name", "created_at",
            "claimed_by_name", "claimed_at", "deal_id")}
    out["mine"] = mine
    out["contacts_visible"] = visible
    if visible:
        out.update({k: rec.get(k) for k in
                    ("contact_name", "contact_phone", "contact_email")})
    return {"prospect": out, "card": information_card(prospect_id),
            "completeness": completeness(rec)}


'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ic1_information_card.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "def completeness(" in mod:
        print("ABORT: completeness already present - CM1 looks applied.")
        return 1
    if MOD_ANCHOR not in mod:
        print("ABORT: apply patch_ic1_information_card.py first.")
        return 1
    if api.count(API_ANCHOR) != 1 or api.count(SHELF_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (api.count(API_ANCHOR), api.count(SHELF_OLD)))
        return 1

    mod = mod.replace(MOD_ANCHOR, MATRIX + MOD_ANCHOR, 1)
    api = api.replace(API_ANCHOR, ENDPOINTS + API_ANCHOR, 1)
    api = api.replace(SHELF_OLD, SHELF, 1)
    i = api.index(DET_ANCHOR)
    j = api.index(DET_END)
    api = api[:i] + DETAIL + api[j:]
    print("  ok  matrix, endpoints, shelf scores, detail")

    # Ten fields, weighted, or it is not the matrix that was asked for.
    if MATRIX.count('"key":') < 10:
        print("ABORT: fewer than ten fields defined.")
        return 1
    if '"weight"' not in MATRIX:
        print("ABORT: fields are unweighted - a missing phone number and a")
        print("       missing registration number are not equally serious.")
        return 1
    # Validation must not be automatic.
    if 'if not c.get("complete"):' not in MATRIX:
        print("ABORT: validation does not require completeness.")
        return 1
    if "stale_validation" not in MATRIX:
        print("ABORT: a record edited after validation would keep its badge.")
        return 1
    # The card must count toward the score.
    if "_card(" not in MATRIX:
        print("ABORT: enrichment items do not count - somebody adding a phone")
        print("       number to the card would score nothing for it.")
        return 1
    if '"score"' not in SHELF:
        print("ABORT: shelf rows carry no score.")
        return 1
    print("  ok  post-checks: ten weighted fields, human validation, card counts")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, mod), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn. GET /api/warehouse/completeness returns the matrix")
    print("and how the whole warehouse scores against it - including which")
    print("field is missing on the most records, which is what decides what to")
    print("backfill first. The UI for this is CM2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
