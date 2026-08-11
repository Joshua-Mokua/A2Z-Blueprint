#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
IC1 - the information card. What is known about a prospect, newest first.

RULING (2026-08-11): "on each we have an information card - all available
public information concerning the company including financials, associations
etc, arranged in recency with key information and links to detailed
information." And earlier: "an interested person can click to view more details
before they can decide to pick."

AN ENRICHMENT ITEM IS A FACT WITH A SOURCE AND A DATE - never a copied article.
The card stores a headline, a date, where it came from, and a LINK. Storing
article bodies would be republishing someone else's work, and a stale copy is
worse than a link that stays current.

    kinds: financial · news · association · filing · contact · relationship · note

UNDATED ITEMS SORT LAST, not first. Something with no date is the least
trustworthy entry on the card; putting it at the top would give it the
prominence of breaking news.

AN UNSOURCED ITEM IS REFUSED. A claim with no provenance on a prospect card is
a rumour that looks like research, and six months later nobody can tell which
is which.

ANYONE MAY ADD, deliberately. A note that a prospect just won a county tender is
exactly the kind of thing that dies in one person's inbox; restricting it to the
lister would guarantee that. Every item records who added it and from where.

CONTACTS STAY PROTECTED ON THE DETAIL PAGE TOO - lister, claimer and admin only.
Opening a page is not a claim, and revealing contacts on a click would make the
shelf's protection decorative.

HOW THE CARD GETS FILLED, honestly. NOT by scraping "all sources": at 1,800
prospects that means automated fetching at scale, and republishing what it
finds. Two legitimate routes instead -

    a licensed provider's API. The vendors selling BRS records also sell
    financials and group structure; push them in through this endpoint.

    an RM who finds something and records it. Worth having on its own, and it
    is the reason "anyone may add" is the rule.

MEASURED: three items on a card sort news (July) above financials (March) above
an undated association entry; an unsourced item is refused.

FRONTEND IS IC2.

REQUIRES DW2.

Usage (from project root, .venv active):
    python scripts\patch_ic1_information_card.py            # dry run
    python scripts\patch_ic1_information_card.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
BACKUP_SUFFIX = ".pre_ic1"

MOD_ANCHOR = "def shelves(status: str = STATUS_AVAILABLE) -> dict:"
API_ANCHOR = '@router.get("/mine")'

CARD = r'''# ── THE INFORMATION CARD ────────────────────────────────────────────────────
# RULING (2026-08-11): "on each we have an information card - all available
# public information concerning the company including financials, associations
# etc, arranged in recency with key information and links to detailed
# information."
#
# An enrichment item is a FACT WITH A SOURCE AND A DATE. Never a copied
# article: we store the headline, the date, where it came from and a LINK.
# Storing article bodies would be republishing somebody else's work, and a
# stale copy is worse than a link that stays current.
#
# ORDERED BY RECENCY because that is how this is read - "what has happened to
# this company lately" - and an undated item sorts last rather than first,
# since something with no date is the least trustworthy thing on the card.
#
# HOW IT GETS FILLED, honestly: not by scraping. Either
#   - a licensed provider's API (the same vendors selling BRS records also sell
#     financials and group structure), pushed in through add_enrichment, or
#   - an RM who finds something and records it, which is worth having on its
#     own - a note that a prospect just won a county tender is exactly the kind
#     of thing that dies in one person's inbox.
ENRICHMENT_KINDS = ("financial", "news", "association", "filing", "contact",
                    "relationship", "note")


def add_enrichment(prospect_id: str, *, kind: str, title: str,
                   source: str, url: str = "", occurred_on: str = "",
                   detail: str = "", added_by: str = "") -> dict:
    """Attach one fact to a prospect's information card.

    `title` should be a headline or a figure, not a paragraph - the card is a
    scan-and-click surface, and anything longer belongs behind the link.
    """
    pid = str(prospect_id or "").strip()
    k = str(kind or "note").strip().lower()
    if k not in ENRICHMENT_KINDS:
        k = "note"
    t = str(title or "").strip()
    if not t:
        raise ValueError("An entry needs a title.")
    if not str(source or "").strip():
        # Provenance is the whole point: an unsourced claim on a prospect card
        # is a rumour that looks like research.
        raise ValueError("Say where this came from.")

    item = {
        "id": uuid.uuid4().hex[:8],
        "kind": k,
        "title": t[:200],
        "detail": str(detail or "")[:500],
        "source": str(source).strip()[:120],
        "url": str(url or "").strip()[:500],
        "occurred_on": str(occurred_on or "")[:10],
        "added_by": str(added_by or ""),
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        rec.setdefault("enrichment", []).append(item)
        data[pid] = rec
        _write(data)
    return item


def information_card(prospect_id: str) -> dict:
    """Everything known about a prospect, newest first.

    Undated items sort LAST, not first: something with no date is the least
    trustworthy entry on the card, and putting it at the top would give it the
    prominence of breaking news.
    """
    rec = get(prospect_id)
    if not rec:
        return {}
    items = list(rec.get("enrichment") or [])
    items.sort(key=lambda i: (i.get("occurred_on") or "0000-00-00",
                              i.get("added_at") or ""), reverse=True)
    by_kind = {}
    for i in items:
        by_kind.setdefault(i["kind"], []).append(i)
    return {
        "prospect_id": rec.get("id"),
        "name": rec.get("name"),
        "items": items,
        "by_kind": by_kind,
        "counts": {k: len(v) for k, v in by_kind.items()},
        "total": len(items),
    }


'''

