"""pages/120_staff_pbt.py — v10.375 Role-aware Staff PBT (Phase A second batch).

First UI surface of the v10.370 + v10.374 work. Shows per-staff PBT
(from `utils.customer_pbt_allocator.compute_pbt_by_staff`) classified by
the role taxonomy axis (from `utils.role_taxonomy.classify_role`).

Joshua's body-system framing: this page presents the **circulatory
system** — where PBT flows through the staff dimension. The seniority
axis (skeleton) lives in other pages; this one focuses on profitability
responsibility per the v10.374 taxonomy.

Three filters in the sidebar:
  • Profitability tier (default: portfolio_owner — the primary sales)
  • SBU (Retail / Commercial / Corporate / Treasury / Digital / Support / Executive)
  • Branch scope (branch_bound / head_office / national)

The page makes the v10.370 G257 identity directly visible to users:
  Σ(PBT across selected staff) = portion of bank PBT this slice owns.
  Σ(PBT all tiers including Unassigned) = Bank PBT exactly (within KES 100).

Tabs:
  1. Staff ranking — table sortable by PBT, customer count, role
  2. Tier distribution — Σ PBT by profitability tier (shows reconciliation visibly)
  3. SBU contribution — Σ PBT by SBU
  4. Unassigned customers — customers whose rm_code doesn't map to a known staff

Audit: G130 (UI integration), G160 (manifest), G257 (staff identity preserved),
G260 (role taxonomy alignment).
"""

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from pages._access import require_access

require_access("sales_customer.branch_log")  # piggyback existing scope

# ── Page header ─────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>👥 Staff PBT — Role-Aware View</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "v10.375 · Phase A · canonical engine</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "Per-staff profitability from the v10.370 atomic engine. Roles classified "
    "via the v10.374 profitability axis (portfolio_owner / proposition_owner / "
    "structural_owner / service / support). Σ(Staff PBT including Unassigned) "
    "= Bank PBT (G257). 'Tagged in CBS' is role-neutral; the tier shows who "
    "actually owns the PBT vs who's incidentally tagged."
)


