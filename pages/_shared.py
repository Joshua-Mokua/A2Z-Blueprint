# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_shared.py — Shim re-exporting utils.page_shared.

v10.346 — canonical location moved to utils/page_shared.py so that
utils/* modules (notably utils/finance_hub_render.py) can import
load_shared_state without a layer violation.

Every existing `from pages._shared import load_shared_state` keeps
working unchanged.
"""

from utils.page_shared import *  # noqa: F401, F403
from utils.page_shared import load_shared_state  # noqa: F401
