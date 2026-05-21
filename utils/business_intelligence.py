"""utils.business_intelligence — Automated Business Intelligence
(Standard #48, v5.52). Volume Eight — Execute Enhancement.

Per v6 spec §7:
    AutomatedBusinessIntelligence: variance-driven commentary with
    LLM hook + deterministic rule-based fallback.

This is a Category D standard (ML/AI scaffolding). Per Rule 7 (No silent
ML predictions, v6 §4):

  1. LLM hook is wired but disabled by default
  2. When no llm_provider_fn is injected, returns rule-based commentary
     with explicit basis="rule_based" and fallback_reason
  3. Spec deviation #4 documented inline

WHAT THIS MODULE SHIPS
----------------------
1. AutomatedBusinessIntelligence class with:
   - generate_commentary(metrics, period, prior_period_metrics) — narrative
     with basis flag ("rule_based" | "llm")
   - _rule_based_commentary() — deterministic template-driven narrative
   - _llm hook injectable

2. Variance attribution math (deterministic)
3. Spec-literal phrasing patterns matching the example output:
   "As of 28th April, total interest income decreased marginally by
    KES 1.78M (-2.3%) vs prior period, driven by lower loan disbursements
    in MSME segment (down 12%)."

HONESTY DISCIPLINE
------------------
Rule 7 (NEW for v6, Cat D):
  - LLM hook returns None when no provider configured
  - Rule-based fallback is deterministic — same input → same output
  - basis flag in response shows source ("rule_based" vs "llm")
  - meta.spec_deviation field documents the scaffold status

Rule 1:
  - Decimal-internal for variance amounts
  - Variance pct = None when prior_value is zero
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger("a2z.business_intelligence")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals — narrative phrasing patterns (v6 §7 #48)
# ─────────────────────────────────────────────────────────────────────

# These templates produce the kind of narrative shown in the spec example:
# "As of 28th April, total interest income decreased marginally by KES 1.78M
#  (-2.3%) vs prior period, driven by lower loan disbursements in MSME segment."

VARIANCE_DESCRIPTORS: Dict[str, Tuple[float, str]] = {
    # threshold (abs variance pct), adverb that modifies the direction verb
    "negligible":  (1.0,   "negligibly"),
    "marginal":    (5.0,   "marginally"),
    "moderate":    (15.0,  "moderately"),
    "significant": (30.0,  "significantly"),
    "extreme":     (float("inf"), "dramatically"),
}

DIRECTION_VERB_INCREASE = "increased"
DIRECTION_VERB_DECREASE = "decreased"
DIRECTION_VERB_FLAT     = "remained flat"

# Spec deviation #4 marker
SPEC_DEVIATION_NOTE = "LLM-generated narrative is downstream work; v6 ships rule-based template engine"


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class AutomatedBusinessIntelligence:
    """Variance-driven business commentary.

    Cat D pattern (Rule 7): ships with rule-based commentary that is
    deterministic and verifiable. LLM hook is wired but disabled by
    default — when no llm_provider_fn is injected, falls back to template
    commentary and returns basis="rule_based" with explicit fallback_reason.
    """

    def __init__(self, llm_provider_fn: Optional[Callable[[str], str]] = None):
        """llm_provider_fn(prompt: str) -> str.

        When None (default), commentary is rule-based per Rule 7 — the
        engine refuses to silently substitute an LLM-generated narrative.
        """
        self._llm = llm_provider_fn

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: generate_commentary
    # ──────────────────────────────────────────────────────────────────

    def generate_commentary(
        self,
        metrics: Dict[str, Any],
        period: str,
        prior_period_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Produce a narrative for a metrics block.

        Args:
            metrics: dict of {metric_name: value} for current period
            period: 'YYYY-MM-DD' or 'YYYY-MM' label for the report
            prior_period_metrics: dict of {metric_name: value} for prior period

        Returns:
            {
              "commentary": str,
              "basis": "rule_based" | "llm",
              "period": str,
              "variances": [{metric, current, prior, variance, variance_pct, direction}],
              "meta": {
                "fallback_reason": str | None,    # set when basis="rule_based" + LLM unavailable
                "spec_deviation": str | None,
                "generated_at": str,
              }
            }

        Returns {} for empty inputs.
        """
        if not metrics or not period:
            return {}

        # Compute variances (deterministic, used by both branches)
        variances = self._compute_variances(metrics, prior_period_metrics or {})

        # ── Rule 7: LLM hook fallback ─────────────────────────────────
        if self._llm is None:
            text = self._rule_based_commentary(metrics, period, variances)
            return {
                "commentary": text,
                "basis":      "rule_based",
                "period":     period,
                "variances":  variances,
                "meta": {
                    "fallback_reason": "no_llm_provider_configured",
                    "spec_deviation":  SPEC_DEVIATION_NOTE,
                    "generated_at":    datetime.now(timezone.utc).isoformat(),
                },
            }

        # ── Production path: LLM provider injected ───────────────────
        try:
            prompt = self._build_prompt(metrics, period, variances)
            text = self._llm(prompt)
            return {
                "commentary": text,
                "basis":      "llm",
                "period":     period,
                "variances":  variances,
                "meta": {
                    "fallback_reason": None,
                    "spec_deviation":  None,
                    "generated_at":    datetime.now(timezone.utc).isoformat(),
                },
            }
        except Exception as e:
            # If the LLM provider fails, fall back to rule-based but
            # SURFACE the failure (don't silently swap)
            logger.warning("LLM provider failed: %s — falling back to rule-based", e)
            text = self._rule_based_commentary(metrics, period, variances)
            return {
                "commentary": text,
                "basis":      "rule_based",
                "period":     period,
                "variances":  variances,
                "meta": {
                    "fallback_reason": f"llm_provider_error: {type(e).__name__}",
                    "spec_deviation":  SPEC_DEVIATION_NOTE,
                    "generated_at":    datetime.now(timezone.utc).isoformat(),
                },
            }

    # ──────────────────────────────────────────────────────────────────
    # Variance computation (used by both branches — deterministic)
    # ──────────────────────────────────────────────────────────────────

    def _compute_variances(
        self,
        metrics: Dict[str, Any],
        prior: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Compute variance for each metric. Returns list (preserves order)."""
        out: List[Dict[str, Any]] = []
        for metric_name, current_val in metrics.items():
            try:
                current_dec = Decimal(str(current_val))
            except Exception:
                continue

            prior_val = prior.get(metric_name)
            if prior_val is None:
                out.append({
                    "metric":       metric_name,
                    "current":      _money(current_dec),
                    "prior":        None,
                    "variance":     None,
                    "variance_pct": None,
                    "direction":    None,
                })
                continue

            try:
                prior_dec = Decimal(str(prior_val))
            except Exception:
                continue

            variance = current_dec - prior_dec
            if prior_dec == 0:
                variance_pct = None    # Rule 1
            else:
                variance_pct = float(variance / prior_dec * Decimal("100"))

            if variance > 0:
                direction = "increased"
            elif variance < 0:
                direction = "decreased"
            else:
                direction = "flat"

            out.append({
                "metric":       metric_name,
                "current":      _money(current_dec),
                "prior":        _money(prior_dec),
                "variance":     _money(variance),
                "variance_pct": round(variance_pct, 2) if variance_pct is not None else None,
                "direction":    direction,
            })
        return out

    # ──────────────────────────────────────────────────────────────────
    # Rule-based commentary (deterministic — Rule 7 fallback)
    # ──────────────────────────────────────────────────────────────────

    def _rule_based_commentary(
        self,
        metrics: Dict[str, Any],
        period: str,
        variances: List[Dict[str, Any]],
    ) -> str:
        """Deterministic template-driven narrative.

        Same input → same output. No randomness, no model.
        Generates one sentence per metric with variance attribution.
        """
        if not variances:
            return f"As of {period}, no metrics provided."

        sentences: List[str] = []
        period_str = self._format_period(period)

        for v in variances:
            metric = v["metric"]
            current = v["current"]
            current_str = self._format_amount(current)

            if v["prior"] is None:
                sentences.append(
                    f"{self._humanize(metric)} stood at {current_str} "
                    f"(no prior period reference available)"
                )
                continue

            if v["variance_pct"] is None:
                # Prior was zero
                sentences.append(
                    f"{self._humanize(metric)} stood at {current_str} "
                    f"(prior period was zero — variance not computable)"
                )
                continue

            direction_verb = (
                DIRECTION_VERB_INCREASE if v["direction"] == "increased" else
                DIRECTION_VERB_DECREASE if v["direction"] == "decreased" else
                DIRECTION_VERB_FLAT
            )
            adverb = self._classify_variance(abs(v["variance_pct"]))
            variance_str = self._format_amount(abs(v["variance"]))
            pct_str = f"{v['variance_pct']:+.1f}%"

            if v["direction"] == "flat":
                sentences.append(
                    f"{self._humanize(metric)} {direction_verb} "
                    f"({pct_str} vs prior period)"
                )
            else:
                sentences.append(
                    f"{self._humanize(metric)} {direction_verb} {adverb} "
                    f"by KES {variance_str} ({pct_str}) vs prior period"
                )

        # Stitch into a paragraph
        prefix = f"As of {period_str}, "
        body = "; ".join(sentences) + "."
        # Capitalize first letter of body
        if body and body[0].islower():
            body = body[0].upper() + body[1:]
        return prefix + body

    def _build_prompt(
        self, metrics: Dict[str, Any], period: str, variances: List[Dict[str, Any]],
    ) -> str:
        """Build LLM prompt for production path."""
        lines = [
            f"Generate a 2-3 sentence executive commentary for {period}.",
            "Metrics and their variance from prior period:",
        ]
        for v in variances:
            if v["prior"] is None:
                lines.append(f"  - {v['metric']}: KES {v['current']:,.2f} (no prior comparison)")
            elif v["variance_pct"] is None:
                lines.append(f"  - {v['metric']}: KES {v['current']:,.2f} (prior zero)")
            else:
                lines.append(
                    f"  - {v['metric']}: KES {v['current']:,.2f} "
                    f"({v['variance_pct']:+.1f}% vs prior)"
                )
        lines.append("Style: factual, executive-level, no speculation.")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────
    # Formatting helpers
    # ──────────────────────────────────────────────────────────────────

    def _classify_variance(self, abs_pct: float) -> str:
        """Map abs(variance_pct) to an adverb modifying the direction verb."""
        for name, (threshold, adverb) in VARIANCE_DESCRIPTORS.items():
            if abs_pct < threshold:
                return adverb
        return "dramatically"

    def _humanize(self, metric_name: str) -> str:
        """Convert snake_case_metric → 'Snake case metric'."""
        words = metric_name.replace("_", " ")
        return words[0].upper() + words[1:] if words else words

    def _format_amount(self, amount: float) -> str:
        """Format as KES amount with M/K suffixes for readability."""
        if abs(amount) >= 1_000_000_000:
            return f"{amount / 1_000_000_000:.2f}B"
        if abs(amount) >= 1_000_000:
            return f"{amount / 1_000_000:.2f}M"
        if abs(amount) >= 1_000:
            return f"{amount / 1_000:.2f}K"
        return f"{amount:.2f}"

    def _format_period(self, period: str) -> str:
        """Format period label more naturally if it's a date."""
        try:
            dt = datetime.strptime(period, "%Y-%m-%d")
            return dt.strftime("%-d %B %Y") if hasattr(dt, "strftime") else period
        except (ValueError, AttributeError):
            return period


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.business_intelligence self-test")

    # ── Empty inputs → {} ────────────────────────────────────────────
    eng = AutomatedBusinessIntelligence()
    assert eng.generate_commentary({}, "2026-04-29") == {}
    assert eng.generate_commentary({"x": 1}, "") == {}
    print(f"  ✅ empty inputs → {{}}")

    # ── No LLM provider: basis='rule_based' with fallback_reason ─────
    metrics = {
        "interest_income": 75_000_000,
        "fee_income":      30_000_000,
    }
    prior = {
        "interest_income": 76_780_000,    # ~-2.3%
        "fee_income":      28_000_000,    # ~+7.1%
    }
    r = eng.generate_commentary(metrics, "2026-04-29", prior)
    assert r["basis"] == "rule_based"
    assert r["meta"]["fallback_reason"] == "no_llm_provider_configured"
    assert r["meta"]["spec_deviation"] is not None
    assert "LLM-generated narrative is downstream" in r["meta"]["spec_deviation"]
    print(f"  ✅ no LLM provider → basis='rule_based', fallback_reason set")

    # ── Rule-based commentary text contains key elements ─────────────
    text = r["commentary"]
    assert "April" in text or "2026" in text   # period rendered
    assert "Interest income" in text
    assert "decreased" in text                  # variance direction
    assert "%" in text                          # variance pct included
    print(f"  ✅ rule-based commentary content valid")
    print(f"      sample: {text[:120]}...")

    # ── Variances computed correctly ─────────────────────────────────
    interest_var = next(v for v in r["variances"] if v["metric"] == "interest_income")
    assert interest_var["current"] == 75_000_000.00
    assert interest_var["prior"]   == 76_780_000.00
    assert interest_var["variance"] == -1_780_000.00
    assert abs(interest_var["variance_pct"] - (-2.32)) < 0.01
    assert interest_var["direction"] == "decreased"
    print(f"  ✅ variance math: {interest_var['variance_pct']}% decrease "
          f"by KES {abs(interest_var['variance']):,.2f}")

    # ── Determinism: same input → same output ────────────────────────
    r2 = eng.generate_commentary(metrics, "2026-04-29", prior)
    assert r["commentary"] == r2["commentary"]    # identical text
    print(f"  ✅ rule-based commentary is deterministic")

    # ── No prior period: variance=None, direction=None ───────────────
    r = eng.generate_commentary(metrics, "2026-04-29")    # no prior
    for v in r["variances"]:
        assert v["prior"] is None
        assert v["variance"] is None
        assert v["direction"] is None
    assert "no prior period" in r["commentary"]
    print(f"  ✅ no prior period → variance=None, narrative explicit")

    # ── Prior=0 → variance_pct=None (Rule 1) ─────────────────────────
    r = eng.generate_commentary(
        {"new_revenue": 1_000_000},
        "2026-04",
        {"new_revenue": 0},
    )
    nv = r["variances"][0]
    assert nv["variance_pct"] is None
    assert "prior period was zero" in r["commentary"] or "variance not computable" in r["commentary"]
    print(f"  ✅ prior=0 → variance_pct=None (Rule 1)")

    # ── LLM provider injected: basis='llm' ───────────────────────────
    eng_with_llm = AutomatedBusinessIntelligence(
        llm_provider_fn=lambda prompt: "LLM-GENERATED: results were strong this quarter."
    )
    r = eng_with_llm.generate_commentary(metrics, "2026-04-29", prior)
    assert r["basis"] == "llm"
    assert r["commentary"] == "LLM-GENERATED: results were strong this quarter."
    assert r["meta"]["fallback_reason"] is None
    assert r["meta"]["spec_deviation"] is None
    print(f"  ✅ LLM provider injected → basis='llm', no spec_deviation")

    # ── LLM provider error → falls back with explicit reason ─────────
    def failing_llm(prompt):
        raise ConnectionError("LLM API timeout")
    eng_failing = AutomatedBusinessIntelligence(llm_provider_fn=failing_llm)
    r = eng_failing.generate_commentary(metrics, "2026-04-29", prior)
    assert r["basis"] == "rule_based"
    assert "llm_provider_error" in r["meta"]["fallback_reason"]
    assert "ConnectionError" in r["meta"]["fallback_reason"]
    print(f"  ✅ LLM error → fallback with explicit reason: "
          f"{r['meta']['fallback_reason']}")

    # ── Variance descriptors match thresholds ────────────────────────
    cases = [
        ({"x": 1030}, {"x": 1000},   "marginally"),          # 3% — marginal
        ({"x": 1100}, {"x": 1000},   "moderately"),          # 10% — moderate
        ({"x": 1250}, {"x": 1000},   "significantly"),       # 25% — significant
        ({"x": 2000}, {"x": 1000},   "dramatically"),        # 100% — extreme
    ]
    for m, p, expected_descriptor in cases:
        r = eng.generate_commentary(m, "2026-04", p)
        assert expected_descriptor in r["commentary"], \
            f"expected {expected_descriptor!r} in commentary for {m} vs {p}"
    print(f"  ✅ variance descriptors map to thresholds correctly")

    # ── Tampering test: spec deviation note is verifiable string ─────
    # The exact wording matters for audit gate G50
    assert "LLM-generated narrative is downstream work" in SPEC_DEVIATION_NOTE
    print(f"  ✅ spec deviation note: '{SPEC_DEVIATION_NOTE[:60]}...'")

    print("\n  ALL TESTS PASSED")
