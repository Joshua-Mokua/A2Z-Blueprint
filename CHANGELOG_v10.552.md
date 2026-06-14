# CHANGELOG v10.552 — Hardening Batch H1: Create/Refer Deal identity (D-01)

## Root cause (Create Deal failure)
validate_create_payload requires staff_code + staff_name. The POST
/api/pipeline/deals route validated the RAW client payload and never
re-derived caller identity — but get_current_user carries only JWT claims
(username/role), NOT staff_code/full_name (whoami_detailed re-fetches those
from users.json: "never trust JWT for these"). So when the client identity
was thin/absent the deal was rejected with "Missing required field:
staff_code", and the server could not recover. (The historical 2026-06-11
"failure" was a separate, already-fixed CIF-persistence issue — closed by δ2.)

## Resolution (utils/api.py)
Both the create and refer routes now inject staff_code/staff_name from the
caller's users.json record when the client omitted them (mirroring
whoami_detailed's re-fetch). Effects:
  - creation/referral can no longer fail for a thin client identity;
  - the client can no longer assert an arbitrary deal owner (latent gap);
  - managers/admins may still create on behalf by explicitly supplying a
    different staff_code (α5 / GAP-005 scope) — explicit values are preserved.

## Audit correction
A pipeline EDIT endpoint DOES exist: `@app.put("/api/pipeline/deals/{id}")`
(pipeline_deal_update). The earlier audit's "Edit Deal missing at both
layers" was wrong — it is a FRONTEND-only gap (no updatePipelineDeal fetcher).

## Verification
- py_compile utils/api.py -> OK
- proof: thin identity -> filled from users.json (validation passes);
  explicit client value preserved; unknown user still fails clearly.
- behavioral pytest locks the validate_create_payload contract.
