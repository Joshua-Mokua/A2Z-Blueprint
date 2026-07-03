#!/usr/bin/env python3
"""scripts/apply_fp1_create_policy.py — FP1: product-flow-derived create policy.

Fixes the create-deal blockers ("Unknown stage" / "deferred to Arc α4") ONCE at the
root, keyed to the PRODUCT'S OWN flow — including custom flows like Personal Loan
(Initiation -> ... -> Credit Analysis -> ... -> Trops).

ROOT: get_all_pipeline_stage_names() (core.py) now unions product_flows stages, so any
admin-authored stage is recognised (no more "Unknown stage").

CREATE POLICY (validate_create_payload, api_pipeline_mutations.py):
  * Create allowed at any stage in the product's flow BEFORE the credit-analysis
    handoff. Handoff stage is detected as (in priority):
      1. product_flows[...]["credit_handoff_stage"] if set, else
      2. the first stage whose name is in the CREDIT-ANALYSIS FAMILY
         {"Credit Analysis", "Credit Assessment"} (case-insensitive), else
      3. no cutoff (whole flow creatable, terminal guard only).
  * Blocked AT or AFTER the handoff (past there the case belongs to the modules).
  * Terminal stages blocked.
  * A deal created BEYOND the first stage must be manager-validated.

SAFE: .pre_fp1 backups (core.py, api_pipeline_mutations.py). Idempotent. --revert.
NOTE: this batch does NOT touch pipeline_settings.json — product flows are yours to
author from admin. It only makes the ENGINE respect whatever flow you configure.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "utils" / "core.py"
MUT = ROOT / "utils" / "api_pipeline_mutations.py"
BAKS = {CORE: CORE.with_suffix(".py.pre_fp1"), MUT: MUT.with_suffix(".py.pre_fp1")}

def patch_core(s):
    seg = s.split("def get_all_pipeline_stage_names")
    if len(seg) < 2 or "product_flows" in seg[1].split("return names")[0]:
        return s, False
    anchor = '''        for flow in cfg.get("stage_flows", {}).values():
            if isinstance(flow, list):
                for st in flow:
                    n = str(st).strip()
                    if n:
                        names.add(n)
    except Exception:
        pass
    return names'''
    new = '''        for flow in cfg.get("stage_flows", {}).values():
            if isinstance(flow, list):
                for st in flow:
                    n = str(st).strip()
                    if n:
                        names.add(n)
        # FP1 (2026-07-02): per-PRODUCT flows must be recognised too, else an
        # admin-authored product-flow stage is "Unknown stage" at create/advance.
        for entry in cfg.get("product_flows", {}).values():
            if isinstance(entry, dict):
                for st in entry.get("stages", []):
                    n = str(st.get("stage", "")).strip() if isinstance(st, dict) else str(st).strip()
                    if n:
                        names.add(n)
    except Exception:
        pass
    return names'''
    return s.replace(anchor, new, 1), True

def patch_mutations(s):
    if "_credit_handoff_cutoff" in s:
        return s, False
    helper = '''

# FP1 (2026-07-02): create-cutoff derived from the PRODUCT'S OWN flow, not a frozen set.
# The credit-analysis handoff stage is where the deal leaves pipeline ORIGINATION and
# becomes an LMS matter. It may be named per product ("Credit Analysis",
# "Credit Assessment", ...); detect it flexibly.
_CREDIT_ANALYSIS_FAMILY = {"credit analysis", "credit assessment"}

def _product_flow_stage_names(product_type: str) -> list:
    """Ordered stage names for a product's flow (product_flows)."""
    try:
        from utils.api import _load_json, _norm_product
        cfg = _load_json("pipeline_settings.json") or {}
        pf = cfg.get("product_flows", {}) or {}
        want = _norm_product(product_type) if product_type else ""
        for name, entry in pf.items():
            if _norm_product(name) == want and isinstance(entry, dict):
                out = []
                for st in entry.get("stages", []):
                    nm = st.get("stage") if isinstance(st, dict) else st
                    if nm:
                        out.append(str(nm))
                return out
    except Exception:
        pass
    return []

def _credit_handoff_cutoff(product_type: str):
    """Return (handoff_stage, handoff_index, flow_stages). handoff_index is None if
    the product's flow has no credit-analysis handoff stage."""
    stages = _product_flow_stage_names(product_type)
    # explicit config override
    explicit = None
    try:
        from utils.api import _load_json, _norm_product
        cfg = _load_json("pipeline_settings.json") or {}
        pf = cfg.get("product_flows", {}) or {}
        want = _norm_product(product_type) if product_type else ""
        for name, entry in pf.items():
            if _norm_product(name) == want and isinstance(entry, dict):
                explicit = entry.get("credit_handoff_stage")
                break
    except Exception:
        pass
    if explicit and explicit in stages:
        return explicit, stages.index(explicit), stages
    # family match (first stage whose name is in the credit-analysis family)
    for i, nm in enumerate(stages):
        if str(nm).strip().lower() in _CREDIT_ANALYSIS_FAMILY:
            return nm, i, stages
    return None, None, stages

