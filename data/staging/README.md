# `data/staging/` — Pre-Production Rehearsal

**Mirrors PROD layout but isolated.** Used to rehearse production
deployments without touching PROD data.

## Promotion

STAGING is the last step before PROD. Promotion requires:
- Explicit `set_by` actor (typically CIO/COO)
- Recorded reason
- `force=False` (uses the natural STAGING -> PROD transition)
