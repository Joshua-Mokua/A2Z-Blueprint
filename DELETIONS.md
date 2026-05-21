# v10.294 Deletions

The following files were DELETED in this batch. They are listed
here because zip files cannot represent file deletions; the
maintainer must remove them manually after extracting this zip:

- `utils/cims_feedback_loop.py` — dead duplicate of
  `utils/cims_completion_feedback.py` (standard #180); zero
  inbound references; not locked by any audit gate.

After extraction, run:

    rm utils/cims_feedback_loop.py

Then verify the audit still passes:

    python scripts/audit.py

Expected: `Score: 185/185 gates = 100.0% — PASS`
