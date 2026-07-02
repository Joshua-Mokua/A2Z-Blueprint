#!/usr/bin/env python3
"""scripts/apply_sr1_stage_catalogue.py — SR1: Stage Repository backend.

A governed stage_catalogue (admin-managed, in pipeline_settings.json), mirroring
product_catalogue. A stage NAME must exist in the catalogue before a product flow can
use it — this locks the vocabulary (esp. the credit-analysis handoff) so flows can't
drift ("Contact" vs "Contacted"). Seeds from the Personal Loan (Assets) flow.

- config: seed "stage_catalogue": {"stages":[{"name","retired"}...]} if absent.
- api.py: _is_stage_catalogued(name); _validate_product_flow now rejects any stage not
  in the catalogue (with a clear "add it to the stage repository first" message);
  the /api/pipeline/stages config response exposes stage_catalogue; stage_catalogue
  added to _EDITABLE_CONFIG_KEYS so admin can manage it.
- RETIRING a stage never breaks existing deals: retired stages stay VALID for flows
  that already use them; they're only hidden from NEW authoring (enforced in SR2 UI).
  Backend validation accepts catalogued stages whether or not retired.

SAFE: .pre_sr1 backups. Idempotent. --revert.
"""
import sys, shutil, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
CFG = ROOT / "data" / "pipeline_settings.json"
BAKS = {API: API.with_suffix(".py.pre_sr1"), CFG: CFG.with_suffix(".json.pre_sr1")}

SEED_STAGES = [
    "Initiation", "Negotiation", "Documentation", "Branch Credit Committee Review",
    "Credit Analysis", "Offer Letter", "Credit Administration", "Trops",
]

def patch_config(text):
    d = json.loads(text)
    if "stage_catalogue" in d:
        return text, False
    # seed from Personal Loan flow stages if present, else the SEED_STAGES constant
    seed = list(SEED_STAGES)
    try:
        pl = d.get("product_flows", {}).get("Personal Loan", {})
        names = [s.get("stage") if isinstance(s, dict) else s for s in pl.get("stages", [])]
        if names:
            seed = [str(n) for n in names if n]
    except Exception:
        pass
    d["stage_catalogue"] = {"stages": [{"name": n, "retired": False} for n in seed]}
    return json.dumps(d, indent=2), True

def patch_api(s):
    changed = False
    # a) _is_stage_catalogued helper (mirrors _is_product_catalogued), inserted before it
    if "_is_stage_catalogued" not in s:
        helper = '''def _is_stage_catalogued(stage_name: str) -> bool:
    """SR1: True if a stage NAME exists in the admin stage_catalogue (exact,
    case-insensitive after strip). Retired stages still count as catalogued so
    existing flows/deals never break; the UI hides retired names from NEW authoring.
    Mirrors _is_product_catalogued."""
    nm = str(stage_name or "").strip().lower()
    if not nm:
        return False
    cfg = _load_json("pipeline_settings.json") or {}
    cat = cfg.get("stage_catalogue", {}) if isinstance(cfg, dict) else {}
    for st in (cat.get("stages", []) if isinstance(cat, dict) else []):
        cn = st.get("name") if isinstance(st, dict) else st
        if str(cn or "").strip().lower() == nm:
            return True
    return False


def _stage_catalogue_names(include_retired: bool = True) -> list:
    """Ordered catalogue stage names (for dropdowns / validation)."""
    cfg = _load_json("pipeline_settings.json") or {}
    cat = cfg.get("stage_catalogue", {}) if isinstance(cfg, dict) else {}
    out = []
    for st in (cat.get("stages", []) if isinstance(cat, dict) else []):
        if isinstance(st, dict):
            if not include_retired and st.get("retired"):
                continue
            nm = str(st.get("name", "") or "").strip()
        else:
            nm = str(st or "").strip()
        if nm:
            out.append(nm)
    return out


'''
        s = s.replace("def _is_product_catalogued(product_type: str) -> bool:",
                      helper + "def _is_product_catalogued(product_type: str) -> bool:", 1)
        changed = True

    # b) enforce catalogue membership in _validate_product_flow (after the per-stage loop
    #    that populates `seen`). Add a check right after the stages loop's dup/target checks.
    if "not in the stage repository" not in s:
        anchor = '''        seen.add(nm)
        try:
            t = int(s.get("target_days"))
        except (TypeError, ValueError):
            return False, f"stage '{nm}': target_days must be an integer"
        if t <= 0:
            return False, f"stage '{nm}': target_days must be positive"'''
        new = '''        seen.add(nm)
        # SR1: every stage must exist in the admin stage_catalogue (governed
        # vocabulary). If the catalogue is empty (not yet seeded), skip this
        # check so nothing breaks pre-seed.
        if _stage_catalogue_names() and not _is_stage_catalogued(nm):
            return False, (
                f"Stage '{nm}' is not in the stage repository. Add it to the stage "
                "repository first, then use it in a product flow."
            )
        try:
            t = int(s.get("target_days"))
        except (TypeError, ValueError):
            return False, f"stage '{nm}': target_days must be an integer"
        if t <= 0:
            return False, f"stage '{nm}': target_days must be positive"'''
        s = s.replace(anchor, new, 1)
        changed = True

    # c) expose stage_catalogue in the config response
    if '"stage_catalogue":' not in s:
        s = s.replace('        "product_flows":     cfg.get("product_flows", {}),',
                      '        "product_flows":     cfg.get("product_flows", {}),\n'
                      '        "stage_catalogue":   cfg.get("stage_catalogue", {}),', 1)
        changed = True

    # d) allow admin to manage stage_catalogue
    if '"stage_catalogue"' not in s.split("_EDITABLE_CONFIG_KEYS")[1].split("}")[0]:
        s = s.replace('_EDITABLE_CONFIG_KEYS = {',
                      '_EDITABLE_CONFIG_KEYS = {\n    "stage_catalogue",', 1)
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
    print(f"  pipeline_settings.json (seed stage_catalogue): {'change' if cfg_ch else 'skip'}")
    print(f"  api.py (catalogue guard + config expose): {'change' if a_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for tgt, new, ch in ((CFG, cfg_new, cfg_ch), (API, a_new, a_ch)):
        if ch:
            if not BAKS[tgt].exists(): BAKS[tgt].write_text(tgt.read_text(encoding="utf-8"), encoding="utf-8")
            tgt.write_text(new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