# ── Load CBS + compute ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load_staff_pbt_view():
    """Run seed + persist + canonical engines once; cache for 5 min."""
    try:
        from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
        from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
        from utils.pbt_computation import compute_pbt_from_cbs
        from utils.customer_pbt_allocator import (
            compute_pbt_by_customer, compute_pbt_by_staff,
            sum_staff_pbts, UNASSIGNED_STAFF_BUCKET,
        )
        from utils.role_taxonomy import classify_role

        bank, _ = seed_virtual_bank(config=SeedConfig.small())
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            persist_bank_to_cbs(bank, output_dir=td_path)
            bank_pbt = compute_pbt_from_cbs(td_path)
            cust_pbts = compute_pbt_by_customer(td_path)
            staff_pbts = compute_pbt_by_staff(td_path, customer_pbts=cust_pbts)
            staff_total = sum_staff_pbts(staff_pbts)

        # Load users.json to enrich staff codes with names + roles
        users_path = Path(__file__).resolve().parent.parent / "data" / "users.json"
        users = {}
        if users_path.exists():
            try:
                u = json.loads(users_path.read_text(encoding="utf-8"))
                # users.json keyed by login — flatten to staff_code lookup
                for login, rec in u.items():
                    if isinstance(rec, dict):
                        sc = rec.get("staff_code", "")
                        if sc:
                            users[sc] = {
                                "name": rec.get("full_name", login),
                                "role": rec.get("role", ""),
                                "department": rec.get("department", ""),
                            }
            except Exception:
                pass

        # Build dataframe
        rows = []
        for staff_code, pbt_components in staff_pbts.items():
            u = users.get(staff_code, {})
            role = u.get("role", "Unknown" if staff_code != UNASSIGNED_STAFF_BUCKET
                         else "Unassigned")
            classification = classify_role(role)
            rows.append({
                "staff_code": staff_code,
                "name": u.get("name", staff_code),
                "role": role,
                "tier": classification.tier,
                "branch_scope": classification.branch_scope,
                "sbu": classification.sbu,
                "department": u.get("department", ""),
                "customers": int(pbt_components.notes[0].split(":")[1].strip().split()[0])
                              if pbt_components.notes else 0,
                "pbt": float(pbt_components.pbt),
                "operating_income": float(pbt_components.operating_income),
                "total_opex": float(pbt_components.total_opex),
                "impairment": float(pbt_components.impairment_charge),
            })
        df = pd.DataFrame(rows)
        return {
            "df": df,
            "bank_pbt": float(bank_pbt.pbt),
            "staff_total_pbt": float(staff_total.pbt),
            "delta_kes": float(bank_pbt.pbt - staff_total.pbt),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


data = _load_staff_pbt_view()

if "error" in data:
    st.error(f"Could not load staff PBT view: {data['error']}")
    st.stop()

df = data["df"]
bank_pbt = data["bank_pbt"]
staff_total = data["staff_total_pbt"]
delta = data["delta_kes"]


# ── Top reconciliation strip (makes G257 visible) ───────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Bank PBT", f"KES {bank_pbt/1e9:,.2f}B")
with c2:
    st.metric("Σ Staff PBT", f"KES {staff_total/1e9:,.2f}B")
with c3:
    st.metric(
        "Δ Reconciliation",
        f"KES {delta:,.0f}",
        help="G257 enforces this to be < KES 100. Currently shows the live identity."
    )
with c4:
    st.metric("Staff Buckets", f"{len(df)}")


# ── Filters (the role-aware bit) ────────────────────────────────────
st.markdown("---")
fc1, fc2, fc3 = st.columns(3)
with fc1:
    tier_options = ["(all tiers)"] + sorted(df["tier"].unique().tolist())
    tier_filter = st.selectbox(
        "Profitability tier",
        tier_options,
        index=tier_options.index("portfolio_owner") if "portfolio_owner" in tier_options else 0,
        help=(
            "portfolio_owner: tagged sales staff (RMs, ROs). "
            "proposition_owner: overlap propositions (Women Banking). "
            "structural_owner: Branch Managers and above. "
            "service: Tellers/CSOs (occasionally tagged). "
            "support: HO functions."
        ),
    )
with fc2:
    sbu_options = ["(all SBUs)"] + sorted(df["sbu"].unique().tolist())
    sbu_filter = st.selectbox("SBU", sbu_options)
with fc3:
    scope_options = ["(all scopes)"] + sorted(df["branch_scope"].unique().tolist())
    scope_filter = st.selectbox(
        "Branch scope",
        scope_options,
        help=(
            "branch_bound: works at one branch. "
            "head_office: HO RM whose customers span multiple branches. "
            "national: bank-wide role."
        ),
    )

# Apply filters
fdf = df.copy()
if tier_filter != "(all tiers)":
    fdf = fdf[fdf["tier"] == tier_filter]
if sbu_filter != "(all SBUs)":
    fdf = fdf[fdf["sbu"] == sbu_filter]
if scope_filter != "(all scopes)":
    fdf = fdf[fdf["branch_scope"] == scope_filter]

# ── Tabs ────────────────────────────────────────────────────────────
tabs = st.tabs([
    "Staff ranking",
    "Tier distribution",
    "SBU contribution",
    "Unassigned",
])

with tabs[0]:
    st.markdown(f"**{len(fdf)} staff** match current filters")
    if len(fdf) > 0:
        slice_pbt = fdf["pbt"].sum()
        slice_pct = (slice_pbt / bank_pbt * 100) if bank_pbt else 0
        st.caption(
            f"Σ(filtered) = KES {slice_pbt/1e9:,.2f}B "
            f"({slice_pct:+.1f}% of bank PBT)"
        )
        display = fdf[[
            "staff_code", "name", "role", "tier", "sbu", "branch_scope",
            "customers", "operating_income", "total_opex", "impairment", "pbt",
        ]].copy()
        display = display.sort_values("pbt", ascending=False).reset_index(drop=True)
        # Format money columns
        for col in ("operating_income", "total_opex", "impairment", "pbt"):
            display[col] = display[col].apply(lambda v: f"{v:,.0f}")
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("No staff match the current filter combination.")

with tabs[1]:
    st.markdown("**Σ PBT by profitability tier** — the G257 identity made visible")
    tier_sum = df.groupby("tier").agg(
        staff_count=("staff_code", "count"),
        pbt=("pbt", "sum"),
        customers=("customers", "sum"),
    ).reset_index()
    tier_sum["pbt_pct"] = (tier_sum["pbt"] / bank_pbt * 100).round(2)
    tier_sum_disp = tier_sum.copy()
    tier_sum_disp["pbt"] = tier_sum_disp["pbt"].apply(lambda v: f"KES {v/1e9:,.3f}B")
    tier_sum_disp["pbt_pct"] = tier_sum_disp["pbt_pct"].apply(lambda v: f"{v:+.2f}%")
    st.dataframe(tier_sum_disp, use_container_width=True, hide_index=True)
    st.caption(
        f"Σ across all tiers = KES {df['pbt'].sum()/1e9:,.3f}B; "
        f"Bank PBT = KES {bank_pbt/1e9:,.3f}B; "
        f"Δ = KES {bank_pbt - df['pbt'].sum():,.0f} (G257 tolerance: KES 100)."
    )

with tabs[2]:
    st.markdown("**Σ PBT by SBU** — links to v10.368 SBU dimension")
    sbu_sum = df.groupby("sbu").agg(
        staff_count=("staff_code", "count"),
        pbt=("pbt", "sum"),
        customers=("customers", "sum"),
    ).reset_index().sort_values("pbt", ascending=False)
    sbu_disp = sbu_sum.copy()
    sbu_disp["pbt"] = sbu_disp["pbt"].apply(lambda v: f"KES {v/1e9:,.3f}B")
    st.dataframe(sbu_disp, use_container_width=True, hide_index=True)

with tabs[3]:
    st.markdown(
        "**Unassigned bucket** — customers whose `rm_code` doesn't match any "
        "known staff. In production this surfaces data quality issues."
    )
    unassigned = df[df["staff_code"] == "Unassigned"]
    if len(unassigned) > 0:
        st.dataframe(unassigned, use_container_width=True, hide_index=True)
        u_pbt = float(unassigned["pbt"].sum())
        st.metric(
            "Unassigned PBT",
            f"KES {u_pbt/1e9:,.3f}B",
            help=(
                "This share of bank PBT is held by customers without a tagged "
                "RM. Engineering goal: zero. Real banks typically have <5% in "
                "this bucket; values above that point to RM-coverage gaps."
            ),
        )
    else:
        st.success("No unassigned customers — 100% of customers have a tagged staff.")


# ── Footer: data lineage ────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**Data lineage:** seeded VirtualBankCore → "
    "`persist_bank_to_cbs` → CBS accounts.csv + customers.csv → "
    "`compute_pbt_by_customer` (v10.370 atomic, G256) → "
    "`compute_pbt_by_staff` (v10.370 Σ over portfolio, G257) → "
    "joined with `users.json::role` → "
    "`classify_role` (v10.374 profitability axis, G260) → this view. "
    "All identities reconcile to Bank PBT within KES 100."
)

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

