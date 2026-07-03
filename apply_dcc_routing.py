#!/usr/bin/env python3
"""scripts/apply_dcc_routing.py — DCC: customer-type committee routing.

Adds the customer-type DCC layer to the committee-journey engine:
  branch-originated: BCC -> DCC(by customer type) -> Credit Analysis
  non-branch:              DCC(by customer type) -> Credit Analysis
DCC by customer type: Consumer DCC | Commercial DCC | CIB DCC, chosen from the deal's
client_type. Admin-configured routing (N1).

- api.py:
  * _DEFAULT_COMMITTEE_PALETTE gains Consumer DCC / Commercial DCC / CIB DCC
    (members=[], admin-editable — they seed the palette the admin manages).
  * _effective_committee_journey inserts the client_type DCC before Credit Analysis
    and drops branch-only committees for non-branch deals, reading the map from
    committee_routing (admin config); falls back gracefully if unconfigured.
- config: seed committee_routing (client_type_to_dcc + branch_only_codes) if absent.

SAFE: .pre_dcc backups. Idempotent. --revert.
"""
import sys, shutil, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
CFG = ROOT / "data" / "pipeline_settings.json"
BAKS = {API: API.with_suffix(".py.pre_dcc"), CFG: CFG.with_suffix(".json.pre_dcc")}

def patch_config(text):
    d = json.loads(text)
    if "committee_routing" in d:
        return text, False
    d["committee_routing"] = {
        "client_type_to_dcc": {
            "Consumer": "DCC_CONS", "Commercial": "DCC_COMM", "CIB": "DCC_CIB",
        },
        "branch_only_codes": ["BCC1"],
    }
    return json.dumps(d, indent=2), True

def patch_api(s):
    changed = False
    # a) add the three DCCs to the DEFAULT palette (admin-editable seed)
    if "DCC_CONS" not in s:
        anchor = '''    {"code": "DCC", "name": "Head Office Department Credit Committee", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},'''
        new = anchor + '''
    {"code": "DCC_CONS", "name": "Consumer DCC", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},
    {"code": "DCC_COMM", "name": "Commercial DCC", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},
    {"code": "DCC_CIB", "name": "CIB DCC", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},'''
        s = s.replace(anchor, new, 1)
        changed = True

    # b) routing helpers + journey extension
    if "_client_type_dcc_for" not in s:
        helper = '''
def _committee_routing_cfg() -> dict:
    """DCC routing config (admin-set): client_type_to_dcc map + branch_only_codes."""
    cfg = _load_json("pipeline_settings.json") or {}
    r = cfg.get("committee_routing", {})
    return r if isinstance(r, dict) else {}

def _client_type_dcc_for(deal: dict) -> str:
    """The DCC committee code matching the deal's client_type, or '' if none."""
    ct = str(deal.get("client_type", "") or "").strip()
    m = _committee_routing_cfg().get("client_type_to_dcc", {}) or {}
    if ct in m:
        return str(m[ct])
    for k, v in m.items():
        if str(k).strip().lower() == ct.lower():
            return str(v)
    return ""

def _deal_is_branch_originated(deal: dict) -> bool:
    """Branch-originated = the deal has a branch. Non-branch (head-office/direct)
    deals skip branch-only committees (e.g. BCC)."""
    return bool(str(deal.get("branch", "") or "").strip())

'''
        s = s.replace("def _effective_committee_journey(deal: dict) -> list:",
                      helper + "\ndef _effective_committee_journey(deal: dict) -> list:", 1)
        anchor = '''    configured = _product_committee_journey(deal)
    out = list(configured)'''
        new = '''    configured = _product_committee_journey(deal)
    out = list(configured)

    # DCC: insert the customer-type DCC (Consumer/Commercial/CIB) if not already present.
    dcc = _client_type_dcc_for(deal)
    if dcc and dcc not in out:
        out.append(dcc)

    # DCC: non-branch deals skip branch-only committees (e.g. BCC).
    if not _deal_is_branch_originated(deal):
        branch_only = set(_committee_routing_cfg().get("branch_only_codes", []) or [])
        out = [c for c in out if c not in branch_only]'''
        s = s.replace(anchor, new, 1)
        changed = True

    return s, changed

def revert():
    for tgt, bak in BAKS.items():
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    cfg = CFG.read_text(encoding="utf-8"); a = API.read_text(encoding="utf-8")
    cfg_new, cfg_ch = patch_config(cfg)
    a_new, a_ch = patch_api(a)
    print(f"  pipeline_settings.json (committee_routing): {'change' if cfg_ch else 'skip'}")
    print(f"  api.py (DCC palette + client-type routing + branch skip): {'change' if a_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for tgt, new, ch in ((CFG, cfg_new, cfg_ch), (API, a_new, a_ch)):
        if ch:
            if not BAKS[tgt].exists(): BAKS[tgt].write_text(tgt.read_text(encoding="utf-8"), encoding="utf-8")
            tgt.write_text(new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
