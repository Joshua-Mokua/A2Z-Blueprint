"""utils/fx_engine.py — Operational FX foundation (Phase 4-1).

Admin-maintained FX rate store + resolver + money normalizer + LCY/FCY
classification. This is the OPERATIONAL booking layer (mid/buy/sell rates for
loans, deposits, deals) and is deliberately separate from the IAS-21
consolidation FX engine in consolidated_tb_engine.py (CLOSING/AVERAGE/HISTORICAL).

Design contract (see docs/PHASE4_SECURED_LENDING_DESIGN.md §8):
  - Base/functional currency = KES. KES always resolves to rate_to_kes = 1.
  - Every monetary record can be normalized to:
        amount_native, currency, fx_rate, amount_kes,
        fx_rate_date, fx_rate_source, currency_book (LCY|FCY)
  - Booking stamps the rate USED so historical amounts never drift when the
    admin updates rates later.
  - Resolution = latest ACTIVE rate with effective_date <= as_of, for the
    requested currency + rate_type.

No hard dependency on streamlit / psycopg2 — pure stdlib so it is testable in
isolation and safe to import anywhere.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

BASE_CURRENCY = "KES"
VALID_RATE_TYPES = ("mid", "buy", "sell")

# Resolve the data dir the same way the rest of the app does, but tolerate
# being imported from anywhere (tests, scripts, API).
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_FX_PATH = _DATA_DIR / "fx_rates.json"


class FxRateError(Exception):
    """Raised for genuine FX problems (missing rate, bad input). Never used to
    mask parse errors — those propagate so a corrupt rate file is loud."""


@dataclass(frozen=True)
class NormalizedMoney:
    amount_native: Decimal
    currency: str
    fx_rate: Decimal
    amount_kes: Decimal
    fx_rate_date: str          # ISO date the rate was effective
    fx_rate_source: str
    currency_book: str         # "LCY" | "FCY"

    def as_dict(self) -> dict:
        return {
            "amount_native":  float(self.amount_native),
            "currency":       self.currency,
            "fx_rate":        float(self.fx_rate),
            "amount_kes":     float(self.amount_kes),
            "fx_rate_date":   self.fx_rate_date,
            "fx_rate_source": self.fx_rate_source,
            "currency_book":  self.currency_book,
        }


def currency_book(currency: Optional[str]) -> str:
    """LCY for the base currency (KES), FCY for everything else."""
    cur = (str(currency or "").strip() or BASE_CURRENCY).upper()
    return "LCY" if cur == BASE_CURRENCY else "FCY"


def _to_decimal(v, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        raise FxRateError(f"{field} is not a valid number: {v!r}")


def _as_iso(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.date().isoformat() if isinstance(d, datetime) else d.isoformat()
    return str(d or "").strip()


class FxRateStore:
    """JSON-backed, admin-maintainable FX rate table.

    File shape (data/fx_rates.json):
        {
          "base_currency": "KES",
          "rates": [
            {"currency","rate_to_kes","rate_type","effective_date",
             "source","entered_by","active"}
          ]
        }
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_FX_PATH
        self._rates: List[dict] = []
        self._base = BASE_CURRENCY
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            # Absent file is a legitimate first-run state: start with just the
            # base currency. (Distinct from a corrupt file, which raises.)
            self._rates = []
            self._base = BASE_CURRENCY
            return
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            self._rates = []
            return
        data = json.loads(raw)  # corrupt JSON raises loudly — by design
        self._base = str(data.get("base_currency", BASE_CURRENCY)).upper()
        self._rates = list(data.get("rates", []))

    def save(self) -> None:
        payload = {
            "_doc": "Operational FX rates (admin-maintained). KES is base "
                    "(rate_to_kes=1). Resolver picks latest active rate with "
                    "effective_date <= as_of for currency+rate_type.",
            "base_currency": self._base,
            "rates": self._rates,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ---- queries -----------------------------------------------------
    def list_rates(self, currency: Optional[str] = None,
                   active_only: bool = False) -> List[dict]:
        out = self._rates
        if currency:
            cur = currency.upper()
            out = [r for r in out if str(r.get("currency", "")).upper() == cur]
        if active_only:
            out = [r for r in out if r.get("active", True)]
        return list(out)

    def resolve_rate(self, currency: Optional[str], as_of=None,
                     rate_type: str = "mid") -> Decimal:
        """Latest active rate_to_kes for currency+rate_type with
        effective_date <= as_of. KES short-circuits to 1. Raises FxRateError
        if no rate is found for a non-base currency."""
        cur = (str(currency or "").strip() or self._base).upper()
        if cur == self._base:
            return Decimal("1")
        if rate_type not in VALID_RATE_TYPES:
            raise FxRateError(f"rate_type must be one of {VALID_RATE_TYPES}, "
                              f"got {rate_type!r}")
        as_of_iso = _as_iso(as_of) or date.today().isoformat()
        candidates = [
            r for r in self._rates
            if str(r.get("currency", "")).upper() == cur
            and str(r.get("rate_type", "mid")) == rate_type
            and r.get("active", True)
            and _as_iso(r.get("effective_date", "")) <= as_of_iso
        ]
        if not candidates:
            raise FxRateError(
                f"No active {rate_type} rate for {cur} as of {as_of_iso}. "
                f"Admin must add it to {self.path.name}.")
        best = max(candidates, key=lambda r: _as_iso(r.get("effective_date", "")))
        return _to_decimal(best.get("rate_to_kes"), "rate_to_kes")

    # ---- mutation (admin) -------------------------------------------
    def upsert_rate(self, currency: str, rate_to_kes, effective_date,
                    rate_type: str = "mid", source: str = "admin",
                    entered_by: str = "admin", active: bool = True) -> dict:
        """Add or replace the rate for (currency, rate_type, effective_date).
        Keeps history: distinct effective_dates coexist."""
        cur = str(currency or "").strip().upper()
        if not cur:
            raise FxRateError("currency is required")
        if rate_type not in VALID_RATE_TYPES:
            raise FxRateError(f"rate_type must be one of {VALID_RATE_TYPES}")
        rate = _to_decimal(rate_to_kes, "rate_to_kes")
        if rate <= 0:
            raise FxRateError("rate_to_kes must be > 0")
        eff = _as_iso(effective_date)
        row = {
            "currency": cur, "rate_to_kes": float(rate), "rate_type": rate_type,
            "effective_date": eff, "source": source, "entered_by": entered_by,
            "active": bool(active),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        # replace any existing row with same (currency, rate_type, effective_date)
        self._rates = [
            r for r in self._rates
            if not (str(r.get("currency", "")).upper() == cur
                    and str(r.get("rate_type", "mid")) == rate_type
                    and _as_iso(r.get("effective_date", "")) == eff)
        ]
        self._rates.append(row)
        return row


# ---- module-level convenience -------------------------------------------
def normalize_money(amount_native, currency: Optional[str], as_of=None,
                    rate_type: str = "mid",
                    store: Optional[FxRateStore] = None) -> NormalizedMoney:
    """Convert a native amount into the full normalized money set. Stamps the
    rate used. KES is pass-through (rate 1, LCY)."""
    st = store or FxRateStore()
    amt = _to_decimal(amount_native, "amount_native")
    cur = (str(currency or "").strip() or BASE_CURRENCY).upper()
    rate = st.resolve_rate(cur, as_of=as_of, rate_type=rate_type)
    as_of_iso = _as_iso(as_of) or date.today().isoformat()
    return NormalizedMoney(
        amount_native=amt,
        currency=cur,
        fx_rate=rate,
        amount_kes=(amt * rate).quantize(Decimal("0.01")),
        fx_rate_date=as_of_iso,
        fx_rate_source=("system" if cur == BASE_CURRENCY else "admin_table"),
        currency_book=currency_book(cur),
    )


def stamp_money_fields(record: dict, amount_key: str = "deal_value",
                       currency_key: str = "currency", as_of=None,
                       store: Optional[FxRateStore] = None) -> dict:
    """Additively stamp the normalized money set onto a record (in place).

    Adds: currency (upper), currency_book, fx_rate, amount_kes, fx_rate_date,
    fx_rate_source. RESILIENT — never raises: if the rate is missing or the
    amount is unparseable, currency_book (always computable) is still set and the
    fx_* fields are left unresolved (source='unresolved'). This keeps booking
    paths safe for exotic/unconfigured currencies.
    """
    cur = str(record.get(currency_key) or BASE_CURRENCY).upper()
    record["currency"] = cur
    record["currency_book"] = currency_book(cur)
    amt = record.get(amount_key)
    try:
        m = normalize_money(amt if amt is not None else 0, cur,
                            as_of=as_of, store=store)
        record["fx_rate"] = float(m.fx_rate)
        record["amount_kes"] = float(m.amount_kes)
        record["fx_rate_date"] = m.fx_rate_date
        record["fx_rate_source"] = m.fx_rate_source
    except Exception:
        record.setdefault("fx_rate", None)
        record.setdefault("amount_kes", None)
        record.setdefault("fx_rate_date", None)
        record["fx_rate_source"] = "unresolved"
    return record
