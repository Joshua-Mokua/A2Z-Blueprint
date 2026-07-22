# Staff sync to Alex's production server — handoff

## Status: file ready, awaiting Alex's pull + restart

## What was done (this session)
- Confirmed Postgres is the true roster source (363 users); staff_register.xlsx was stale.
- Exported true Postgres -> data/staff_register.xlsx (export_pg_to_register.py).
- Finalized upload file: dropped ADMIN001 system row (fixed 'invalid role Admin' AND
  'multiple roots'); validated against the SAME checks _staffup_validate uses.
  -> data/staff_register_upload.xlsx (362 staff, 0 validation errors, proven on Josh's machine).
- Verified upload feature (staff_upload_preview/apply + frontend fetchers) is committed
  (67671de) and pushed to origin/main. api.py clean, 0 commits ahead.

## Alex's 500 = version skew
His bank server runs code older than 67671de, so the upload endpoint crashes (500, not a
422 validation reject). The file is valid — the endpoint on his side is stale.

## Alex's fix (send him this)
1. git pull
2. Stop the API server (Ctrl+C)
3. Restart: python -m utils.api
4. Hard-refresh browser (Ctrl+Shift+R)
5. Retry upload -> preview should validate (362 staff), not 500
If still 500: send the last ~15 lines from the API server console when clicking Upload.

## CRITICAL before Alex clicks APPLY (not just preview)
Upload is WIPE-AND-REPLACE. Keep-set preserves ONLY ["william001","admin"] by default.
-> Confirm Alex's admin login username. If it is NOT 'admin' or 'william001', he will be
   LOCKED OUT of production. Add his login to the keep-list first (the apply body takes a
   `keep` list; or he runs scripts/upload_staff_register.py <file> --apply --keep <his_login>).

## Upload file location
- data/staff_register_upload.xlsx (repo)
- also copied to Josh's Desktop
- 362 staff, 1 root (KE1333 MD Rabecca), all roles/branches/reports-to valid

## The deeper split-brain (NOT fixed — future)
App reads staff from TWO places: admin UI -> Postgres; roster/BSC/scoring -> staff_register.xlsx.
They drift. Today's export made them agree; a permanent fix would make one authoritative.
