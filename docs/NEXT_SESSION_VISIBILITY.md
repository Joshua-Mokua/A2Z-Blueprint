# Next session — dotted-line pipeline visibility gaps

## The issue (Josh, EOD)
Certain managers can't see pipeline they should via DOTTED-LINE reporting:
- **Fiona** — should see (dotted) pipeline from **Consumer RMs, especially Premier Banking** — sees NONE.
- **Head of DSA** — similar visibility gap.
- **Head of Direct Banking** — similar gap.

Open question: does Josh need to EXPLICITLY MAP direct reportees (because hierarchy-derived
visibility has become unreliable admin-side), or should the system derive it?

## What to investigate first (morning)
1. How pipeline VISIBILITY is resolved — the scope engine:
   - `get_visible_staff_codes(user)` / `resolve_deal_permissions` (utils/api_pipeline_scope.py,
     api_pipeline_permissions.py) — how does it decide whose deals a manager sees?
   - Does it use SOLID-line only (Reports To Code) or also DOTTED-line? Where do dotted lines live?
2. Fiona's record: her role, unit, staff_code, and what managed_* fields she has
   (managed_roles / managed_units / managed_staff_codes in users.json). Is Premier / Consumer RM
   in her managed scope?
3. The Consumer RM / Premier staff: their Reports To Code + segment — do they roll up to Fiona
   by hierarchy, or only by an explicit dotted-line map that's missing?
4. Head of DSA + Head of Direct Banking: same — what should roll up to them, and does it?

## Likely shapes of the fix
- **If visibility is solid-line only** → need a dotted-line mechanism (a manager sees a set of
  roles/units/staff beyond their direct reports). May already exist via managed_roles/
  managed_units — check if it's populated for Fiona et al.
- **If dotted-line exists but isn't mapped** → populate the managed_* (or equivalent) mapping
  for Fiona (Consumer RM/Premier), Head of DSA, Head of Direct Banking.
- **If admin-side mapping is broken** → the admin UI for setting managed scope may not be
  writing correctly (echoes the earlier grant_admin_pg / store-split class of bug — confirm
  which store the visibility scope reads vs where admin writes).

## Note
Roster HAS good columns (Staff Code, Role, Unit, Department, Branch, Region, Reports To Code,
Band) — so hierarchy + dotted-line data is available to compute from. The question is whether
the scope engine uses it, and whether the dotted-line relationships are mapped.

## Resume pointer
HEAD at EOD: 36f6449 (branch-scoped committee picker). Today closed the credit-flow + branch-
committee workstream. This visibility issue is a NEW workstream for the morning.

## ADDENDUM (Josh EOD) — segment-level Consumer visibility
Beyond the individual dotted-line managers, there's a SEGMENT-level requirement:
- The **Consumer head-office team** should see the **ENTIRE Consumer pipeline**, and be able to
  **filter by sub-segment: Direct / Premier / Advantage** — for continuity.
So the morning's problem is two layers of the same scope engine:
  1. SEGMENT-level: Consumer HO team sees all Consumer pipeline, filterable by Direct/Premier/
     Advantage.
  2. DOTTED-LINE manager: Fiona (Premier), Head of DSA, Head of Direct Banking see their slices.

## Morning plan (refined)
1. Probe the scope engine: does get_visible_staff_codes support segment-wide visibility (see a
   whole Department/segment) AND dotted-line (managed_roles/units/staff)? Or only solid-line?
2. Confirm the Consumer sub-segments in data: are Direct / Premier / Advantage distinct values
   somewhere (a column, a segment field, a unit)? Needed for the filter.
3. Design: a Consumer-HO "sees all Consumer, filter by sub-segment" scope, plus the dotted-line
   maps for Fiona / Head of DSA / Head of Direct Banking.
4. Decide explicit-mapping vs derived, then implement + verify each manager sees the right slice.
