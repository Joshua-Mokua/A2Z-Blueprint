"""utils/staff_code.py — canonical staff-code comparison.

Real-world variants of the SAME person's code:
    FLEXCUBE writes   KE0439   (zero-padded to 4 digits)
    the roster holds  KE439
    staff type        439      (omitting the KE prefix)

This module normalises those to one comparison key so lookups match, WITHOUT changing
any stored code. Storage stays exactly as-is in the roster, in FLEXCUBE, and in CBS —
only the comparison is normalised. No migration, no foreign-key breakage.

SCOPE (deliberate): only KE-prefixed codes and bare digits are normalised. CN codes
(DSAs) and ADMIN codes are returned untouched — DSA codes are shared exactly as written
and must not be altered.

    canon("KE0439") -> "KE439"
    canon("KE439")  -> "KE439"
    canon("439")    -> "KE439"
    canon("CN020")  -> "CN020"    (untouched)
    canon("ADMIN001") -> "ADMIN001"  (untouched)
"""
from __future__ import annotations

import re
from typing import Any, Optional

_KE_RX = re.compile(r"^KE0*(\d+)$", re.I)
_BARE_RX = re.compile(r"^0*(\d+)$")


def canon(code: Any) -> str:
    """Canonical comparison key for a staff code. Never mutates stored data."""
    if code is None:
        return ""
    c = str(code).strip().upper()
    if not c:
        return ""

    m = _KE_RX.match(c)
    if m:
        return f"KE{int(m.group(1))}"

    # A bare number is assumed to be a KE staff code with the prefix omitted —
    # this is what staff type when they skip the "KE".
    m = _BARE_RX.match(c)
    if m:
        return f"KE{int(m.group(1))}"

    # CN (DSA) and ADMIN codes are returned exactly as given.
    return c


def same_staff(a: Any, b: Any) -> bool:
    """True if two codes refer to the same person, across format variants."""
    ca, cb = canon(a), canon(b)
    return bool(ca) and ca == cb


def canon_set(codes) -> set:
    """Canonicalise an iterable of codes (for visible-set membership tests)."""
    return {canon(c) for c in (codes or []) if canon(c)}