'''
    s = s.replace("def validate_create_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:",
                  helper + "\ndef validate_create_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:", 1)

    old_block = '''    # Stage must be a known non-LMS stage. Creating a deal directly
    # at an LMS stage would have the same inconsistency problem as
    # advancing into one without the handoff.
    stage = str(deal_data.get("stage", ""))
    if stage in LMS_DEFERRED_STAGES:
        return False, (
            f"Cannot create deal directly at stage '{stage}' "
            "(LMS handoff stage — deferred to Arc α4). "
            "Create at 'Lead' and advance through the workflow."
        )
    # State-machine integrity (stress-pass Phase 1): a deal must be BORN at an
    # early stage and walk the workflow. Block creation directly at terminal
    # outcomes (Closed Won/Lost) — which would book an instant fake win/loss
    # with no workflow — and at the Compliance handoff stage, which would skip
    # the entire pipeline and the LMS handoff.
    _CREATE_BLOCKED_STAGES = {"Closed Won", "Closed Lost", "Compliance"}
    if stage in _CREATE_BLOCKED_STAGES:
        return False, (
            f"Cannot create a deal directly at stage '{stage}'. "
            "Deals must start at an early stage (e.g. 'Lead') and advance "
            "through the workflow; terminal and handoff stages are reached "
            "by progressing a deal, not by creating one there."
        )
    if stage not in ALLOWED_ADVANCE_STAGES and stage not in _configured_stage_names():
        return False, f"Unknown stage: '{stage}'"'''
    new_block = '''    # FP1 (2026-07-02): create policy derived from the PRODUCT'S OWN flow, replacing
    # the stale hardcoded LMS_DEFERRED create-block. The pipeline tracks a deal
    # start->disbursement (the lead never drops), but a deal may only be CREATED
    # before the credit-analysis handoff; past there the case lives in the modules.
    stage = str(deal_data.get("stage", ""))
    product_type = str(deal_data.get("product_type", "") or "")

    if stage not in ALLOWED_ADVANCE_STAGES and stage not in _configured_stage_names():
        return False, f"Unknown stage: '{stage}'"

    if stage in {"Closed Won", "Closed Lost"}:
        return False, (
            f"Cannot create a deal directly at a terminal stage ('{stage}'). "
            "Terminal outcomes are reached by progressing a deal, not by creating one there."
        )

    handoff_stage, handoff_idx, flow_stages = _credit_handoff_cutoff(product_type)
    if flow_stages:
        if stage not in flow_stages:
            return False, (
                f"Stage '{stage}' is not part of the '{product_type}' product flow. "
                f"Configured stages: {', '.join(flow_stages)}."
            )
        stage_idx = flow_stages.index(stage)
        if handoff_idx is not None and stage_idx >= handoff_idx:
            return False, (
                f"Cannot create a deal at stage '{stage}'. Creation is allowed only "
                f"before the credit-analysis handoff ('{handoff_stage}'); at or beyond "
                "that point the deal is tracked automatically as it moves through credit "
                "analysis, credit administration and disbursement."
            )
        if stage_idx > 0 and not bool(deal_data.get("manager_validated")):
            return False, (
                f"A deal created already at stage '{stage}' must be manager-validated "
                "at creation (manager_validated) to record an in-progress deal entering "
                "above the first stage."
            )
    else:
        if stage not in {"Lead", "Open", "Prospecting", "Pitched", "Initiation"} and not bool(deal_data.get("manager_validated")):
            return False, (
                f"A deal created at stage '{stage}' (above the first stage) must be "
                "manager-validated at creation."
            )'''
    s = s.replace(old_block, new_block, 1)
    return s, True

def revert():
    for tgt, bak in BAKS.items():
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    c = CORE.read_text(encoding="utf-8"); m = MUT.read_text(encoding="utf-8")
    c_new, c_ch = patch_core(c); m_new, m_ch = patch_mutations(m)
    print(f"  core.py (recognise product_flows stages): {'change' if c_ch else 'skip'}")
    print(f"  api_pipeline_mutations.py (FP1 create policy): {'change' if m_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for tgt, new, ch in ((CORE, c_new, c_ch), (MUT, m_new, m_ch)):
        if ch:
            if not BAKS[tgt].exists(): BAKS[tgt].write_text(tgt.read_text(encoding="utf-8"), encoding="utf-8")
            tgt.write_text(new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
