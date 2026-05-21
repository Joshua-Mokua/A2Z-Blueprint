# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_admin_canonical.py — Admin: Canonical Hierarchy Management.

Per Joshua v10.400: production-time admin can edit role_manager_whitelist,
role_tiers, and branch_tier_threshold from the UI, then regenerate the
cascade. All changes write to data/org_hierarchy_config.json with provenance.

Used as a sub-tab in pages/7_admin.py "People & Org" section.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.canonical_admin import (
    DEFAULT_BRANCH_TIER_THRESHOLD,
    get_branch_tier_threshold,
    list_role_managers,
    list_role_tiers,
    read_change_log,
    regenerate_cascade_from_canonical,
    remove_role,
    set_branch_tier_threshold,
    set_role_managers,
    set_role_tier,
    validate_canonical,
)


def render_canonical_admin(tab, uname: str):
    """Render the canonical hierarchy admin UI in `tab`."""
    with tab:
        st.subheader("🎯 Canonical Hierarchy")
        st.caption(
            "Edit the **organisation's canonical reporting lines** — who reports "
            "to whom, by role. The cascade engine reads this to allocate KPI "
            "targets down the organisation. Changes persist to "
            "`data/org_hierarchy_config.json` with full provenance."
        )

        view = st.radio(
            "",
            ["📋 Overview", "🔗 Reporting Lines", "🎚️ Role Tiers",
             "⚙️ Threshold", "🔄 Regenerate", "📜 Change Log"],
            horizontal=True, key="canonical_view",
        )
        st.markdown("---")

        if view == "📋 Overview":
            _render_overview()
        elif view == "🔗 Reporting Lines":
            _render_reporting_lines(uname)
        elif view == "🎚️ Role Tiers":
            _render_role_tiers(uname)
        elif view == "⚙️ Threshold":
            _render_threshold(uname)
        elif view == "🔄 Regenerate":
            _render_regenerate(uname)
        elif view == "📜 Change Log":
            _render_change_log()


