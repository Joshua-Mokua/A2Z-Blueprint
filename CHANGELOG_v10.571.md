# CHANGELOG v10.571 — Batch B7: managers oversee, owners operate

## Change
A non-admin manager-in-scope could edit and advance a subordinate's deal. Now
the owner drives the deal (edit/advance); the manager oversees — view, validate
(the anti-ghost gate), query (return to owner), approve-cancel. Admin retains
full operate rights, and is the interim continuity path for moving a departed
RM's deals until the dedicated reassignment lands.

utils/api_pipeline_permissions.py — resolve_deal_permissions:
- new is_admin_like = is_admin OR "admin" in role
- can_edit          = (is_owner OR is_admin_like) and not backup-only
- can_advance_stage = (is_owner OR is_backup OR is_admin_like) and not terminal
(can_view / can_validate / can_approve_cancel unchanged — managers keep these.)

## Verified
- Manager: view+validate yes; edit+advance no.
- Owner: edit+advance yes.  Backup: advance yes, edit no.  Admin: all yes.

## Follow-on (recorded in PENDING_ITEMS.md)
Admin reassignment of a deal's owner (staff departure/handover), with the set of
authorized-to-reassign roles defined by admin in config. Interim: admin edits
the owner directly.

## Test
tests/test_batchB7_manager_no_operate.py (run in the project venv).
