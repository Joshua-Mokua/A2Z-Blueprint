#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
VU2 - VU1's api.ts half, as ANCHORED EDITS.

WHY THERE IS A v2. VU1 shipped a WHOLE api.ts, captured before FN1 and HD1 had
added `unit`/`segment` to fetchPipelineDefinedFunnel and fetchPipelineAnalytics.
Applying it overwrote both, and the build failed:

    fetchPipelineDefinedFunnel({ unit, segment })
    -> Expected 0 arguments, but got 1

The funnel and the headline cards lost their filters to a patch that had
nothing to do with either. That is the FIFTH time a whole-file capture has
carried away work it never knew about - a sidebar entry, a committee tab,
origin imports, a field mapping, and now two function signatures.

This adds the two things VU1 actually needed and touches nothing else:

  castCommitteeVote          the per-member vote call
  CommitteeGate.votes_cast   so the panel can show "1 of 2 voted, awaiting X"
        .quorum              before any record exists to read it from
        .awaiting

If either is already present it is skipped, so this is safe to run after a
partial recovery.

Verified: tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_vu2_api_client_anchored.py            # dry run
    python scripts\\patch_vu2_api_client_anchored.py --apply
"""
import os
import shutil
import sys

APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_vu2"

VOTE_ANCHOR = "export async function recordDealCommitteeDecision("

VOTE_NEW = """export interface CommitteeVoteResult {
  status: string; committee: string; your_vote: string;
  votes_cast: number; quorum: number; decided: boolean; outcome: string;
  tally: { name?: string; role?: string; vote?: string; at?: string }[];
  awaiting: string[];
}
/** ONE MEMBER, ONE VOTE, from their own login. recordDealCommitteeDecision
 *  posts every member's vote at once, which is how a single member closed a
 *  case: one vote, below quorum, DEFERRED, done. */
export async function castCommitteeVote(
  dealId: string, code: string,
  body: { vote: string; documents_validated?: boolean; comment?: string; note?: string },
): Promise<CommitteeVoteResult> {
  return postJson<CommitteeVoteResult>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/committee/${encodeURIComponent(code)}/vote`,
    body);
}

"""

GATE_OLD = """export interface CommitteeGate {
  code: string; name: string; recording_mode: string; voting_rule: string;
  members: { name: string; role: string }[];
  record: CommitteeRecord | null;
}"""

GATE_NEW = """export interface CommitteeGate {
  code: string; name: string; recording_mode: string; voting_rule: string;
  members: { name: string; role: string }[];
  record: CommitteeRecord | null;
  /** Whether THIS viewer may vote on this gate. The panel used to ask
   *  canEdit - "owner or admin" - which is the wrong question: a committee
   *  member is neither, and was shown a read-only panel with nothing to vote
   *  with. The server answers it from the roster. */
  can_vote?: boolean;
  /** Progress BEFORE a decision exists. Without these a member cannot tell
   *  whether the committee is waiting on them or on somebody else, which is
   *  the question they opened the case to answer. */
  votes_cast?: number;
  quorum?: number;
  awaiting?: string[];
}"""



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(APITS):
        print("ABORT: %s not found." % APITS)
        return 1

    s = open(APITS, encoding="utf-8").read()
    before = s
    did = []

    if "castCommitteeVote" in s:
        print("  already  castCommitteeVote")
    elif s.count(VOTE_ANCHOR) != 1:
        print("ABORT: the recordDealCommitteeDecision anchor matched %d times."
              % s.count(VOTE_ANCHOR))
        return 1
    else:
        s = s.replace(VOTE_ANCHOR, VOTE_NEW + VOTE_ANCHOR, 1)
        did.append("castCommitteeVote")

    if "can_vote?" in s and "votes_cast?" in s:
        print("  already  CommitteeGate progress fields")
    elif s.count(GATE_OLD) != 1:
        print("ABORT: the CommitteeGate type matched %d times." % s.count(GATE_OLD))
        return 1
    else:
        s = s.replace(GATE_OLD, GATE_NEW, 1)
        did.append("CommitteeGate progress")

    if s == before:
        print("ABORT: nothing to do - VU2 looks applied.")
        return 1
    print("  ok  added: %s" % ", ".join(did))

    # THE WHOLE POINT OF v2: the filters FN1 and HD1 added must survive.
    for fn in ("fetchPipelineDefinedFunnel", "fetchPipelineAnalytics"):
        i = s.find("export async function %s(" % fn)
        if i < 0:
            print("ABORT: %s is missing entirely." % fn)
            return 1
        if "opts" not in s[i:i + 260]:
            print("ABORT: %s no longer takes a filter - this patch would undo" % fn)
            print("       FN1/HD1, which is exactly what v1 did.")
            return 1
    print("  ok  the funnel and analytics filters are intact")

    for op, cl in (("{", "}"), ("(", ")")):
        if s.count(op) != s.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(APITS, APITS + BACKUP_SUFFIX)
    open(APITS, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % APITS)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