# ─────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────
def _render_overview():
    rmw = list_role_managers()
    tiers = list_role_tiers()
    threshold = get_branch_tier_threshold()
    validation = validate_canonical()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Roles mapped", len(rmw))
    c2.metric("Tier entries", len(tiers))
    c3.metric("Branch threshold", threshold)
    valid_color = "🟢" if validation["valid"] else "🔴"
    c4.metric("Canonical valid", f"{valid_color} {'Yes' if validation['valid'] else 'No'}")

    if not validation["valid"]:
        with st.expander(f"⚠️ {len(validation['issues'])} issue(s) detected", expanded=True):
            for issue in validation["issues"][:20]:
                st.error(f"• {issue}")
            if len(validation["issues"]) > 20:
                st.caption(f"... and {len(validation['issues'])-20} more")

    # Tier distribution
    st.markdown("**Tier distribution** — staff layers by canonical tier")
    tier_counts: dict = {}
    for role, t in tiers.items():
        tier_counts[t] = tier_counts.get(t, 0) + 1

    tier_labels = {
        0: "0 — MD (root)",
        1: "1 — Chiefs",
        2: "2 — Heads / Directors",
        3: "3 — Senior Managers / Area",
        4: "4 — Managers (branch top)",
        5: "5 — Officers / Supervisors",
        6: "6 — Frontline",
    }
    rows = []
    for t in sorted(tier_counts.keys()):
        rows.append({
            "Tier": t,
            "Label": tier_labels.get(t, f"Tier {t}"),
            "Roles at this tier": tier_counts[t],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────
# Reporting Lines editor
# ─────────────────────────────────────────────────────────────────────
def _render_reporting_lines(uname: str):
    rmw = list_role_managers()
    tiers = list_role_tiers()
    all_roles = sorted(set(rmw.keys()) | set(tiers.keys()))

    st.markdown("**Edit canonical reporting lines** — who can manage whom (by role).")
    st.caption(
        "Order matters: the first listed manager is the *primary* (preferred "
        "same-unit match); subsequent ones are alternatives / fallbacks."
    )

    # Search
    search = st.text_input("🔍 Filter roles", "", key="rmw_search").strip().lower()

    # Display
    filtered = [r for r in sorted(rmw.keys()) if search in r.lower()] if search else sorted(rmw.keys())
    st.caption(f"Showing {len(filtered)} of {len(rmw)} roles")

    rows = []
    for role in filtered:
        rows.append({
            "Role": role,
            "Tier": tiers.get(role, "—"),
            "Reports to (canonical)": " → ".join(rmw[role]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Edit one role
    st.markdown("##### ✏️ Edit a role's managers")
    edit_role = st.selectbox(
        "Role to edit", [""] + all_roles, key="rmw_edit_role",
    )
    if edit_role:
        current_mgrs = rmw.get(edit_role, [])
        st.caption(f"Currently reports to: `{', '.join(current_mgrs) if current_mgrs else '—'}`")
        new_mgrs_str = st.text_area(
            "New manager list (comma-separated, primary first)",
            value=", ".join(current_mgrs),
            key=f"rmw_edit_mgrs_{edit_role}",
            help="Order: first = primary same-unit; rest = alternatives",
        )
        reason = st.text_input("Reason for change (optional)", "", key=f"rmw_edit_reason_{edit_role}")
        c1, c2 = st.columns([1, 4])
        if c1.button("💾 Save", key=f"rmw_save_{edit_role}", type="primary"):
            new_mgrs = [m.strip() for m in new_mgrs_str.split(",") if m.strip()]
            ok = set_role_managers(edit_role, new_mgrs, who=uname, reason=reason)
            if ok:
                st.success(f"✓ Updated {edit_role} → {new_mgrs}")
                st.rerun()
            else:
                st.error("Save failed")
        if c2.button(f"🗑️ Remove role '{edit_role}' from canonical",
                     key=f"rmw_remove_{edit_role}"):
            if remove_role(edit_role, who=uname, reason=reason):
                st.success(f"✓ Removed {edit_role}")
                st.rerun()
            else:
                st.error("Remove failed")

    st.markdown("---")

    # Add new role mapping
    st.markdown("##### ➕ Add a new role → manager mapping")
    add_role = st.text_input("New role name", "", key="rmw_add_role")
    add_mgrs = st.text_input("Reports to (comma-separated)", "", key="rmw_add_mgrs")
    add_reason = st.text_input("Reason", "Add new role", key="rmw_add_reason")
    if st.button("➕ Add role", key="rmw_add_btn", type="primary"):
        if not add_role.strip():
            st.error("Role name required")
        else:
            mgrs = [m.strip() for m in add_mgrs.split(",") if m.strip()]
            if not mgrs:
                st.error("At least one manager role required")
            else:
                ok = set_role_managers(add_role.strip(), mgrs, who=uname, reason=add_reason)
                if ok:
                    st.success(f"✓ Added {add_role} → {mgrs}")
                    st.rerun()
                else:
                    st.error("Add failed")


# ─────────────────────────────────────────────────────────────────────
# Role Tiers editor
# ─────────────────────────────────────────────────────────────────────
def _render_role_tiers(uname: str):
    tiers = list_role_tiers()
    st.markdown("**Edit canonical tier per role.**")
    st.caption(
        "Tier 0 = MD root | 1 = Chiefs | 2 = Heads | 3 = Senior Managers / "
        "Area | 4 = Managers (branch top) | 5 = Officers | 6 = Frontline."
    )

    search = st.text_input("🔍 Filter roles", "", key="tier_search").strip().lower()
    filtered = [r for r in sorted(tiers.keys()) if search in r.lower()] if search else sorted(tiers.keys())
    st.caption(f"Showing {len(filtered)} of {len(tiers)} roles")

    rows = [{"Role": r, "Tier": tiers[r]} for r in filtered]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### ✏️ Edit a role's tier")
    edit_role = st.selectbox("Role", [""] + sorted(tiers.keys()), key="tier_edit_role")
    if edit_role:
        current_tier = tiers.get(edit_role, 5)
        new_tier = st.number_input(
            f"New tier for {edit_role}",
            min_value=0, max_value=9, value=int(current_tier),
            step=1, key=f"tier_edit_val_{edit_role}",
        )
        reason = st.text_input("Reason", "", key=f"tier_edit_reason_{edit_role}")
        if st.button("💾 Save tier", key=f"tier_save_{edit_role}", type="primary"):
            ok = set_role_tier(edit_role, int(new_tier), who=uname, reason=reason)
            if ok:
                st.success(f"✓ {edit_role} → tier {new_tier}")
                st.rerun()
            else:
                st.error("Save failed")


# ─────────────────────────────────────────────────────────────────────
# Branch tier threshold
# ─────────────────────────────────────────────────────────────────────
def _render_threshold(uname: str):
    current = get_branch_tier_threshold()
    st.markdown("**Branch tier threshold**")
    st.caption(
        "Roles at this tier or higher are treated as **branch-level** "
        "(same-unit reporting enforced). Roles below this tier are HQ/regional "
        "(any-unit reporting allowed). Default: 4."
    )
    new_t = st.number_input(
        "Threshold", min_value=0, max_value=9, value=current, step=1,
        key="threshold_val",
    )
    reason = st.text_input("Reason for change", "", key="threshold_reason")
    if st.button("💾 Save threshold", key="threshold_save", type="primary"):
        ok = set_branch_tier_threshold(int(new_t), who=uname, reason=reason)
        if ok:
            st.success(f"✓ Threshold set to {new_t}")
            st.rerun()
        else:
            st.error("Save failed")


# ─────────────────────────────────────────────────────────────────────
# Regenerate cascade
# ─────────────────────────────────────────────────────────────────────
def _render_regenerate(uname: str):
    st.markdown("### 🔄 Regenerate Target Cascade")
    st.caption(
        "After editing canonical, regenerate `target_cascade.json` so the "
        "cascade engine reflects the new reporting lines. Auto-backup of the "
        "old cascade is kept at `data/_canonical_backups/`."
    )
    st.info(
        "**v10.404 default: Preserve manual allocations.** Any manager who has "
        "manually set targets for their team via 'Set team targets' is preserved "
        "— their subtree won't be overwritten. Only gaps get filled from canonical."
    )

    # Mode selector
    mode = st.radio(
        "Mode",
        ["🛡️ Preserve manual allocations (recommended)",
         "🔥 Force full rebuild (overwrites all manual work)"],
        key="regen_mode",
        horizontal=False,
    )
    preserve = mode.startswith("🛡️")

    if not preserve:
        st.warning(
            "⚠️ **Force rebuild will OVERWRITE every manager's manual "
            "allocation.** Use only after exporting/backing up critical "
            "allocations manually."
        )

    reason = st.text_input("Reason for regen", "manual regen", key="regen_reason")
    if st.button("🔄 Regenerate cascade now", key="regen_btn", type="primary"):
        with st.spinner("Regenerating cascade…"):
            ok, count, msg = regenerate_cascade_from_canonical(
                who=uname, reason=reason, preserve_manual=preserve
            )
        if ok:
            st.success(f"✓ {msg}")
            st.caption(
                "Engine will pick up new cascade on next page load. "
                "Run `python utils/cascade_structure_engine.py` to verify."
            )
        else:
            st.error(f"✗ {msg}")


# ─────────────────────────────────────────────────────────────────────
# Change log
# ─────────────────────────────────────────────────────────────────────
def _render_change_log():
    log = read_change_log(limit=100)
    st.markdown(f"**Recent canonical changes ({len(log)} entries)**")
    if not log:
        st.info("No changes logged yet.")
        return
    rows = []
    for entry in reversed(log):  # newest first
        rows.append({
            "When": entry.get("ts", "")[:19].replace("T", " "),
            "Who": entry.get("who", ""),
            "Action": entry.get("action", ""),
            "Target": entry.get("target", ""),
            "Old → New": (
                f"{_short(entry.get('old'))} → {_short(entry.get('new'))}"
            ),
            "Reason": entry.get("reason", "")[:50],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _short(v) -> str:
    if v is None:
        return "—"
    s = str(v)
    return s if len(s) < 40 else s[:37] + "…"
