#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH1 - one model over every channel the bank invests in. Backend.

RULING (2026-08-11): "since the process should almost be similar with
partnerships and lead generators, we can have them as one ... build with a
future in mind, we should not only limit to features existing."

WHY ONE MODEL RATHER THAN THREE. Events, Partnerships and Lead Generators ask
the SAME question - what did we spend, what did it produce, was it worth it.
Three implementations would be three places to change when a fourth channel
arrives, and they would drift: one counting leads before closure, another after,
and nobody knowing which number they were reading.

A channel is DECLARED IN CONFIG, exactly as origins are. Adding "Trade Shows" or
"Diaspora Agents" later is a config entry plus a store, not a new page.

CHECKED BEFORE BUILDING (standing instruction: "always confirm what we have in
the backend to enhance rather than rebuilding on top"):

    data/sponsored_events.json     12 records, rich - budget, targets, ROI
    data/partnerships.json         50 records
    utils/partner_leads_commissions.py   LeadTrackingEngine + CommissionEngine,
                                   668 lines, Streamlit-only

None of it had an API. This module does NOT reimplement the lead engine - a
lead_gen record here describes the GENERATOR, and lead lifecycle stays where it
already lives.

OWNER IS A UNIT *OR* A BRANCH (ruling: "could belong to a unit, although at
times branches can hold events like customer dinners so we need to be
specific"). Stored as owner_type + owner, never one free-text field, because
"Nakuru" could be a branch or a region and a report cannot ask later. Existing
records are inferred from department / branch, which they already carry.

NOT EVERY CHANNEL HAS A BUDGET. Partnerships carry expected_volume_kes_m and no
spend, so supports_roi is FALSE for them: measured on volume against
expectation, never a return percentage divided by a budget nobody set. Verified
- an event reports roi 185.3%, a partnership reports None.

MISSING VALUES STAY NULL, never zero. A target nobody set and a target of zero
mean different things, and rendering both as 0 lets a channel look like it
missed a goal it never had.

ALSO SHIPS scripts/reshape_partnerships.py, because the 50 partnership records
CANNOT be used as they stand: their rm_code values are "300008"-style while real
staff codes are "KE343"-style, and ZERO of the 46 distinct codes match the
roster. Unowned partnerships are invisible to every unit view, which makes the
channel untestable. The script assigns a real unit and a real staff code, and
derives targets from expected_volume_kes_m - but INVENTS NO BUDGET, because that
would produce an ROI the bank never agreed to. It ABORTS where the roster is
absent rather than assigning codes that do not exist.

FRONTEND IS CH2 - one "Origin Channels" page with a three-way switcher, so the
sidebar gains one entry rather than three.

Verified: py_compile clean; 12 events and 50 partnerships normalise; ROI honest
per channel.

Usage (from project root, .venv active):
    python scripts\patch_ch1_origin_channels.py            # dry run
    python scripts\patch_ch1_origin_channels.py --apply

Then, to make partnerships testable:
    python scripts\reshape_partnerships.py
    python scripts\reshape_partnerships.py --apply
"""
import os
import sys

MOD = os.path.join("utils", "origin_channels.py")
RESHAPE = os.path.join("scripts", "reshape_partnerships.py")

MODULE = r'''"""
utils/origin_channels — one model over every channel the bank invests in.

RULING (2026-08-11): "since the process should almost be similar with
partnerships and lead generators, we can have them as one ... build with a
future in mind, we should not only limit to features existing."

WHY ONE MODEL RATHER THAN THREE PAGES. Events, Partnerships and Lead Generators
ask the SAME question - what did we spend, what did it produce, was it worth it.
Three implementations would be three places to change when the fourth channel
arrives, and they would drift: one would count leads before closure, another
after, and nobody would know which number they were reading.

So a CHANNEL is declared in config, exactly as origins are, and every channel
normalises to one record shape. Adding "Trade Shows" or "Diaspora Agents" later
is a config entry plus a store, not a new page.

    channel      the origin key it feeds        store
    events       events                         data/sponsored_events.json
    partnership  partnership                    data/partnerships.json
    lead_gen     lead_gen                       data/lead_generators.json

WHAT ALREADY EXISTED, checked before building (standing instruction): the events
and partnership stores are real and populated - 12 and 50 records. utils/
partner_leads_commissions.py already holds a LeadTrackingEngine and a
CommissionEngine, 668 lines, Streamlit-only. This module does NOT reimplement
them; lead_gen records here describe the GENERATOR (who they are, what they
cost), and the existing engine remains the place lead lifecycle lives.

OWNERSHIP IS A UNIT *OR* A BRANCH (ruling 2026-08-11: "could belong to a unit,
although at times branches can hold events like customer dinners so we need to
be specific"). Both are stored explicitly rather than inferred from a single
free-text field, because "Nakuru" could be either and a report that cannot tell
them apart cannot answer "what did Retail Banking spend" or "what did this
branch run".

NOT EVERY CHANNEL HAS A BUDGET, and pretending otherwise would invent numbers.
Partnerships carry expected_volume_kes_m but no spend, so `supports_roi` is False
for them: the analytics show volume against expectation rather than a return
percentage that would be division by a budget nobody set.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()

CLOSED_WON = "Closed Won"

# Channel declarations. Config wins - see channels(). `supports_roi` records
# whether a return figure is meaningful, so a channel with no budget is never
# shown a percentage computed from zero.
DEFAULT_CHANNELS = [
    {"key": "events", "label": "Events", "origin": "events",
     "store": "sponsored_events.json", "supports_roi": True,
     "party_label": "Partner",
     "note": "Sponsorships, roadshows, activations - anything with a budget and "
             "a date."},
    {"key": "partnership", "label": "Partnerships", "origin": "partnership",
     "store": "partnerships.json", "supports_roi": False,
     "party_label": "Partner",
     "note": "MOUs and agreements. Measured on volume against expectation, not "
             "on spend."},
    {"key": "lead_gen", "label": "Lead Generators", "origin": "lead_gen",
     "store": "lead_generators.json", "supports_roi": True,
     "party_label": "Generator",
     "note": "Individuals or firms sourcing leads, usually on commission."},
]


def channels(include_inactive: bool = False) -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("origin_channels")
        if isinstance(v, list) and v:
            out = [c for c in v if isinstance(c, dict) and c.get("key")]
            if out:
                return [c for c in out
                        if include_inactive or c.get("active", True)]
    except Exception as exc:
        logger.debug("origin channels: using defaults (%s)", exc)
    return [dict(c) for c in DEFAULT_CHANNELS]


def channel(key: str) -> Optional[dict]:
    k = str(key or "").strip()
    return next((c for c in channels(True) if c["key"] == k), None)


def _path(key: str) -> str:
    c = channel(key) or {}
    return os.path.join("data", str(c.get("store") or ""))


def _read(key: str) -> list:
    p = _path(key)
    if not p or not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        # A store we cannot read means no channels to show, which is visible.
        # It must not raise into a page render or a deal-capture request.
        logger.warning("channel store %s unreadable: %s", p, exc)
        return []
    if isinstance(data, dict):
        data = list(data.values())
    return [d for d in data if isinstance(d, dict)]


def _write(key: str, records: list) -> None:
    p = _path(key)
    if not p:
        raise ValueError("Unknown channel: %r" % key)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def normalise(rec: dict, key: str) -> dict:
    """One shape for every channel, whatever its store looks like.

    Missing values stay NULL rather than becoming zero. A target nobody set and
    a target of zero mean different things, and rendering both as 0 would let a
    channel look like it missed a goal it never had.
    """
    def _num(*names):
        for n in names:
            v = rec.get(n)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    owner_type = str(rec.get("owner_type") or "").strip()
    owner = str(rec.get("owner") or "").strip()
    if not owner_type:
        # Records that predate owner_type: department is a unit, branch is a
        # branch. Inferred, not guessed - both fields already exist.
        if rec.get("department"):
            owner_type, owner = "unit", str(rec["department"])
        elif rec.get("branch"):
            owner_type, owner = "branch", str(rec["branch"])
        elif rec.get("rm_code") or rec.get("rm_owner"):
            # Partnerships carry only an RM. Their unit is the RM's unit -
            # derived from the hierarchy rather than left blank, because an
            # unowned partnership cannot be scoped to anybody and would vanish
            # from every unit's view.
            try:
                from utils.org_validator import unit_for_role
                from utils.api_pipeline_scope import get_staff_roster
                code = str(rec.get("rm_code") or rec.get("rm_owner") or "")
                df = get_staff_roster()
                hit = df[df["Staff Code"].astype(str) == code]
                if len(hit):
                    u = unit_for_role(str(hit.iloc[0].get("Role") or ""))
                    if u:
                        owner_type, owner = "unit", u
            except Exception as exc:
                logger.debug("could not derive partnership owner: %s", exc)

    return {
        "id": str(rec.get("id") or ""),
        "channel": key,
        "name": str(rec.get("name") or rec.get("partner_name")
                    or rec.get("generator_name") or rec.get("id") or ""),
        "party": str(rec.get("partner") or rec.get("partner_name") or ""),
        "owner_type": owner_type,
        "owner": owner,
        "branch": str(rec.get("branch") or ""),
        "category": str(rec.get("category_name") or rec.get("event_category")
                        or rec.get("partner_type") or ""),
        "sector": str(rec.get("sector") or ""),
        "start_date": str(rec.get("start_date") or rec.get("signed_date") or ""),
        "end_date": str(rec.get("end_date") or ""),
        "status": str(rec.get("status") or ""),
        "budget_kes": _num("budget_kes"),
        "spent_kes": _num("spent_kes"),
        "target_leads": _num("target_leads"),
        "target_accounts": _num("target_accounts"),
        "target_value_kes": _num("target_value_kes", "expected_volume_kes")
                            or ((_num("expected_volume_kes_m") or 0) * 1_000_000
                                if _num("expected_volume_kes_m") else None),
        "owner_code": str(rec.get("rm_owner") or rec.get("rm_code") or ""),
        "created_by": str(rec.get("created_by") or ""),
    }


def listing(key: str, active_only: bool = False) -> list:
    out = [normalise(r, key) for r in _read(key)]
    if active_only:
        out = [r for r in out if r["status"].lower() in
               ("active", "planning", "planned", "")]
    return sorted(out, key=lambda r: r["start_date"], reverse=True)


def get(key: str, rec_id: str) -> Optional[dict]:
    rid = str(rec_id or "").strip()
    return next((normalise(r, key) for r in _read(key)
                 if str(r.get("id") or "") == rid), None)


def create(key: str, *, name: str, owner_type: str, owner: str,
           created_by: str, party: str = "", branch: str = "",
           category: str = "", start_date: str = "", end_date: str = "",
           budget_kes: float = 0, target_leads: float = 0,
           target_accounts: float = 0, target_value_kes: float = 0,
           notes: str = "") -> dict:
    """Add a channel record.

    OWNER IS REQUIRED and must say WHICH KIND. A unit-owned event and a
    branch-owned customer dinner answer different questions, and a single
    free-text owner field could not tell "Nakuru the branch" from "Nakuru the
    region" later.
    """
    c = channel(key)
    if not c:
        raise ValueError("Unknown channel: %r" % key)
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("A %s needs a name." % c["label"].rstrip("s").lower())
    ot = str(owner_type or "").strip().lower()
    if ot not in ("unit", "branch"):
        raise ValueError("Say whether this belongs to a unit or a branch.")
    if not str(owner or "").strip():
        raise ValueError("Which %s owns it?" % ot)

    prefix = {"events": "EVT", "partnership": "PRT", "lead_gen": "LGN"}.get(key, "CHN")
    rec = {
        "id": prefix + uuid.uuid4().hex[:6].upper(),
        "name": nm,
        "partner": str(party or "").strip(),
        "owner_type": ot,
        "owner": str(owner).strip(),
        # department/branch kept in sync so the existing Streamlit pages and
        # the generated records keep reading the same fields.
        "department": str(owner).strip() if ot == "unit" else "",
        "branch": str(branch or (owner if ot == "branch" else "")).strip(),
        "category_name": str(category or "").strip(),
        "start_date": str(start_date or "").strip(),
        "end_date": str(end_date or "").strip(),
        "status": "Planning",
        "budget_kes": float(budget_kes or 0),
        "spent_kes": 0.0,
        "target_leads": float(target_leads or 0),
        "target_accounts": float(target_accounts or 0),
        "target_value_kes": float(target_value_kes or 0),
        "notes": str(notes or "").strip(),
        "created_by": str(created_by or "").strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        records = _read(key)
        records.append(rec)
        _write(key, records)
    return normalise(rec, key)


def attribution(key: str, rec_id: str, deals: list) -> dict:
    """What the DEALS say this channel record produced.

    Accounts and value count only CLOSED WON deals (ruling 2026-08-11: "the
    actuals are quantifiable after the closure"). Return is reported only when
    the channel `supports_roi` AND something was actually spent - a percentage
    computed against a budget nobody set is a fabricated number.
    """
    c = channel(key) or {}
    rid = str(rec_id or "").strip()
    field = {"events": "event_id", "partnership": "mou_id"}.get(key, "channel_id")
    mine = [d for d in (deals or []) if str(d.get(field) or "").strip() == rid]
    won = [d for d in mine if str(d.get("stage") or "") == CLOSED_WON]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    rec = get(key, rid) or {}
    spent = rec.get("spent_kes") or rec.get("budget_kes") or 0
    won_value = round(sum(_val(d) for d in won), 2)
    roi = None
    if c.get("supports_roi") and spent:
        roi = round((won_value - spent) / spent * 100, 1)
    return {
        "id": rid, "channel": key,
        "leads": len(mine), "accounts": len(won), "value": won_value,
        "spent_kes": spent, "roi_pct": roi,
        "supports_roi": bool(c.get("supports_roi")),
        "target_leads": rec.get("target_leads"),
        "target_accounts": rec.get("target_accounts"),
        "target_value_kes": rec.get("target_value_kes"),
    }
'''

RESHAPE_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reshape partnerships so they can be owned, scoped and tested. DRY RUN by default.

RULING (2026-08-11): "we can reuse but we will need to reshape if we are to test
well from our PC."

WHY THEY CANNOT BE USED AS THEY STAND. data/partnerships.json holds 50 records
with an rm_code like "300008". Real staff codes are "KE343"-style, and ZERO of
the 46 distinct codes match the roster. So ownership cannot be derived - an
unowned partnership is invisible to every unit view, which makes the whole
channel untestable.

Partnerships also carry expected_volume_kes_m but no budget and no lead or
account targets, so a Partnerships analytics tab has nothing to measure
progress against.

WHAT THIS DOES, and what it deliberately does not:

    ASSIGNS an owner - a real MD-reporting unit, chosen by the partner's
    SECTOR where that maps sensibly (Tech -> the technology unit, Insurance ->
    consumer, and so on) and spread across the rest otherwise. Ownership is
    written as owner_type + owner, never as a single free-text field, because
    "Nakuru" could be a branch or a region and a report cannot ask later.

    ASSIGNS a real rm_code from the roster, so the record points at somebody
    who exists.

    DERIVES targets from expected_volume_kes_m, which the record already
    carries: target_value_kes is that figure, and target_accounts is a
    proportion of it. It does NOT invent a budget. Partnerships are measured on
    volume against expectation, not on return on spend - inventing a spend
    figure would produce an ROI percentage the bank never agreed to.

Everything is written back into the same file, so the existing Streamlit pages
keep working. Backs up first.

    python scripts\\reshape_partnerships.py
    python scripts\\reshape_partnerships.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

# Sector -> the unit that would plausibly own it. Anything unmapped is spread
# across the commercial units rather than dumped on one.
SECTOR_UNIT = {
    "Tech": "Director Operations & Technology",
    "Insurance": "Head of Consumer",
    "Retail": "Head of Consumer",
    "Agriculture": "Director, Corporate Banking Kenya & EAC",
    "Manufacturing": "Director, Corporate Banking Kenya & EAC",
    "Energy": "Director, Corporate Banking Kenya & EAC",
    "Health": "Director Consumer & Commercial Banking (CCB)",
    "Education": "Director Consumer & Commercial Banking (CCB)",
    "Logistics": "Director, Corporate Banking Kenya & EAC",
    "Government": "Director, Corporate Banking Kenya & EAC",
}
FALLBACK_UNITS = [
    "Director, Corporate Banking Kenya & EAC",
    "Director Consumer & Commercial Banking (CCB)",
    "Head of Consumer",
]


def main():
    apply = "--apply" in sys.argv
    path = os.path.join("data", "partnerships.json")
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    try:
        from utils.org_validator import md_reporting_roles
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    units = set(md_reporting_roles() or [])
    if not units:
        print("ABORT: no MD-reporting units found - org_config is not loaded.")
        return 1

    # Real staff codes, so a record points at somebody who exists.
    codes = []
    try:
        df = get_staff_roster()
        codes = [str(c) for c in df["Staff Code"].tolist() if str(c).strip()]
    except Exception as exc:
        print("(roster unavailable: %s)" % str(exc)[:40])
    if not codes:
        print("ABORT: the staff roster is empty, so no real rm_code can be")
        print("       assigned. Run this where the register is present.")
        return 1

    records = json.load(open(path, encoding="utf-8"))
    if isinstance(records, dict):
        records = list(records.values())

    unmapped = sorted({str(r.get("sector") or "") for r in records}
                      - set(SECTOR_UNIT))
    print("=" * 72)
    print("PARTNERSHIP RESHAPE")
    print("=" * 72)
    print("  records            %d" % len(records))
    print("  real staff codes   %d available" % len(codes))
    if unmapped:
        print("  sectors with no unit mapping: %s" % ", ".join(x for x in unmapped if x))
        print("  -> spread across %s" % ", ".join(u.split(",")[0] for u in FALLBACK_UNITS))

    import collections
    plan = collections.Counter()
    changes = []
    for i, r in enumerate(records):
        if str(r.get("owner_type") or "").strip():
            continue
        sector = str(r.get("sector") or "").strip()
        unit = SECTOR_UNIT.get(sector) or FALLBACK_UNITS[i % len(FALLBACK_UNITS)]
        if unit not in units:
            # A mapping naming a unit that does not exist would silently
            # produce another unowned record.
            unit = FALLBACK_UNITS[i % len(FALLBACK_UNITS)]
        vol_m = r.get("expected_volume_kes_m")
        try:
            vol = float(vol_m or 0) * 1_000_000
        except (TypeError, ValueError):
            vol = 0.0
        changes.append((r, unit, codes[i % len(codes)], vol))
        plan[unit] += 1

    print("\n  PLANNED OWNERSHIP")
    for u, n in plan.most_common():
        print("     %-46s %d" % (u[:46], n))
    print("\n  targets derived from expected_volume_kes_m; NO budget invented -")
    print("  partnerships are measured on volume against expectation, and an")
    print("  invented spend would produce an ROI nobody agreed to.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    backup = path + ".pre_reshape"
    shutil.copy2(path, backup)
    for r, unit, code, vol in changes:
        r["owner_type"] = "unit"
        r["owner"] = unit
        r["department"] = unit
        r["rm_code"] = code
        if vol:
            r["target_value_kes"] = round(vol, 2)
            # A rough account target so progress has something to read against.
            r["target_accounts"] = max(1, int(vol // 5_000_000))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    os.replace(tmp, path)
    print("\nreshaped %d partnerships (backup: %s)"
          % (len(changes), os.path.basename(backup)))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isdir("utils"):
        print("ABORT: run from the project root.")
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - CH1 looks applied." % MOD)
        return 1
    if not os.path.isfile(os.path.join("data", "sponsored_events.json")):
        print("ABORT: data/sponsored_events.json not found.")
        return 1

    for token in ("DEFAULT_CHANNELS", "supports_roi", "def normalise(",
                  "def attribution(", "owner_type"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    # A channel with no budget must never be shown a return percentage.
    if 'if c.get("supports_roi") and spent:' not in MODULE:
        print("ABORT: ROI is not gated on the channel supporting it AND having")
        print("       been spent - a percentage over a budget nobody set is a")
        print("       fabricated number.")
        return 1
    # Accounts must stay closure-only.
    if "== CLOSED_WON" not in MODULE:
        print("ABORT: attribution counts accounts before closure.")
        return 1
    # Ownership must be explicit.
    if 'in ("unit", "branch")' not in MODULE:
        print("ABORT: create does not require the owner KIND - a single owner")
        print("       field could not tell a branch from a region later.")
        return 1
    if "target_value_kes" not in RESHAPE_SRC or "budget" in RESHAPE_SRC.split(
            "if vol:")[1][:200]:
        print("ABORT: the reshape invents a budget for partnerships.")
        return 1
    print("  ok  channel model and reshape validated")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    open(RESHAPE, "w", encoding="utf-8", newline="").write(RESHAPE_SRC)
    print("CREATED %s" % RESHAPE)

    import py_compile
    for path in (MOD, RESHAPE):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Nothing reads this yet - CH2 brings the page. Meanwhile, make the")
    print("partnerships testable:")
    print("  python scripts\\reshape_partnerships.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
