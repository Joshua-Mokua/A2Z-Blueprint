# CHANGELOG v10.553 — Hardening Batch H2: pipeline route model binding (real D-01 root cause)

## Why the H1 model patch had no runtime effect
All 7 pipeline mutation routes in utils/api.py annotate their request body
as a forward-ref STRING (payload: "PipelineDealCreate", "PipelineDealRefer",
"PipelineDealUpdate", "PipelineDealAdvance", "PipelineDealValidate",
"PipelineDealCancelRequest", "PipelineDealCancelApprove") — but none of those
models were imported into api.py. FastAPI resolves such annotations against
the module's globals; with the names absent, the forward-refs could not bind
the real (patched) classes, and a clean start of this file raises NameError
at route setup (consistent with a stale backend still serving the old model
while restarts of the current file fail to take over).

## Fix (utils/api.py)
Import the 7 pipeline request models at MODULE LEVEL (after the auth_jwt
import). api_pipeline_models imports only stdlib + pydantic, so there is no
import cycle. The forward-refs now resolve to the current classes, so the
H1 changes (staff_code/staff_name optional + server-side identity injection)
finally take effect at runtime.

## Verified
- py_compile api.py -> OK
- all 7 models import; forward-ref 'PipelineDealCreate' resolves;
  staff_code/staff_name .is_required() == False; a body without identity
  constructs without 422.

## After applying — confirm the running server matches disk
1. Fully stop ALL python processes, then `python -m utils.api`.
2. Watch the console: it must print the startup banner with NO NameError.
3. Open http://localhost:8502/api/docs -> POST /api/pipeline/deals ->
   staff_code must show as NOT required.
4. Create the deal in React -> should return 201.
