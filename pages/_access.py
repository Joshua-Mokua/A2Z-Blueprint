"""pages/_access.py — Shim re-exporting utils.page_access.

v10.346 — canonical location moved to utils/page_access.py.
Every existing `from pages._access import require_access` keeps
working unchanged.
"""

from utils.page_access import *  # noqa: F401, F403
from utils.page_access import (  # noqa: F401
    require_access,
    get_my_scope,
    check_access_dotted,
    tab_visible,
)
# check_access, get_visible_staff, tab_visible_cascade are imported
# from utils.core_audit by utils.page_access; re-export so callers
# that imported them from pages._access keep working.
from utils.core_audit import (  # noqa: F401
    check_access,
    get_visible_staff,
    tab_visible_cascade,
)
