# Reset fix — wipe the file the app actually uses

## Problem
scripts/reset_test_data.py wiped data/pipeline.json, but PipelineManager
reads/writes data/pipeline_deals.json (+ pipeline_activities.json). So the
reset never cleared the real store — 14 stale deals (D0001-D0014) survived,
and new deals were numbered D0015+ because add_deal numbers as D{count+1}.

## Fix
WIPE list now empties the canonical store first:
  - pipeline_deals.json       (PipelineManager deals)
  - pipeline_activities.json  (deal activity log)
  - pipeline.json             (legacy; kept defensively, skipped if absent)
Still backs up every file before mutating; Postgres pipeline_deals still
truncated. Staff / config / BSC untouched.

## Run (project root, venv active)
  python scripts\reset_test_data.py            # dry-run, shows counts
  python scripts\reset_test_data.py --confirm  # execute (backs up first)
Then restart the API. After this, a freshly created deal is D0001.
