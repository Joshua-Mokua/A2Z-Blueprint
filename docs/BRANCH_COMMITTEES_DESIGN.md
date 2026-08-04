# Branch Credit Committees — per-branch constitution (design)

## Requirement (from Josh)
Admin can already create the Department committees (3: DCC_CONS/COMM/CIB — works). But Branch
Credit Committees must be 16 (one per branch in the network), each with:
  - a branch-specific name, e.g. "Fortis Branch Credit Committee"
  - members
  - chaired by that branch's BM (or a chosen alternate if the BM is unavailable)
Needs to be EASY — creating 16 by hand is tedious.

## What already exists
- CommitteeAdmin.tsx: working editor (code, name, chaired_by, members, recording_mode).
- upsert_committee_palette endpoint: saves a committee {code, name, chaired_by, members[]}.
- Committee record supports name + chair + members — but NOT a `branch` association yet.
- 17 branches in org_config (Head Office + 16 branches). Head Office = CIB/direct-to-dept.
- Routing (_effective_committee_journey, _deal_is_branch_originated) resolves committees;
  branch_only_codes currently = ["BCC1"] (one generic branch committee).

## Gaps
1. Committee record has no `branch` field → can't map a committee to its branch.
2. Only one generic BCC1 exists → no per-branch committees.
3. No easy way to create all 16.
4. Routing sends branch-originated deals to BCC1 (generic), not the deal's own branch committee.

## Design
### 1. Add `branch` to the committee record (backend, additive)
upsert_committee_palette accepts an optional `branch` field. Branch-kind committees carry
`branch: "Fortis"`. Department committees leave it blank. Backward compatible (optional).

### 2. Generator: scaffold 16 branch committees (the "with ease" part)
A one-click "Generate branch committees" action (admin) that, for each branch (excluding Head
Office), pre-creates a committee:
  - code:  BCC_<BRANCHKEY>   (e.g. BCC_FORTIS)
  - name:  "<Branch> Branch Credit Committee"
  - kind:  "branch"
  - branch: "<Branch>"
  - chaired_by: the branch's BM (looked up from org structure), if resolvable
  - members: [] (admin fills)
Idempotent: skips branches that already have a committee. Admin then edits members/chair per
committee in the existing CommitteeAdmin UI.

### 3. Alternate chair
chaired_by stays a single field; admin can change it per committee if the BM is unavailable.
(Optional later: an `alternate_chair` field. For now, admin edits chaired_by.)

### 4. Routing (uses branch field)
When a branch-originated deal reaches the branch committee step, resolve the committee whose
`branch` matches the deal's branch (instead of the generic BCC1). _deal_is_branch_originated
already identifies branch deals; add a resolver: branch -> BCC_<branch> committee code.
branch_only_codes becomes the set of all BCC_* codes (or the resolver handles it).

## Delivery (respects skip-worktree/per-site)
- Committees live in lms_config.json (skip-worktree, per-site). So the GENERATOR runs on each
  site (Alex runs it on the bank) — it reads that site's branches + BMs and scaffolds locally.
- Backend code (branch field, generator endpoint, routing resolver) travels via git (tracked).
- No overwrite of any committee the bank already made (generator is idempotent).

## Build order
1. Backend: add `branch` to committee record + a generate-branch-committees endpoint + routing
   resolver (branch -> committee). Tracked, travels via git.
2. Frontend: a "Generate branch committees" button in CommitteeAdmin + a branch field in the
   editor. Tracked.
3. Bank: Alex pulls, clicks Generate (or runs a seed), then edits members per branch.

## Open decisions for Josh
1. Head Office — no branch committee (CIB direct to department)? Assumed yes.
2. Auto-fill BM as chair from org structure — or leave chair blank for admin to set? Assumed
   auto-fill BM where resolvable.
3. Should the 16 be created by an admin BUTTON in the UI, or a seed script Alex runs? UI button
   is easier for the bank; seed is more controllable. Recommend UI button (self-service).
