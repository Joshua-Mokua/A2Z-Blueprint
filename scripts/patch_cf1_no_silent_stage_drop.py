#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CF1 - a stage with no target is reported, not silently thrown away.

FROM THE BANK (2026-09-04): "admin needs to add documents by ticking... he has
ticked and when trying to save it says every flow needs a closing... yet the
flow clearly has those stated."

THE FLOW DOES HAVE THEM. The form throws them away before sending:

    .filter((s) => s.stage && Number.isFinite(s.target_days) && s.target_days > 0)

A stage whose target is blank - or zero - is DROPPED SILENTLY. Closing stages
are the ones most likely to be blank, because nothing is "due" after a deal
closes and nobody thinks to type a number there. So Closed Won and Closed Lost
vanish from the payload, and the server correctly reports that the flow has no
closing stage.

The admin then looks at the screen, sees Closed Won and Closed Lost sitting
there, and is told they do not exist. That is the worst kind of error message:
truthful about the payload and false about what the person can see.

WHAT THIS CHANGES: a stage with a name but no usable target is no longer
dropped. The form REFUSES to save and names the stages that need a number.

WHY NOT DEFAULT THEM TO 1: because a target is a service-level promise, and
inventing one for a closing stage would put a number in the bank's SLA report
that nobody chose. The admin should type it.

WHY NOT LET THE SERVER REJECT IT: it already does, but by then the stage is
gone from the payload and the message describes a flow the admin is not
looking at.

Usage (from project root, .venv active):
    python scripts\patch_cf1_no_silent_stage_drop.py            # dry run
    python scripts\patch_cf1_no_silent_stage_drop.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "AdminConfig.tsx")

OLD = '''      .filter((s) => s.stage && Number.isFinite(s.target_days) && s.target_days > 0);
    if (stages.length === 0) {
      toast({ tone: 'danger', message: 'Add at least one stage with a positive target.' });
      return;
    }'''

NEW = '''      .filter((s) => s.stage);

    // ── A STAGE WITH NO TARGET IS REPORTED, NOT THROWN AWAY ─────────────────
    // This used to drop any stage whose target was blank or zero. Closing
    // stages are the likeliest to be blank - nothing is "due" after a deal
    // closes - so Closed Won and Closed Lost disappeared from the payload and
    // the server replied that the flow had no closing stage. The admin was
    // looking straight at them.
    //
    // They are not invented a target here: a target is a service-level
    // promise, and a number nobody chose would end up in the bank's SLA
    // report. The admin is asked for it instead.
    const untargeted = stages
      .filter((s) => !Number.isFinite(s.target_days) || s.target_days <= 0)
      .map((s) => s.stage);
    if (untargeted.length > 0) {
      toast({
        tone: 'danger',
        message: `Give a target in days for: ${untargeted.join(', ')}. `
               + 'Every stage needs one, including the closing stages.',
      });
      return;
    }
    if (stages.length === 0) {
      toast({ tone: 'danger', message: 'Add at least one stage with a positive target.' });
      return;
    }'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "A STAGE WITH NO TARGET IS REPORTED" in s:
        print("ABORT: CF1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the stage filter matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  an untargeted stage is named, not dropped")

    if "Number.isFinite(s.target_days) && s.target_days > 0);" in s:
        print("ABORT: the silent drop survives.")
        return 1
    if "untargeted.join" not in s:
        print("ABORT: the admin is not told WHICH stages need a number.")
        return 1
    if "target_days: 1" in NEW or "|| 1" in NEW:
        print("ABORT: a target is being invented. That number would reach the")
        print("       bank's SLA report without anybody choosing it.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1
    print("  ok  post-checks: nothing dropped, nothing invented")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cf1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
