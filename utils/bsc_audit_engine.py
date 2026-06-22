"""BSC Deep Audit Engine — v10.424 (BSC Rescue Phase opens).

Per Joshua's directive: every staff has complete befitting BSC; React
migration ready; admin config functioning; 100% interconnection BSC ↔
cascade; aligned with canonical org hierarchy; no ambiguities or
duplications.

This engine surfaces every BSC integrity issue as queryable structured
data, so fix batches (v10.425+) can be tracked against it.

Audit categories (each returns its own dataclass):
  1. audit_staff_coverage        — every staff_register row has BSC entries
  2. audit_kpi_completeness      — each staff has reasonable KPI count for role
  3. audit_pillar_canonical      — only 4 canonical pillars used
  4. audit_weight_normalization  — per-staff Weight sums to 1.0
  5. audit_library_alignment     — every BSC KPI exists in kpi_library
  6. audit_cascade_linkage       — cascaded targets reflected in BSC
  7. audit_duplicate_rows        — no (staff, KPI) pair appears twice
  8. bsc_full_audit              — rollup of all 7 above

The engine is READ-ONLY. It computes findings without modifying state.
Fix batches v10.425+ consume these audit results to drive migrations.

Live findings on current state (v10.424 ship):
  - 1437 staff (matches register; 100% coverage by count)
  - 6 Chief officers have only 2 KPIs (incomplete BSC)
  - 221 BSC rows have "Operational" pillar (non-canonical alias)
  - 494 staff have Weight sums != 1.0
  - 81 KPIs in BSC actuals not registered in kpi_library
  - 0 duplicate (staff, KPI) rows ✓

ARCHITECTURAL NOTE: API-first per v10.412 discipline. ZERO streamlit
imports. JSON-serializable dataclass returns. Engine state preserved.

Shipped: v10.424.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Canonical pillars (from kpi_library after v10.423)
CANONICAL_PILLARS: List[str] = [
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
]

# Tolerance for weight normalization checks
WEIGHT_TOLERANCE = 0.01  # 1%

# Per-role minimum KPI expectations (band-driven; conservative defaults)
# These are thresholds below which a BSC is "incomplete". Calibrated
# to surface chiefs/directors that lack proper BSCs without false-flagging
# specialized roles that legitimately have few KPIs.
MIN_KPIS_BY_ROLE_TIER: Dict[str, int] = {
    "exec_chief": 8,        # C-suite — must have multi-pillar BSC
    "director": 8,          # Directors — multi-pillar
    "head": 6,              # Heads of department — multi-pillar
    "regional": 5,
    "branch_manager": 5,
    "manager": 4,
    "specialist": 3,
    "officer": 3,
    "support": 2,
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class StaffCoverageAudit:
    register_count: int
    bsc_unique_staff: int
    in_register_not_in_bsc: List[str]   # missing BSC
    in_bsc_not_in_register: List[str]   # ghost entries
    coverage_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncompleteBSCEntry:
    staff_name: str
    staff_code: str
    role: str
    kpi_count: int
    threshold: int
    pillars_covered: int            # # of unique pillars in their BSC

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KPICompletenessAudit:
    total_staff: int
    incomplete_count: int
    incomplete_entries: List[IncompleteBSCEntry]
    avg_kpis_per_staff: float
    min_kpis: int
    max_kpis: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PillarCanonicalAudit:
    canonical_pillars: List[str]
    pillars_in_bsc: List[str]
    non_canonical_pillars: Dict[str, int]   # {pillar_name: row_count}
    affected_kpis: Dict[str, int]
    affected_roles: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WeightNormalizationAudit:
    total_staff: int
    normalized_count: int                   # weight sum == 1.0
    not_normalized_count: int
    not_normalized_samples: List[Tuple[str, float]]  # (staff_name, weight_sum)
    avg_weight_sum: float
    min_weight_sum: float
    max_weight_sum: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LibraryAlignmentAudit:
    bsc_unique_kpis: int
    library_kpi_count: int
    bsc_kpis_not_in_library: List[str]      # unregistered
    library_kpis_not_in_bsc: List[str]      # configured but unused
    alignment_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CascadeLinkageAudit:
    cascaded_staff_count: int
    bsc_staff_count: int
    cascaded_targets_not_in_bsc: List[str]  # samples: "staff_code|kpi"
    bsc_kpis_without_cascade: int
    sample_size_checked: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateRowAudit:
    total_bsc_rows: int
    duplicate_pairs: List[Tuple[str, str, int]]  # (staff, kpi, count)
    duplicate_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BSCFullAudit:
    """Rollup of all 7 audit categories with overall health score."""
    staff_coverage: StaffCoverageAudit
    kpi_completeness: KPICompletenessAudit
    pillar_canonical: PillarCanonicalAudit
    weight_normalization: WeightNormalizationAudit
    library_alignment: LibraryAlignmentAudit
    cascade_linkage: CascadeLinkageAudit
    duplicate_rows: DuplicateRowAudit
    overall_health_pct: float
    issues_by_severity: Dict[str, int]   # {critical, warning, info}
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "staff_coverage": self.staff_coverage.to_dict(),
            "kpi_completeness": self.kpi_completeness.to_dict(),
            "pillar_canonical": self.pillar_canonical.to_dict(),
            "weight_normalization": self.weight_normalization.to_dict(),
            "library_alignment": self.library_alignment.to_dict(),
            "cascade_linkage": self.cascade_linkage.to_dict(),
            "duplicate_rows": self.duplicate_rows.to_dict(),
            "overall_health_pct": self.overall_health_pct,
            "issues_by_severity": self.issues_by_severity,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_bsc_actuals(
    actuals_path: Optional[Path] = None,
) -> Optional["pandas.DataFrame"]:  # type: ignore
    """Load the BSC actuals Excel file. Returns None if unavailable."""
    import pandas as pd
    if actuals_path is None:
        # Find newest actuals_*.xlsx
        candidates = sorted(DATA_DIR.glob("actuals_*.xlsx"))
        if not candidates:
            return None
        actuals_path = candidates[-1]
    try:
        return pd.read_excel(actuals_path, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


def _load_staff_register(
    register_path: Optional[Path] = None,
) -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    if register_path is None:
        register_path = DATA_DIR / "staff_register.xlsx"
    if not register_path.exists():
        return None
    try:
        return pd.read_excel(register_path)
    except Exception:  # noqa: BLE001
        return None


def _load_kpi_library() -> Dict[str, Any]:
    path = DATA_DIR / "kpi_library.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_cascade() -> Dict[str, Any]:
    path = DATA_DIR / "target_cascade.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _classify_role_tier(role: str) -> str:
    """Map a role name to a tier for KPI-count threshold lookup."""
    rl = (role or "").lower()
    if any(x in rl for x in ("managing director", "chief executive")):
        return "exec_chief"
    if "chief" in rl:
        return "exec_chief"
    if "director" in rl:
        return "director"
    if rl.startswith("head") or "head of" in rl:
        return "head"
    if "regional" in rl:
        return "regional"
    if "branch manager" in rl:
        return "branch_manager"
    if "manager" in rl:
        return "manager"
    if any(x in rl for x in ("specialist", "analyst", "advisor")):
        return "specialist"
    if "officer" in rl:
        return "officer"
    return "support"


# ════════════════════════════════════════════════════════════════════
# Public API — Per-Category Audits
# ════════════════════════════════════════════════════════════════════

def audit_staff_coverage(
    actuals_path: Optional[Path] = None,
    register_path: Optional[Path] = None,
) -> StaffCoverageAudit:
    df = _load_bsc_actuals(actuals_path)
    reg = _load_staff_register(register_path)
    if df is None or reg is None:
        return StaffCoverageAudit(0, 0, [], [], 0.0)

    bsc_staff = set(df["Staff Name"].dropna().astype(str).str.strip())
    reg_staff = set(reg["Staff Name"].dropna().astype(str).str.strip())

    missing = sorted(reg_staff - bsc_staff)
    ghosts = sorted(bsc_staff - reg_staff)
    matched = len(reg_staff & bsc_staff)
    cov = (matched / len(reg_staff) * 100) if reg_staff else 0.0

    return StaffCoverageAudit(
        register_count=len(reg_staff),
        bsc_unique_staff=len(bsc_staff),
        in_register_not_in_bsc=missing,
        in_bsc_not_in_register=ghosts,
        coverage_pct=round(cov, 2),
    )


def audit_kpi_completeness(
    actuals_path: Optional[Path] = None,
) -> KPICompletenessAudit:
    df = _load_bsc_actuals(actuals_path)
    if df is None:
        return KPICompletenessAudit(0, 0, [], 0.0, 0, 0)

    # KPI count + pillar coverage per staff
    staff_stats = df.groupby(["Staff Name", "Staff Code", "Role"]).agg(
        kpi_count=("KPI", "nunique"),
        pillars_covered=("Pillar", "nunique"),
    ).reset_index()

    incomplete: List[IncompleteBSCEntry] = []
    for _, row in staff_stats.iterrows():
        role = str(row["Role"])
        tier = _classify_role_tier(role)
        threshold = MIN_KPIS_BY_ROLE_TIER.get(tier, 3)
        if row["kpi_count"] < threshold:
            incomplete.append(IncompleteBSCEntry(
                staff_name=str(row["Staff Name"]),
                staff_code=str(row["Staff Code"]),
                role=role,
                kpi_count=int(row["kpi_count"]),
                threshold=threshold,
                pillars_covered=int(row["pillars_covered"]),
            ))

    return KPICompletenessAudit(
        total_staff=len(staff_stats),
        incomplete_count=len(incomplete),
        incomplete_entries=incomplete,
        avg_kpis_per_staff=round(float(staff_stats["kpi_count"].mean()), 2),
        min_kpis=int(staff_stats["kpi_count"].min()),
        max_kpis=int(staff_stats["kpi_count"].max()),
    )


def audit_pillar_canonical(
    actuals_path: Optional[Path] = None,
) -> PillarCanonicalAudit:
    df = _load_bsc_actuals(actuals_path)
    if df is None:
        return PillarCanonicalAudit(CANONICAL_PILLARS, [], {}, {}, {})

    pillars_in_bsc = sorted(df["Pillar"].dropna().unique().tolist())
    non_canonical = {
        p: int((df["Pillar"] == p).sum())
        for p in pillars_in_bsc
        if p not in CANONICAL_PILLARS
    }

    # Affected KPIs + roles for non-canonical pillars
    affected_kpis: Dict[str, int] = {}
    affected_roles: Dict[str, int] = {}
    if non_canonical:
        nc_mask = df["Pillar"].isin(non_canonical.keys())
        affected_kpis = df[nc_mask]["KPI"].value_counts().head(20).to_dict()
        affected_roles = df[nc_mask]["Role"].value_counts().head(10).to_dict()

    return PillarCanonicalAudit(
        canonical_pillars=CANONICAL_PILLARS,
        pillars_in_bsc=pillars_in_bsc,
        non_canonical_pillars=non_canonical,
        affected_kpis={k: int(v) for k, v in affected_kpis.items()},
        affected_roles={k: int(v) for k, v in affected_roles.items()},
    )


def audit_weight_normalization(
    actuals_path: Optional[Path] = None,
) -> WeightNormalizationAudit:
    df = _load_bsc_actuals(actuals_path)
    if df is None:
        return WeightNormalizationAudit(0, 0, 0, [], 0.0, 0.0, 0.0)

    weight_sums = df.groupby("Staff Name")["Weight"].sum()
    normalized = weight_sums[(weight_sums - 1.0).abs() <= WEIGHT_TOLERANCE]
    not_norm = weight_sums[(weight_sums - 1.0).abs() > WEIGHT_TOLERANCE]

    samples = [(str(name), round(float(s), 3))
               for name, s in not_norm.head(20).items()]

    return WeightNormalizationAudit(
        total_staff=len(weight_sums),
        normalized_count=len(normalized),
        not_normalized_count=len(not_norm),
        not_normalized_samples=samples,
        avg_weight_sum=round(float(weight_sums.mean()), 3),
        min_weight_sum=round(float(weight_sums.min()), 3),
        max_weight_sum=round(float(weight_sums.max()), 3),
    )


def audit_library_alignment(
    actuals_path: Optional[Path] = None,
) -> LibraryAlignmentAudit:
    df = _load_bsc_actuals(actuals_path)
    lib = _load_kpi_library()
    if df is None:
        return LibraryAlignmentAudit(0, 0, [], [], 0.0)

    bsc_kpis = set(df["KPI"].dropna().astype(str).str.strip().unique())

    lib_kpi_names: Set[str] = set()
    lib_kpi_ids: Set[str] = set()
    lib_aliases: Set[str] = set()
    # Flat kpis list
    for k in lib.get("kpis", []):
        if isinstance(k, dict):
            if k.get("id"):
                lib_kpi_ids.add(str(k["id"]).strip())
            if k.get("name"):
                lib_kpi_names.add(str(k["name"]).strip())
            # v10.426 — also consider aliases field
            aliases = k.get("aliases", [])
            if isinstance(aliases, list):
                for a in aliases:
                    if a:
                        lib_aliases.add(str(a).strip())
    # Pillar-nested
    pillars = lib.get("pillars", {})
    if isinstance(pillars, dict):
        for _, klist in pillars.items():
            for k in klist:
                if isinstance(k, dict):
                    if k.get("id"):
                        lib_kpi_ids.add(str(k["id"]).strip())
                    if k.get("name"):
                        lib_kpi_names.add(str(k["name"]).strip())
                    aliases = k.get("aliases", [])
                    if isinstance(aliases, list):
                        for a in aliases:
                            if a:
                                lib_aliases.add(str(a).strip())

    lib_universe = lib_kpi_names | lib_kpi_ids | lib_aliases
    unregistered = sorted(bsc_kpis - lib_universe)
    unused = sorted(lib_kpi_names - bsc_kpis)
    alignment = (
        len(bsc_kpis & lib_universe) / len(bsc_kpis) * 100
        if bsc_kpis else 0.0
    )

    return LibraryAlignmentAudit(
        bsc_unique_kpis=len(bsc_kpis),
        library_kpi_count=len(lib_universe),
        bsc_kpis_not_in_library=unregistered,
        library_kpis_not_in_bsc=unused[:50],  # cap for serialization size
        alignment_pct=round(alignment, 2),
    )


def audit_cascade_linkage(
    actuals_path: Optional[Path] = None,
    sample_size: int = 200,
) -> CascadeLinkageAudit:
    df = _load_bsc_actuals(actuals_path)
    cascade = _load_cascade()
    if df is None:
        return CascadeLinkageAudit(0, 0, [], 0, 0)

    # Parse cascade keys: "staff_code|kpi_id|period"
    cascade_pairs: Set[Tuple[str, str]] = set()
    for key in cascade:
        if not isinstance(key, str) or "|" not in key:
            continue
        parts = key.split("|")
        if len(parts) >= 2:
            cascade_pairs.add((str(parts[0]), str(parts[1])))

    # Index BSC by (staff_code, kpi)
    bsc_pairs: Set[Tuple[str, str]] = set()
    for _, row in df.iterrows():
        sc = str(row.get("Staff Code", "")).strip()
        kpi = str(row.get("KPI", "")).strip()
        if sc and kpi:
            bsc_pairs.add((sc, kpi))

    # Sample cascade pairs to check for missing BSC entry
    # (We check by staff_code presence rather than exact KPI ID match
    # since cascade uses IDs and BSC uses names — alignment_pct below will
    # surface KPI-name vs ID issues separately.)
    cascade_staff = {s for s, _ in cascade_pairs}
    bsc_staff_codes = {s for s, _ in bsc_pairs}
    cascaded_not_in_bsc = sorted(cascade_staff - bsc_staff_codes)[:50]

    return CascadeLinkageAudit(
        cascaded_staff_count=len(cascade_staff),
        bsc_staff_count=len(bsc_staff_codes),
        cascaded_targets_not_in_bsc=cascaded_not_in_bsc,
        bsc_kpis_without_cascade=len(bsc_pairs - cascade_pairs),
        sample_size_checked=min(len(cascade_pairs), sample_size),
    )


def audit_duplicate_rows(
    actuals_path: Optional[Path] = None,
) -> DuplicateRowAudit:
    df = _load_bsc_actuals(actuals_path)
    if df is None:
        return DuplicateRowAudit(0, [], 0)

    pair_counts = df.groupby(["Staff Name", "KPI"]).size()
    dupes = pair_counts[pair_counts > 1]
    samples = [(str(staff), str(kpi), int(cnt))
               for (staff, kpi), cnt in dupes.head(20).items()]

    return DuplicateRowAudit(
        total_bsc_rows=len(df),
        duplicate_pairs=samples,
        duplicate_count=int(len(dupes)),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Full Audit Rollup
# ════════════════════════════════════════════════════════════════════

def bsc_full_audit(
    actuals_path: Optional[Path] = None,
    register_path: Optional[Path] = None,
) -> BSCFullAudit:
    coverage = audit_staff_coverage(actuals_path, register_path)
    completeness = audit_kpi_completeness(actuals_path)
    pillar = audit_pillar_canonical(actuals_path)
    weight = audit_weight_normalization(actuals_path)
    lib_align = audit_library_alignment(actuals_path)
    cascade = audit_cascade_linkage(actuals_path)
    dupes = audit_duplicate_rows(actuals_path)

    # Severity scoring
    critical = 0
    warning = 0
    info = 0

    if coverage.in_register_not_in_bsc:
        critical += 1
    if completeness.incomplete_count > 0:
        warning += 1
    if pillar.non_canonical_pillars:
        warning += 1
    if weight.not_normalized_count > 0:
        warning += 1
    if lib_align.alignment_pct < 100.0:
        warning += 1
    if cascade.cascaded_targets_not_in_bsc:
        critical += 1
    if dupes.duplicate_count > 0:
        critical += 1

    # Overall health: percent of 7 categories passing
    passing = 0
    if not coverage.in_register_not_in_bsc and not coverage.in_bsc_not_in_register:
        passing += 1
    if completeness.incomplete_count == 0:
        passing += 1
    if not pillar.non_canonical_pillars:
        passing += 1
    if weight.not_normalized_count == 0:
        passing += 1
    if lib_align.alignment_pct == 100.0:
        passing += 1
    if not cascade.cascaded_targets_not_in_bsc:
        passing += 1
    if dupes.duplicate_count == 0:
        passing += 1
    health_pct = round(passing / 7 * 100, 1)

    return BSCFullAudit(
        staff_coverage=coverage,
        kpi_completeness=completeness,
        pillar_canonical=pillar,
        weight_normalization=weight,
        library_alignment=lib_align,
        cascade_linkage=cascade,
        duplicate_rows=dupes,
        overall_health_pct=health_pct,
        issues_by_severity={
            "critical": critical,
            "warning": warning,
            "info": info,
        },
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_audit_engine self-test ─")
    import tempfile
    import re

    # Zero streamlit check
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports (React-ready)")

    # Constants
    assert len(CANONICAL_PILLARS) == 4
    print(f"  ✓ 4 canonical pillars defined")

    # Role tier classification
    assert _classify_role_tier("Chief Operating Officer") == "exec_chief"
    assert _classify_role_tier("Director Consumer & Commercial Banking (CCB)") == "director"
    assert _classify_role_tier("Head Of Retail") == "head"
    assert _classify_role_tier("Regional Head") == "regional"
    assert _classify_role_tier("Branch Manager") == "branch_manager"
    assert _classify_role_tier("Relationship Officer") == "officer"
    assert _classify_role_tier("") == "support"
    print(f"  ✓ Role tier classification works")

    # Synthetic BSC actuals (in-memory test)
    import pandas as pd
    synth = pd.DataFrame({
        "Staff Name":     ["Alice", "Alice", "Alice", "Bob", "Bob"],
        "Staff Code":     ["S001", "S001", "S001", "S002", "S002"],
        "Role":           ["Manager", "Manager", "Manager", "Officer", "Officer"],
        "Unit":           ["A", "A", "A", "B", "B"],
        "Category":       ["X", "X", "X", "Y", "Y"],
        "Staff Status":   ["Active", "Active", "Active", "Active", "Active"],
        "KPI":            ["K1", "K2", "K3", "K1", "K2"],
        "Pillar":         ["Financial", "Customer Focus",
                           "Operational Excellence", "Operational", "Financial"],
        "Weight":         [0.3, 0.4, 0.3, 0.5, 0.5],
        "Annual Target":  [100, 100, 100, 100, 100],
        "YTD_Actual":     [50, 50, 50, 50, 50],
        "Dec-25":         [10, 10, 10, 10, 10],
        "Annual Actual":  [60, 60, 60, 60, 60],
    })

    tmp = Path(tempfile.mkdtemp())
    try:
        # Write to xlsx with header row + data row pattern matching actuals format
        path = tmp / "actuals_test.xlsx"
        # Need to write a 2-row header pattern
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            # Write a blank row then headers — emulate the real file structure
            pd.DataFrame([[""] * len(synth.columns)],
                         columns=synth.columns).to_excel(
                writer, sheet_name="KPI Data", index=False, header=False)
            synth.to_excel(writer, sheet_name="KPI Data",
                          startrow=1, index=False)

        # Pillar canonical
        p = audit_pillar_canonical(actuals_path=path)
        assert "Operational" in p.non_canonical_pillars
        assert p.non_canonical_pillars["Operational"] == 1
        print(f"  ✓ Pillar canonical detects 'Operational' alias")

        # Weight normalization
        w = audit_weight_normalization(actuals_path=path)
        # Alice: 0.3+0.4+0.3 = 1.0 (normalized); Bob: 0.5+0.5 = 1.0 (normalized)
        assert w.normalized_count == 2
        assert w.not_normalized_count == 0
        print(f"  ✓ Weight normalization audit works")

        # Duplicate rows (synthetic has none)
        d = audit_duplicate_rows(actuals_path=path)
        assert d.duplicate_count == 0
        print(f"  ✓ Duplicate row audit works")

        # Full rollup
        full = bsc_full_audit(actuals_path=path)
        # Pillar non-canonical means health < 100
        assert full.overall_health_pct < 100
        assert full.issues_by_severity["warning"] >= 1
        print(f"  ✓ Full audit rollup works (health={full.overall_health_pct}%, "
              f"issues={full.issues_by_severity})")

        # JSON serialization
        json.dumps(full.to_dict())
        print(f"  ✓ Full audit JSON-serializable")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