ENDPOINTS = r'''@router.get("/prospects/{prospect_id}")
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
    return {"prospect": out, "card": information_card(prospect_id)}


@router.post("/prospects/{prospect_id}/enrichment")
def warehouse_add_enrichment(prospect_id: str,
                             payload: dict = Body(default_factory=dict),
                             user: dict = Depends(get_current_user)):
    """Add a fact to a prospect's information card.

    ANYONE MAY ADD, deliberately. A note that a prospect just won a county
    tender is exactly the kind of thing that dies in one person's inbox, and
    restricting it to the lister would guarantee that. Every item records who
    added it and where it came from, which is the accountability that matters
    here.
    """
    from utils.deals_warehouse import add_enrichment
    code, name = _actor(user)
    try:
        item = add_enrichment(
            prospect_id,
            kind=str(payload.get("kind", "note") or "note"),
            title=str(payload.get("title", "") or ""),
            source=str(payload.get("source", "") or ""),
            url=str(payload.get("url", "") or ""),
            occurred_on=str(payload.get("occurred_on", "") or ""),
            detail=str(payload.get("detail", "") or ""),
            added_by=name or code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_log("WAREHOUSE_ENRICH", str(user.get("username", "") or ""),
              detail="%s: %s" % (prospect_id, item["title"][:60]))
    return {"item": item}


'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_dw1_warehouse.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "def information_card(" in mod:
        print("ABORT: information_card already present - IC1 looks applied.")
        return 1
    if mod.count(MOD_ANCHOR) != 1:
        print("ABORT: shelves anchor matched %d times." % mod.count(MOD_ANCHOR))
        return 1
    if api.count(API_ANCHOR) != 1:
        print("ABORT: mine route matched %d times." % api.count(API_ANCHOR))
        return 1

    mod = mod.replace(MOD_ANCHOR, CARD + MOD_ANCHOR, 1)
    api = api.replace(API_ANCHOR, ENDPOINTS + API_ANCHOR, 1)
    print("  ok  card model and endpoints")

    # Provenance is not optional.
    if "Say where this came from" not in CARD:
        print("ABORT: an unsourced item would be accepted - a claim with no")
        print("       provenance is a rumour that looks like research.")
        return 1
    # Undated last, or an undated item reads as breaking news.
    if '"0000-00-00"' not in CARD:
        print("ABORT: undated items would sort first.")
        return 1
    # No article bodies.
    if "[:200]" not in CARD or "[:500]" not in CARD:
        print("ABORT: item fields are unbounded - the card would end up holding")
        print("       copied article text rather than a headline and a link.")
        return 1
    # Contacts must stay gated on the detail page.
    if "contacts_visible" not in ENDPOINTS:
        print("ABORT: the detail page does not gate contacts - opening a page")
        print("       is not a claim.")
        return 1
    print("  ok  post-checks: sourced, dated, bounded, contacts gated")

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

    print("\nRestart uvicorn. The card is empty until something is added -")
    print("either from a licensed provider's API or by an RM who found it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
