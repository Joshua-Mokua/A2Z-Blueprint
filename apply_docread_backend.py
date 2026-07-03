#!/usr/bin/env python3
"""scripts/apply_docread_backend.py — Batch 2: read path for per-product docs.

Makes _get_required_documents_for_deal resolve the deal's PRODUCT config first
(product_flows[product].required_documents from Batch 1), falling back to the
legacy lms_config document_checklist tiers when the product has no configured
documents. Also exposes documents_required_at_stage so later batches (gate) can
use it.

Backward compatible: products with no required_documents fall through to the
exact legacy behavior. SAFE: .pre_docread backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_docread")

# Replace the body of _get_required_documents_for_deal so it checks product config first.
ANCHOR = '''def _get_required_documents_for_deal(deal: dict) -> list:
    """Required credit documents for a deal, from lms_config's tiered
    document_checklist: default + amount/product add-ons. Order preserved,
    de-duplicated."""
    cfg = _load_json("lms_config.json") or {}'''

NEW = '''def _product_document_config(deal: dict) -> tuple:
    """(required_documents, required_at_stage) from the deal's PRODUCT flow
    (Batch 1 config in pipeline_settings.product_flows). ([], "") if unset."""
    product = str(deal.get("product") or deal.get("product_type") or "").strip()
    if not product:
        return [], ""
    pcfg = _load_json("pipeline_settings.json") or {}
    flows = pcfg.get("product_flows", {}) if isinstance(pcfg, dict) else {}
    entry = flows.get(product) if isinstance(flows, dict) else None
    if not isinstance(entry, dict):
        return [], ""
    docs = entry.get("required_documents") or []
    if not isinstance(docs, list):
        docs = []
    stage = str(entry.get("documents_required_at_stage", "") or "")
    return [str(d) for d in docs if str(d).strip()], stage


def _get_required_documents_for_deal(deal: dict) -> list:
    """Required documents for a deal. Precedence:
      1. the deal's PRODUCT config (product_flows[product].required_documents), else
      2. legacy lms_config tiered document_checklist (default + amount/product).
    Order preserved, de-duplicated."""
    # 1) per-product configured documents (Batch 1) take precedence.
    prod_docs, _stage = _product_document_config(deal)
    if prod_docs:
        seen, out = set(), []
        for d in prod_docs:
            if d not in seen:
                seen.add(d); out.append(d)
        return out
    # 2) legacy fallback (unchanged behavior for unconfigured products).
    cfg = _load_json("lms_config.json") or {}'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_docread")
    else:
        print("  no .pre_docread backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if "_product_document_config" in s:
        print("  already applied."); return
    if ANCHOR not in s:
        print("  ERROR: _get_required_documents_for_deal anchor not found."); sys.exit(1)
    if dry:
        print("  --dry-run: would insert product-first doc resolution. Nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(ANCHOR, NEW, 1)
    API.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
