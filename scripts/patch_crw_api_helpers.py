#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Add the calls the credit risk workbench needs.

Every one of these endpoints already exists. Nothing in the app called them,
so credit risk had a tick where the bank had designed a decision.

    /lms/config/conditions                     the seeded library
    /lms/applications/{id}/decision            takes the two condition lists
    /lms/applications/{id}/return-for-rework    takes return_to after RT1
    /lms/applications/{id}/assign               claims from the pool

    python scripts/patch_crw_api_helpers.py            # dry run
    python scripts/patch_crw_api_helpers.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "lib", "api.ts")

BLOCK = '''
// ── Credit risk workbench ─────────────────────────────────────────────────────
// The decision endpoint has always accepted the two condition lists, and the
// escalation has always existed. Nothing on screen offered them.

export interface ConditionLibrary {
  pre_approval: string[];
  pre_disbursement: string[];
  configured: boolean;
}

export async function fetchConditionLibrary(): Promise<ConditionLibrary> {
  return getJson<ConditionLibrary>('/lms/config/conditions');
}

/** Approve, decline or return, with the conditions the decision carries. */
export async function recordCreditRiskDecision(
  appId: string,
  body: {
    verdict: 'approved' | 'declined' | 'returned';
    authority: string;
    reason: string;
    pre_approval_conditions?: string[];
    pre_disbursement_conditions?: string[];
  },
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, typeof body>(
    `/lms/applications/${encodeURIComponent(appId)}/decision`, body);
}

/** Send a case back, naming who it goes to. Omit return_to and it behaves as
 *  it always has - back to the deal's owner. */
export async function returnCaseForRework(
  appId: string,
  body: { reason: string; items?: string[]; return_to?: string; return_to_name?: string },
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, typeof body>(
    `/lms/applications/${encodeURIComponent(appId)}/return-for-rework`, body);
}

/** Claim an unassigned case, so two people do not work the same one. */
export async function claimCase(
  appId: string, analystCode: string, analystName: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse,
                  { analyst_code: string; analyst_name: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/assign`,
    { analyst_code: analystCode, analyst_name: analystName });
}
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "fetchConditionLibrary" in s:
        print("Already applied.")
        return 1
    for need in ("export async function getJson", "postJson",
                 "LoanAppMutationResponse"):
        if need not in s:
            print("%s is not in this file - check before applying." % need)
            return 1

    s = s.rstrip() + "\n" + BLOCK
    if s.count("{") != s.count("}"):
        print("Braces unbalanced.")
        return 1
    print("Four helpers added: conditions, decision, return, claim.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_crw")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: copy CreditRiskWorkbench.tsx over the thin version, then")
    print("      pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
