#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show the reason the server gave, not just the status code.

400 and 422 read the server's detail. Everything else throws

    API /pipeline/deals/D0644/advance failed: 403 Forbidden

and discards it. Every refusal chased this week had a sentence behind it that
nobody saw:

    "This deal has been validated; moving it backward to 'Documentation' must
     be sanctioned by a line manager. Ask a manager to perform this move with
     a reason."

    "This deal is with credit. An analyst has assessed the current figure, so
     a manager has to make the change."

    "This case is not assigned to you. Claim it from the pool first."

Each was written to be read by the person who hit it. Each showed as a status
code, so a rule working correctly looked like a broken system - and the time
went into diagnosing something that was never wrong.

    python scripts/patch_err1_show_what_the_server_said.py            # dry run
    python scripts/patch_err1_show_what_the_server_said.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "lib", "api.ts")

OLD = '''  if (!res.ok) {
    throw new Error(
      `API ${path} failed: ${res.status} ${res.statusText}`,
    );
  }'''

NEW = '''  if (!res.ok) {
    // The server explains its refusals. A 403 carrying "ask a manager to
    // perform this move with a reason" was showing as "403 Forbidden", so a
    // rule working correctly looked like a fault, and the time went into
    // diagnosing something that was never wrong.
    let detail = '';
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch { /* not JSON - fall back to the status */ }
    throw new Error(
      detail || `API ${path} failed: ${res.status} ${res.statusText}`,
    );
  }'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "The server explains its refusals" in s:
        print("Already applied.")
        return 1
    n = s.count(OLD)
    if n == 0:
        print("The error branch was not found in the expected shape.")
        return 1

    # postJson and getJson both have it. Fix every one.
    s = s.replace(OLD, NEW)
    print("Fixed %d error branch(es)." % n)

    if "res.status === 400" not in s:
        print("The 400 handling was lost.")
        return 1
    if "AuthExpiredError" not in s:
        print("The 401 handling was lost.")
        return 1
    if "detail ||" not in s:
        print("An empty detail would leave the user with nothing at all.")
        return 1
    if s.count("{") != s.count("}"):
        print("Braces unbalanced.")
        return 1
    print("A refusal now shows the reason, falling back to the status code.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_err1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
