# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_cockpit_render.py — Shim re-exporting utils.page_cockpit_render.

v10.346 — canonical location moved to utils/page_cockpit_render.py.
Every existing `from pages._cockpit_render import render_summary` keeps
working unchanged.
"""

from utils.page_cockpit_render import *  # noqa: F401, F403
