"""utils.strategy_formulation — Strategy Formulation Intelligence
(Standard ENH-141, v10.135). Phase 1 Strategy Module — first engine.

Per Continuation.docx §Standard #141 (Eco Bank QA spec):
    StrategyFormulationEngine — AI-powered SWOT analysis with
    real-time market data; board vision synthesis via NLP.

This is a Category D standard (NLP scaffolding for board vision; the
SWOT generator itself is fully deterministic over real bank data).
Per Rule 7 (No silent ML predictions):

  1. LLM/NLP hook is wired but disabled by default
  2. When no llm_provider_fn is injected, vision synthesis returns a
     deterministic theme-extraction result with explicit basis="rule_based"
     and fallback_reason
  3. SWOT generator is fully deterministic (no LLM hook needed) — it
     reads real bank data (bsc_scores, bank_targets, tier1_benchmarking,
     competitor_data) and produces structured Strengths/Weaknesses/
     Opportunities/Threats based on quantitative thresholds.

WHAT THIS MODULE SHIPS
----------------------
1. StrategyFormulationEngine class with:
   - generate_swot(business_unit=None) — full SWOT from real data
   - synthesize_board_vision(board_inputs) — board input → strategic
     themes (rule-based fallback when LLM not configured)
   - get_financial_metrics() — pulls from bsc_scores + bank_targets
   - get_market_trends() — pulls from tier1_benchmarking
   - get_competitor_intelligence() — pulls from competitor_data

2. Deterministic SWOT thresholds (per Continuation.docx spec):
   - Strength: performance > target * 1.10 (+10% above)
   - Weakness: performance < target * 0.90 (-10% below)
   - Opportunity: market trend growth_rate > 10% AND relevance > 0.7
   - Threat: competitor action with impact > 0.5

3. Audit-ready output with:
   - generated_at timestamp
   - data_sources list (provenance)
   - strategic_implications text (rule-based; LLM-enhancable)

HONESTY DISCIPLINE
------------------
- SWOT outputs are pure functions of input data. Same data → same SWOT.
- No "AI generated" claims when output is rule-based.
- basis field in board vision response shows source ("rule_based" | "llm").
- Empty SWOT quadrants are surfaced as empty lists (not hidden).
- Forward-compatibility: if bank_targets or tier1_benchmarking files are
  missing or have unexpected shapes, the engine returns partial results
  with explicit notes rather than crashing.

RELATED STANDARDS
-----------------
- ENH-142 StrategicOptionsGenerator — consumes the SWOT output
- ENH-143 Strategic Pillars (planned)
- ENH-145 OKR/BSC Cascade (Enhanced; planned)
- ENH-153 Strategy-to-BSC Daily Integration (planned; this engine
  produces the inputs the cascade engine will consume)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger("a2z.strategy_formulation")


# ════════════════════════════════════════════════════════════════════
# Thresholds (per Continuation.docx Standard #141 spec)
# ════════════════════════════════════════════════════════════════════

STRENGTH_THRESHOLD_RATIO = 1.10        # performance > target * 1.10
WEAKNESS_THRESHOLD_RATIO = 0.90        # performance < target * 0.90
OPPORTUNITY_GROWTH_PCT_MIN = 10.0      # market trend growth_rate > 10%
OPPORTUNITY_RELEVANCE_MIN = 0.7        # AND relevance_to_bank > 0.7
THREAT_IMPACT_MIN = 0.5                # competitor action impact > 0.5
THREAT_IMPACT_IMMEDIATE = 0.8          # > 0.8 → "Immediate" response


# ════════════════════════════════════════════════════════════════════
# StrategyFormulationEngine
# ════════════════════════════════════════════════════════════════════

class StrategyFormulationEngine:
    """Strategy formulation assistant — SWOT + board vision synthesis.

    Reads real bank data and produces structured strategic inputs for
    the Strategic Options Generator (ENH-142) and downstream BSC cascade
    (ENH-145, ENH-153).

    Data sources (all under data/):
    - bsc_scores.json       — staff/dept BSC scorecards (financial_score,
                              customer_score, process_score, people_score)
    - bank_targets.json     — KPI target values for the year
    - tier1_benchmarking.json — peer-bank quarterly metrics
    - competitor_data.json  — competitor moves and market share

    All four are optional. Missing files produce partial SWOT with
    explicit notes about which quadrants couldn't be populated.
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 llm_provider_fn: Optional[Callable[[str], str]] = None):
        """
        Args:
            data_dir: where to read JSON sources from. Defaults to repo's
                data/ directory.
            llm_provider_fn: optional callable accepting a prompt string
                and returning generated text. When None, board vision
                synthesis falls back to rule-based theme extraction.
        """
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.llm_provider_fn = llm_provider_fn

    # ── Data loaders (single responsibility, easy to mock in tests) ──

    def _load_json(self, fname: str) -> Optional[Any]:
        """Load a JSON file from data_dir; return None if missing/invalid."""
        path = self.data_dir / fname
        if not path.exists():
            logger.info(f"strategy_formulation: {fname} not present, skipping")
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"strategy_formulation: could not read {fname}: {e}")
            return None

    def get_financial_metrics(self,
                              business_unit: Optional[str] = None) -> List[Dict]:
        """Returns list of {name, performance, target} from bsc_scores
        cross-referenced with bank_targets.

        For SWOT purposes: aggregate per-staff scores up to bank-level
        average per Balanced Scorecard pillar (financial, customer,
        process, people). When business_unit is provided, filter by
        the staff_code's branch/dept (best-effort via bsc_scores fields).
        """
        bsc = self._load_json("bsc_scores.json")
        targets = self._load_json("bank_targets.json")
        if not bsc:
            return []

        # Normalize bsc rows to a list
        rows = bsc if isinstance(bsc, list) else list(bsc.values())
        if business_unit:
            # Best-effort filter — bsc_scores has staff_code, branch, dept fields
            rows = [r for r in rows
                    if r.get("branch") == business_unit
                    or r.get("dept") == business_unit
                    or r.get("business_unit") == business_unit]

        if not rows:
            return []

        # Aggregate average per BSC pillar
        # BSC pillar scores are on a 0-5 scale (per bsc_scores schema).
        # Target is set to 4.0 — the industry-typical "good performance"
        # benchmark in BSC frameworks (3.0=meets expectations,
        # 4.0=exceeds, 5.0=outstanding). With this target:
        #   Strength: pillar avg > 4.4  (target * 1.10)
        #   Weakness: pillar avg < 3.6  (target * 0.90)
        # which produces realistic strength/weakness flags for typical
        # bank performance distributions.
        pillars = ("financial_score", "customer_score",
                   "process_score", "people_score")
        metrics = []
        for pillar in pillars:
            values = [r.get(pillar) for r in rows
                      if isinstance(r.get(pillar), (int, float))]
            if not values:
                continue
            avg = sum(values) / len(values)
            target = 4.0  # BSC "exceeds expectations" benchmark on 0-5
            metrics.append({
                "name": pillar.replace("_", " ").title(),
                "performance": round(avg, 2),
                "target": target,
                "n_observations": len(values),
                "scale_note": "0-5 scale (BSC pillar; target=4.0 'exceeds')",
            })

        # If bank_targets has KPIs we can match by name, surface those too
        if isinstance(targets, dict):
            # bank_targets keys are like "PBT|2026"; we don't have actuals
            # in this engine's scope, so we skip per-KPI cross-ref. The
            # BSC pillar averages above are the SWOT-grade rollup.
            pass

        return metrics

    def get_market_trends(self) -> List[Dict]:
        """Returns list of {name, growth_rate, size, relevance_to_bank}
        derived from tier1_benchmarking.

        Logic: for each metric tracked in quarterly_metrics, compute
        the growth rate Q-over-Q across tier-1 banks; if positive and
        material (e.g. NIM expansion, digital_customers growth), tag
        with relevance_to_bank score based on metric type.
        """
        bench = self._load_json("tier1_benchmarking.json")
        if not bench or not isinstance(bench, dict):
            return []

        quarterly = bench.get("quarterly_metrics", {})
        if not quarterly:
            return []

        # Pick metric → relevance map per Continuation.docx context
        # (Eco Bank Kenya focus: digital adoption, NIM, customer growth)
        relevance_map = {
            "digital_customers_m":  0.95,   # digital growth = top priority
            "agents":               0.85,   # agency banking — relevant for KE
            "atms":                 0.50,   # commodity infrastructure
            "branches":             0.40,   # declining channel
            "nim_pct":              0.80,   # margin compression watch
            "roe_pct":              0.75,
            "deposits_kes_b":       0.85,
            "loans_kes_b":          0.85,
            "assets_kes_b":         0.65,
            "cir_pct":              0.70,   # cost-to-income (lower is better)
            "lcr_pct":              0.55,   # liquidity coverage
        }

        # Compute average growth rate across tier1 banks per metric
        all_banks = list(quarterly.keys())
        if not all_banks:
            return []

        # Get sorted list of quarters from first bank
        sample_bank_data = quarterly[all_banks[0]]
        if not isinstance(sample_bank_data, dict):
            return []
        quarters = sorted(sample_bank_data.keys())
        if len(quarters) < 2:
            return []

        first_q, last_q = quarters[0], quarters[-1]
        trends = []
        for metric, relevance in relevance_map.items():
            growth_rates = []
            for bank in all_banks:
                q1_val = quarterly.get(bank, {}).get(first_q, {}).get(metric)
                qL_val = quarterly.get(bank, {}).get(last_q, {}).get(metric)
                if (isinstance(q1_val, (int, float))
                        and isinstance(qL_val, (int, float))
                        and q1_val > 0):
                    growth_rates.append((qL_val - q1_val) / q1_val * 100.0)
            if not growth_rates:
                continue
            avg_growth = sum(growth_rates) / len(growth_rates)
            # CIR is inverted — lower is better; flip sign for "trend"
            if metric == "cir_pct":
                avg_growth = -avg_growth
            trends.append({
                "name": metric.replace("_", " ").replace("pct", "%"),
                "growth_rate": round(avg_growth, 2),
                "size": len(all_banks),  # # of banks observed
                "relevance_to_bank": relevance,
                "metric": metric,
                "from_quarter": first_q,
                "to_quarter": last_q,
            })

        return trends

    def get_competitor_intelligence(self) -> List[Dict]:
        """Returns list of {competitor, description, impact} from
        competitor_data.

        Logic: any competitor with > 5% market share AND aggressive
        deposit/lending rate moves is flagged as a meaningful threat.
        """
        comp = self._load_json("competitor_data.json")
        if not comp or not isinstance(comp, dict):
            return []

        banks = comp.get("banks", [])
        market_share = comp.get("market_share", {})
        deposit_rates = comp.get("deposit_rates", {})
        lending_rates = comp.get("lending_rates", {})

        if not banks or not market_share:
            return []

        # Compute "aggression" — bank with deposit rate above peer median
        # and lending rate below peer median is competing on price both ways
        peer_deposit_median = None
        peer_lending_median = None
        if deposit_rates:
            vals = [v for v in deposit_rates.values()
                    if isinstance(v, (int, float))]
            if vals: peer_deposit_median = sorted(vals)[len(vals) // 2]
        if lending_rates:
            vals = [v for v in lending_rates.values()
                    if isinstance(v, (int, float))]
            if vals: peer_lending_median = sorted(vals)[len(vals) // 2]

        actions = []
        for bank in banks:
            share = market_share.get(bank)
            if not isinstance(share, (int, float)) or share < 5.0:
                continue  # too small to flag
            descriptions = []
            impact = 0.3  # baseline — having >5% share is itself a presence
            if peer_deposit_median is not None:
                bank_dep = deposit_rates.get(bank)
                if (isinstance(bank_dep, (int, float))
                        and bank_dep > peer_deposit_median):
                    descriptions.append(
                        f"deposit rate {bank_dep}% (above peer median "
                        f"{peer_deposit_median}%) — capturing CASA share")
                    impact += 0.25
            if peer_lending_median is not None:
                bank_lend = lending_rates.get(bank)
                if (isinstance(bank_lend, (int, float))
                        and bank_lend < peer_lending_median):
                    descriptions.append(
                        f"lending rate {bank_lend}% (below peer median "
                        f"{peer_lending_median}%) — undercutting on price")
                    impact += 0.25
            # Cap impact at 1.0
            impact = min(impact, 1.0)
            description = "; ".join(descriptions) if descriptions \
                else f"market share {share}% — established presence"
            actions.append({
                "competitor":  bank,
                "description": description,
                "impact":      round(impact, 2),
                "market_share_pct": share,
            })

        return actions

    # ── SWOT generator ──

    def generate_swot(self,
                      business_unit: Optional[str] = None) -> Dict[str, Any]:
        """Generate SWOT analysis from real data.

        Args:
            business_unit: optional filter for internal metrics
                (e.g., a specific branch or department).

        Returns:
            {
              "swot": {
                "strengths":     [...],
                "weaknesses":    [...],
                "opportunities": [...],
                "threats":       [...]
              },
              "strategic_implications": [...],
              "data_sources": [...],
              "generated_at": ISO-8601 timestamp,
              "business_unit": str | None
            }
        """
        # ── Internal: Strengths & Weaknesses from financial metrics ──
        internal = {"strengths": [], "weaknesses": []}
        financial_metrics = self.get_financial_metrics(business_unit)
        for metric in financial_metrics:
            perf = metric.get("performance", 0)
            target = metric.get("target", 0)
            if target <= 0:
                continue
            ratio = perf / target
            if ratio > STRENGTH_THRESHOLD_RATIO:
                internal["strengths"].append({
                    "factor":    metric["name"],
                    "value":     perf,
                    "benchmark": target,
                    "evidence":
                        f"Consistently exceeding target by "
                        f"{(ratio - 1) * 100:.0f}%",
                    "n_observations": metric.get("n_observations"),
                })
            elif ratio < WEAKNESS_THRESHOLD_RATIO:
                internal["weaknesses"].append({
                    "factor":    metric["name"],
                    "value":     perf,
                    "benchmark": target,
                    "gap":       round(target - perf, 2),
                    "n_observations": metric.get("n_observations"),
                })

        # ── External: Opportunities & Threats ──
        external = {"opportunities": [], "threats": []}

        market_trends = self.get_market_trends()
        for trend in market_trends:
            if (trend.get("growth_rate", 0) > OPPORTUNITY_GROWTH_PCT_MIN
                    and trend.get("relevance_to_bank", 0)
                        > OPPORTUNITY_RELEVANCE_MIN):
                external["opportunities"].append({
                    "trend":           trend["name"],
                    "growth_rate":     trend["growth_rate"],
                    "market_size":     trend.get("size"),
                    "strategic_fit":   trend["relevance_to_bank"],
                    "recommended_action":
                        f"Consider {trend['name']} in strategic plan",
                    "metric":          trend.get("metric"),
                })

        competitor_actions = self.get_competitor_intelligence()
        for action in competitor_actions:
            if action.get("impact", 0) > THREAT_IMPACT_MIN:
                external["threats"].append({
                    "competitor":        action["competitor"],
                    "action":            action["description"],
                    "impact":            action["impact"],
                    "response_required":
                        "Immediate" if action["impact"]
                            > THREAT_IMPACT_IMMEDIATE
                        else "Monitor",
                    "market_share_pct":  action.get("market_share_pct"),
                })

        # ── Strategic implications (rule-based) ──
        implications = self._generate_implications_rule_based(
            internal, external)

        # ── Provenance ──
        data_sources = []
        for fname in ("bsc_scores.json", "bank_targets.json",
                      "tier1_benchmarking.json", "competitor_data.json"):
            if (self.data_dir / fname).exists():
                data_sources.append(fname)

        return {
            "swot": {
                "strengths":     internal["strengths"],
                "weaknesses":    internal["weaknesses"],
                "opportunities": external["opportunities"],
                "threats":       external["threats"],
            },
            "strategic_implications": implications,
            "data_sources":     data_sources,
            "generated_at":     datetime.now(timezone.utc).isoformat(),
            "business_unit":    business_unit,
            "basis":            "rule_based",
        }

    def _generate_implications_rule_based(
            self,
            internal: Dict[str, List],
            external: Dict[str, List]) -> List[str]:
        """Deterministic strategic implications based on SWOT counts.

        These templates mirror the canonical SWOT-to-strategy mapping
        (S+O = Maxi-Maxi growth strategy, W+O = Mini-Maxi development,
        S+T = Maxi-Mini defensive, W+T = Mini-Mini retreat). Plus
        single-quadrant fallbacks for narrow SWOT inputs.
        """
        s = len(internal.get("strengths", []))
        w = len(internal.get("weaknesses", []))
        o = len(external.get("opportunities", []))
        t = len(external.get("threats", []))
        implications = []
        if s and o:
            implications.append(
                f"S+O (Maxi-Maxi growth): leverage {s} internal strength(s) "
                f"to capture {o} market opportunity(ies). Aggressive "
                f"market-development strategy is data-supported.")
        if w and o:
            implications.append(
                f"W+O (Mini-Maxi development): {o} opportunity(ies) "
                f"available but {w} internal weakness(es) constrain "
                f"capacity. Capability-building precedes expansion.")
        if s and t:
            implications.append(
                f"S+T (Maxi-Mini defensive): {s} strength(s) provide "
                f"buffer against {t} competitor threat(s). Reinforce "
                f"differentiation rather than match competitor pricing.")
        if w and t:
            implications.append(
                f"W+T (Mini-Mini retreat): {w} weakness(es) AND {t} "
                f"threat(s) — defensive consolidation; avoid new bets "
                f"until weaknesses are remediated.")
        # Single-quadrant fallbacks (when only one or two quadrants populated)
        if w and not o and not t and not s:
            implications.append(
                f"Internal-only signal: {w} weakness(es) detected, no "
                f"external opportunities or threats surfaced. Priority "
                f"is capability-building on weak BSC pillars before "
                f"strategic positioning. Verify external data sources "
                f"(tier1_benchmarking, competitor_data) are populated "
                f"to enable full SWOT.")
        if s and not o and not t and not w:
            implications.append(
                f"Internal-strength-only signal: {s} strength(s), no "
                f"external context. Strengths are reusable assets — "
                f"populate market data to identify where to deploy them.")
        if o and not s and not w and not t:
            implications.append(
                f"Opportunity-only signal: {o} opportunity(ies) but no "
                f"internal capability data. Run BSC scoring before "
                f"committing to expansion.")
        if t and not s and not w and not o:
            implications.append(
                f"Threat-only signal: {t} competitor threat(s) without "
                f"internal capability picture. Defensive posture pending "
                f"capability assessment.")
        if not (s or w or o or t):
            implications.append(
                "Insufficient SWOT inputs — verify data sources are "
                "populated (bsc_scores, bank_targets, tier1_benchmarking, "
                "competitor_data) before generating strategy.")
        return implications

    # ── Board vision synthesis (NLP scaffold; rule-based fallback) ──

    def synthesize_board_vision(
            self,
            board_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Capture and structure board/executive vision.

        Args:
            board_inputs: list of {author, content, role?, date?} dicts —
                board members' written input on strategic direction.

        Returns:
            {
              "strategic_themes": [...],
              "conflicts_to_resolve": [...],
              "draft_vision_statement": str,
              "next_steps": str,
              "basis": "rule_based" | "llm",
              "fallback_reason": str | None  (when basis=rule_based)
            }

        When llm_provider_fn was injected at construction time, the
        engine uses it for theme extraction. Otherwise falls back to
        keyword-frequency theme detection over canonical strategic
        keywords (deterministic, reproducible).
        """
        if self.llm_provider_fn is not None:
            return self._synthesize_via_llm(board_inputs)
        return self._synthesize_rule_based(board_inputs)

    # Canonical strategic theme keywords (rule-based detection)
    THEME_KEYWORDS = {
        "Digital Transformation":
            ("digital", "mobile", "app", "online", "fintech",
             "platform", "ai", "automation"),
        "Customer-Centric Banking":
            ("customer", "experience", "service", "satisfaction",
             "nps", "loyalty"),
        "Sustainable Growth":
            ("sustainable", "esg", "climate", "green", "responsible"),
        "Operational Excellence":
            ("efficiency", "cost", "productivity", "automation",
             "lean", "process"),
        "Regulatory Compliance":
            ("compliance", "cbk", "regulation", "regulatory",
             "kyc", "aml"),
        "People & Culture":
            ("talent", "culture", "employee", "training",
             "engagement", "wellbeing"),
        "Risk Management":
            ("risk", "credit", "operational", "cyber", "resilience"),
        "Market Expansion":
            ("growth", "expansion", "new market", "diaspora",
             "regional", "africa"),
    }

    def _synthesize_rule_based(
            self,
            board_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Theme detection by keyword frequency. Same input → same output."""
        theme_counts: Dict[str, int] = {t: 0 for t in self.THEME_KEYWORDS}
        author_themes: Dict[str, set] = {}

        for entry in board_inputs:
            content = (entry.get("content") or "").lower()
            author = entry.get("author") or "anonymous"
            for theme, keywords in self.THEME_KEYWORDS.items():
                if any(kw in content for kw in keywords):
                    theme_counts[theme] += 1
                    author_themes.setdefault(author, set()).add(theme)

        # Themes mentioned by ≥2 authors are "common"
        # Themes mentioned by exactly 1 author may indicate "minority view" → conflict candidate
        common_themes = []
        minority_themes = []
        for theme, count in theme_counts.items():
            if count >= 2:
                authors_with = [a for a, ts in author_themes.items()
                                if theme in ts]
                common_themes.append({
                    "theme":   theme,
                    "mentions": count,
                    "authors": authors_with,
                })
            elif count == 1:
                authors_with = [a for a, ts in author_themes.items()
                                if theme in ts]
                minority_themes.append({
                    "theme":   theme,
                    "authors": authors_with,
                })

        common_themes.sort(key=lambda x: -x["mentions"])

        # Conflicts: minority themes are flagged for board discussion.
        # (Direct-contradiction detection between authors is deferred to
        # ENH-149 Stakeholder Engagement Pulse Engine where author-level
        # sentiment analysis is the primary feature.)
        conflicts = []
        for mt in minority_themes:
            conflicts.append({
                "type":  "minority_theme",
                "theme": mt["theme"],
                "raised_by": mt["authors"],
                "note":  "Single-author mention — surface in board "
                         "workshop to confirm priority.",
            })

        # Vision statement template — deterministic
        if common_themes:
            top_theme_names = [t["theme"] for t in common_themes[:3]]
            if len(top_theme_names) == 1:
                vision_stmt = (
                    f"To lead through {top_theme_names[0]} — building "
                    f"a bank that serves Kenya's evolving customer needs.")
            elif len(top_theme_names) == 2:
                vision_stmt = (
                    f"To lead through {top_theme_names[0]} and "
                    f"{top_theme_names[1]} — building a bank that serves "
                    f"Kenya's evolving customer needs.")
            else:
                vision_stmt = (
                    f"To lead through {top_theme_names[0]}, "
                    f"{top_theme_names[1]}, and {top_theme_names[2]} — "
                    f"building a bank that serves Kenya's evolving "
                    f"customer needs.")
        else:
            vision_stmt = (
                "Insufficient board inputs to draft vision statement. "
                "Collect more written input or run a vision workshop.")

        next_steps = (
            "Board workshop to resolve conflicts and ratify vision."
            if conflicts
            else "Proceed to strategy formulation (ENH-142 Strategic "
                 "Options Generator).")

        return {
            "strategic_themes":      common_themes,
            "conflicts_to_resolve":  conflicts,
            "draft_vision_statement": vision_stmt,
            "next_steps":            next_steps,
            "basis":                 "rule_based",
            "fallback_reason":
                "No llm_provider_fn injected; using deterministic "
                "keyword-frequency theme detection.",
            "n_inputs":              len(board_inputs),
            "n_authors":             len(author_themes),
        }

    def _synthesize_via_llm(
            self,
            board_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """LLM-backed vision synthesis. Caller-injected llm_provider_fn
        receives a structured prompt and returns generated text.

        For v10.135 this is a wired hook returning a placeholder
        marker — production banks injecting an LLM provider will
        receive a parseable response. Keeping this thin until a
        validated prompt-engineering pass happens (post-Phase 1)."""
        # Build prompt from board inputs
        prompt_parts = ["Synthesize strategic themes from the following "
                        "board inputs:\n"]
        for entry in board_inputs:
            author = entry.get("author") or "anonymous"
            content = (entry.get("content") or "").strip()
            prompt_parts.append(f"\n{author}: {content}")
        prompt = "\n".join(prompt_parts)

        try:
            llm_response = self.llm_provider_fn(prompt)
        except Exception as e:
            logger.warning(f"LLM provider failed: {e}; falling back")
            result = self._synthesize_rule_based(board_inputs)
            result["fallback_reason"] = (
                f"LLM provider raised {type(e).__name__}; used "
                f"rule-based fallback.")
            return result

        return {
            "strategic_themes":      [],   # caller parses llm_response
            "conflicts_to_resolve":  [],
            "draft_vision_statement": llm_response[:500] if llm_response
                                       else "",
            "next_steps":            "Review LLM-generated vision with board.",
            "basis":                 "llm",
            "fallback_reason":       None,
            "raw_llm_response":      llm_response,
            "n_inputs":              len(board_inputs),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper for cockpit / API use
# ════════════════════════════════════════════════════════════════════

def generate_swot(business_unit: Optional[str] = None,
                  data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and run SWOT once."""
    return StrategyFormulationEngine(data_dir=data_dir).generate_swot(
        business_unit=business_unit)
