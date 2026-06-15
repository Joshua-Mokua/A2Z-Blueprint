# CHANGELOG v10.564 — reset_test_data.py (fresh-start wipe for pipeline/credit/cascade)

scripts/reset_test_data.py — wipes the transactional data for the three modules
under focus so 5 cases can be run deal -> disbursement on a clean slate.

WIPES (backed up first, timestamped):
  data/pipeline.json          -> []   + Postgres pipeline_deals truncated
  data/loan_applications.json -> []
  data/credit_admin.json      -> []
  data/credit_monitoring.json -> watchlist emptied
  data/target_cascade.json    -> {}   (cascaded targets)
  data/bank_targets.json      -> {}   (ONLY with --include-bank-targets)

KEEPS: staff_register, org_config, pipeline_settings, lms_config, all *_config,
       kpi_library, users.json, BSC actuals/scores, EDMS.

Safety: DRY-RUN by default (shows counts, changes nothing). --confirm executes.
Backs up every file + the pipeline_deals rows into data/_reset_backup_<ts>/
before mutating (backup-before-mutation doctrine).

USAGE:
  python scripts/reset_test_data.py            # dry-run
  python scripts/reset_test_data.py --confirm  # execute
