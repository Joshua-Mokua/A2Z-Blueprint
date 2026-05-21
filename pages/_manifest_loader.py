# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_manifest_loader.py — Shim re-exporting utils.page_manifest_loader.

v10.346 — canonical location moved to utils/page_manifest_loader.py.
"""

from utils.page_manifest_loader import *  # noqa: F401, F403
