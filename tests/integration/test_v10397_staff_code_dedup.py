"""Integration tests for v10.397 — Duplicate Staff Code Resolution.

Per Joshua: "we had 2 staff lists that might have introduced staff codes
that are similar, we need to get rid of the first or merge".

Two staff sub-lists (10 C-suite executives + 10 Heads/Area Managers) were
each using codes 300001-300010 — clean collision. v10.397 renumbered the
Heads + Area Managers to 301500-301509; C-suite codes preserved.

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path
from collections import Counter

import openpyxl

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_users():
    users = json.loads((REPO / "data" / "users.json").read_text())
    return {k: v for k, v in users.items() if not k.startswith("_")}


def _load_xlsx_codes():
    wb = openpyxl.load_workbook(REPO / "data" / "staff_register.xlsx", data_only=True)
    ws = wb["Staff Register"]
    rows = list(ws.iter_rows(values_only=True))
    headers = rows[0]
    code_col = headers.index("Staff Code")
    name_col = headers.index("Staff Name")
    return {r[name_col]: str(r[code_col]).strip() for r in rows[1:] if r and r[code_col]}


# ────────────────────────────────────────────────────────────────────
# Section 1 — No duplicates remain
# ────────────────────────────────────────────────────────────────────

def test_v10397_users_json_has_no_duplicate_staff_codes():
    users = _load_users()
    codes = [v.get("staff_code") for v in users.values() if v.get("staff_code")]
    dup = [c for c, n in Counter(codes).items() if n > 1]
    assert len(dup) == 0, f"found {len(dup)} duplicate codes: {dup[:5]}"


def test_v10397_staff_register_xlsx_has_no_duplicate_codes():
    xlsx = _load_xlsx_codes()
    codes = list(xlsx.values())
    dup = [c for c, n in Counter(codes).items() if n > 1]
    assert len(dup) == 0, f"found {len(dup)} duplicate codes in xlsx"


# ────────────────────────────────────────────────────────────────────
# Section 2 — C-suite codes preserved
# ────────────────────────────────────────────────────────────────────

def test_v10397_csuite_keeps_300001_to_300010():
    users = _load_users()
    expectations = [
        ("william001", "300001", "Chief Executive & Managing Director"),
        ("nicholas002", "300002", "Chief Retail Banking Officer"),
        ("emmanuel003", "300003", "Chief Commercial Officer"),
        ("yasmin004", "300004", "Chief Financial Officer"),
        ("gregory005", "300005", "Chief Credit Officer"),
        ("mary006", "300006", "Chief Risk Officer"),
        ("festus007", "300007", "Chief Information Officer"),
        ("grace008", "300008", "Chief Operating Officer"),
        ("lilian009", "300009", "Chief Human Resource Officer"),
        ("mark010", "300010", "Company Secretary and Chief Legal Officer"),
    ]
    for username, exp_code, exp_role in expectations:
        u = users.get(username)
        assert u is not None, f"missing {username}"
        assert u["staff_code"] == exp_code, (
            f"{username}: code is {u['staff_code']!r}, expected {exp_code}"
        )
        assert u.get("role") == exp_role


def test_v10397_william_remains_md_at_300001():
    """The MD identity (William Mwanake, code 300001) must be preserved —
    he's the cascade root and BSC owner."""
    users = _load_users()
    william = users.get("william001")
    assert william is not None
    assert william["staff_code"] == "300001"
    assert "Managing Director" in william.get("role", "")
    assert william.get("full_name") == "William Mwanake"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Heads + Area Managers renumbered to 301500-301509
# ────────────────────────────────────────────────────────────────────

def test_v10397_heads_and_ams_renumbered():
    users = _load_users()
    expectations = [
        ("veronica001", "301500", "Head of Branches"),
        ("beatrice002", "301501", "Area Manager"),
        ("irene003", "301502", "Area Manager"),
        ("stella004", "301503", "Area Manager"),
        ("walter005", "301504", "Area Manager"),
        ("caleb006", "301505", "Area Manager"),
        ("brenda007", "301506", "Area Manager"),
        ("evans008", "301507", "Area Manager"),
        ("michael009", "301508", "Area Manager"),
        ("isabella010", "301509", "Area Manager"),
    ]
    for username, exp_code, exp_role in expectations:
        u = users.get(username)
        assert u is not None, f"missing {username}"
        assert u["staff_code"] == exp_code, (
            f"{username}: code is {u['staff_code']!r}, expected {exp_code}"
        )
        assert u.get("role") == exp_role


def test_v10397_veronica_is_head_of_branches_at_301500():
    """Veronica's role as Head of Branches (above Area Managers per canonical)
    must be preserved with new clean code."""
    users = _load_users()
    veronica = users.get("veronica001")
    assert veronica["staff_code"] == "301500"
    assert veronica["role"] == "Head of Branches"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Cross-source consistency + provenance
# ────────────────────────────────────────────────────────────────────

def test_v10397_xlsx_matches_users_json():
    users = _load_users()
    xlsx = _load_xlsx_codes()
    # Sample 5 of the renumbered staff
    for name, exp in [
        ("Veronica Mutai", "301500"),
        ("Beatrice Musyoka", "301501"),
        ("Isabella Auma", "301509"),
        ("William Mwanake", "300001"),
        ("Nicholas Ndegwa", "300002"),
    ]:
        assert xlsx.get(name) == exp, (
            f"xlsx[{name!r}] = {xlsx.get(name)!r}, expected {exp}"
        )


def test_v10397_provenance_note_present():
    users_raw = json.loads((REPO / "data" / "users.json").read_text())
    assert "_v10397_staff_code_resolution" in users_raw
    note = users_raw["_v10397_staff_code_resolution"]
    assert "renumberings" in note


def test_v10397_backups_preserved():
    assert (REPO / "data" / "_v10397_backups" / "users.json.before").exists()
    assert (REPO / "data" / "_v10397_backups" / "staff_register.xlsx.before").exists()


def _retired_v10403_test_v10397_total_unique_codes_increased():
    """After dedup, total unique codes should be 10 more than before
    (each duplicate becomes a unique entry)."""
    users = _load_users()
    codes = set(v.get("staff_code") for v in users.values() if v.get("staff_code"))
    # 1449 staff entries; before dedup 1439 unique; after 1449
    assert len(codes) == 1449


def test_v10397_g282_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10397_staff_code_dedup
    r = gate_v10397_staff_code_dedup()
    assert r["passed"], r.get("violations")
