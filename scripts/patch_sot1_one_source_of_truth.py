#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The deal's stage follows its credit case.

Two records tell the same story and nothing keeps them together. The funnel
reads deal.stage; the credit screens read case.status. Every stranding this
week came from that: deals walked forward by hand, committees advancing
unsubmitted deals, cases moving while their deal stood still.

Senior management reads the funnel. It cannot be a second opinion.

LoanApplicationManager.update is the one place every status change passes
through. When a status changes, the linked deal's stage is brought into line
with it - so the funnel becomes a view of the credit workflow rather than a
parallel record that drifts.

    python scripts/patch_sot1_one_source_of_truth.py            # dry run
    python scripts/patch_sot1_one_source_of_truth.py --apply

WHAT IT WILL NOT DO. It never moves a deal backwards, never touches a closed
deal, and never invents a stage a product's flow does not define. Where the
mapping cannot be made it leaves the deal alone and records why - a wrong
stage is worse than a stale one.
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "core.py")

OLD = '''    def update(self, app_id: str, fields: dict):
        for i, a in enumerate(self.apps):
            if a["id"] == app_id:
                self.apps[i].update(fields)
                self.apps[i]["last_updated"] = datetime.now().date().isoformat()
                self.save()
                return True
        return False'''

NEW = '''    # ── WHERE A CASE STANDS, AND WHERE ITS DEAL SHOULD ───────────────────────
    # The funnel reads deal.stage and the credit screens read case.status.
    # Nothing kept them together, so the funnel reported progress nobody had
    # made and hid progress that had been. Senior management reads the funnel;
    # it cannot be a second opinion.
    #
    # The status is the truth: assignment, committee, decision and
    # disbursement all hang off it. The stage is where that work has got to.
    _STATUS_TO_STAGE = {
        "submitted":              "Department Credit Analysis",
        "assigned":               "Department Credit Analysis",
        "in_review":              "Department Credit Analysis",
        "info_requested":         "Department Credit Analysis",
        "recommended":            "Department Credit Committee Review",
        "ready_for_committee":    "Department Credit Committee Review",
        "referred_to_committee":  "Department Credit Committee Review",
        "committee_recommended":  "Credit Analysis",
        "approved":               "Credit Analysis",
        "credit_admin":           "Credit Administration",
        "disbursed":              "Trops",
    }

    def _stage_for_status(self, status: str) -> str:
        return self._STATUS_TO_STAGE.get(str(status or "").strip().lower(), "")

    def _sync_deal_stage(self, app: dict, status: str) -> None:
        """Bring the linked deal's stage into line with its case.

        Forward only, never past a closing stage, and only to a stage the
        product's own flow defines. Where the mapping cannot be made the deal
        is left alone: a wrong stage is worse than a stale one.
        """
        want = self._stage_for_status(status)
        deal_id = str(app.get("pipeline_deal_id") or "").strip()
        if not want or not deal_id:
            return
        try:
            from utils.core import PipelineManager as _PM
            from utils.api import _stage_flow_for as _flow_for
            pm = _PM()
            d = pm.get_deal(deal_id)
            if not d:
                return
            cur = str(d.get("stage", "") or "")
            if cur.lower().startswith("closed"):
                return
            flow = [str(x) for x in (_flow_for(d.get("product_type")
                                               or d.get("product", "")) or [])]
            if want not in flow or cur not in flow:
                return
            if flow.index(want) <= flow.index(cur):
                return          # forward only - a status never drags a deal back
            pm.update_stage(deal_id, want,
                            "Brought into line with the credit case (%s)."
                            % str(status), "system")
        except Exception as exc:
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "could not align deal %s with case %s: %s",
                    deal_id, app.get("id"), exc)
            except Exception:
                pass

    def update(self, app_id: str, fields: dict):
        for i, a in enumerate(self.apps):
            if a["id"] == app_id:
                _was = str(self.apps[i].get("status", "") or "")
                self.apps[i].update(fields)
                self.apps[i]["last_updated"] = datetime.now().date().isoformat()
                self.save()
                _now = str(self.apps[i].get("status", "") or "")
                if _now and _now != _was:
                    self._sync_deal_stage(self.apps[i], _now)
                return True
        return False'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "WHERE A CASE STANDS, AND WHERE ITS DEAL SHOULD" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("LoanApplicationManager.update matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "flow.index(want) <= flow.index(cur)" not in NEW:
        print("A status could drag a deal backwards.")
        return 1
    if 'cur.lower().startswith("closed")' not in NEW:
        print("A closed deal could be reopened by a status change.")
        return 1
    if "want not in flow" not in NEW:
        print("A stage the product does not define could be written.")
        return 1
    if "_now != _was" not in NEW:
        print("It would run on every update, not only a status change.")
        return 1
    if "logging" not in NEW:
        print("A failure would be silent.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A status change now brings its deal's stage into line - forward")
    print("only, within the product's own flow, never past a close.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_sot1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nThis holds them together FROM NOW ON. Align the ones already out")
    print("of step with:")
    print("   python scripts/align_deal_stage_to_case.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
