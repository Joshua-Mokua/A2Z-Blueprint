"""tests/integration/test_v10_13_pricing_workflow.py — v10.13.

Phase 2 batch 7 (Credit batch 3): pricing + workflow + committee + memo + 80/20.
ENH-123, ENH-125, ENH-130, ENH-CRD-R5, ENH-CRD-R7.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1013Imports(unittest.TestCase):
    def test_pricing_module_imports(self):
        from utils import risk_based_pricing  # noqa
    def test_workflow_module_imports(self):
        from utils import credit_workflow  # noqa

    def test_pricing_public_symbols(self):
        from utils import risk_based_pricing as m
        for sym in (
            "PricingDecision", "PricingInputs", "PricingComponents",
            "PricingResult",
            "compute_pricing_components", "price_loan", "compute_raroc",
            "basel_irb_capital_factor",
            "RATE_FLOOR", "RATE_CEILING",
            "DEFAULT_CAPITAL_RATIO_TARGET", "DEFAULT_COST_OF_EQUITY",
        ):
            self.assertTrue(hasattr(m, sym), f"missing pricing public: {sym}")

    def test_workflow_public_symbols(self):
        from utils import credit_workflow as m
        for sym in (
            "ApplicationState", "ALLOWED_TRANSITIONS",
            "is_terminal_state", "is_valid_transition",
            "StateTransition", "CreditWorkflowEngine",
            "AutomationDecision", "AutomationPolicy",
            "evaluate_automation",
            "AUTOMATION_AMOUNT_TIER_1_KES",
            "AUTOMATION_AMOUNT_TIER_2_KES",
            "AUTOMATION_AMOUNT_TIER_3_KES",
            "AUTOMATION_CONFIDENCE_THRESHOLD",
            "CommitteeRole", "CommitteeVote", "CommitteeDecision",
            "COMMITTEE_REQUIREMENTS", "determine_tier",
            "evaluate_committee_decision",
            "CREDIT_MEMO_REQUIRED_SECTIONS",
            "CreditMemoSection", "CreditMemo", "draft_memo_template",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing workflow public: {sym}")


class TestV1013SelfTests(unittest.TestCase):
    def test_pricing_self_test(self):
        from utils import risk_based_pricing
        risk_based_pricing.self_test()

    def test_workflow_self_test(self):
        from utils import credit_workflow
        credit_workflow.self_test()


class TestV1013Registry(unittest.TestCase):
    def test_13_credit_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 13)

    def test_v10_13_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit" and s.status == "active"}
        for sid in ("ENH-123", "ENH-125", "ENH-130",
                      "ENH-CRD-R5", "ENH-CRD-R7"):
            self.assertIn(sid, active_ids)


class TestV1013Pricing(unittest.TestCase):
    """ENH-123 — Risk-based pricing."""

    def test_low_risk_priced_in_normal_band(self):
        from utils.risk_based_pricing import (
            PricingInputs, price_loan, PricingDecision,
            RATE_FLOOR, RATE_CEILING)
        r = price_loan(PricingInputs(
            asset_id="L", pd=Decimal("0.01"), lgd=Decimal("0.40"),
            ead_kes=Decimal("1000000"), tenor_months=12,
            funding_rate=Decimal("0.08")))
        self.assertEqual(r.decision, PricingDecision.PRICE_OFFERED)
        self.assertGreaterEqual(r.offered_rate, RATE_FLOOR)
        self.assertLessEqual(r.offered_rate, RATE_CEILING)

    def test_extreme_pd_declines_uneconomic(self):
        from utils.risk_based_pricing import (
            PricingInputs, price_loan, PricingDecision)
        r = price_loan(PricingInputs(
            asset_id="L", pd=Decimal("0.85"), lgd=Decimal("0.95"),
            ead_kes=Decimal("100000"), tenor_months=12,
            funding_rate=Decimal("0.15")))
        self.assertEqual(r.decision, PricingDecision.DECLINE_UNECONOMIC)

    def test_basel_irb_k_table_monotone(self):
        """K is monotone non-decreasing in PD."""
        from utils.risk_based_pricing import basel_irb_capital_factor
        ks = [basel_irb_capital_factor(Decimal(str(p)))
                for p in [0.001, 0.01, 0.05, 0.1, 0.3, 0.7]]
        for i in range(len(ks) - 1):
            self.assertLessEqual(ks[i], ks[i + 1])

    def test_raroc_positive_for_priced_loan(self):
        from utils.risk_based_pricing import (
            PricingInputs, price_loan)
        r = price_loan(PricingInputs(
            asset_id="L", pd=Decimal("0.02"), lgd=Decimal("0.40"),
            ead_kes=Decimal("1000000"), tenor_months=12,
            funding_rate=Decimal("0.08")))
        self.assertIsNotNone(r.raroc)
        self.assertGreater(r.raroc, Decimal("0"))


class TestV1013StateMachine(unittest.TestCase):
    """ENH-125 — Workflow orchestration."""

    def test_full_happy_path(self):
        from utils.credit_workflow import (
            CreditWorkflowEngine, ApplicationState)
        eng = CreditWorkflowEngine()
        eng.initialize("APP-1")
        for to in [
            ApplicationState.SUBMITTED,
            ApplicationState.EKYC_PENDING,
            ApplicationState.BUREAU_PULL_PENDING,
            ApplicationState.DECISION_PENDING,
            ApplicationState.APPROVED,
            ApplicationState.DOCUMENTATION_PENDING,
            ApplicationState.DISBURSEMENT_PENDING,
            ApplicationState.DISBURSED,
        ]:
            eng.transition(application_id="APP-1", to_state=to,
                            actor="sys", timestamp="t")
        self.assertEqual(eng.get_state("APP-1"),
                            ApplicationState.DISBURSED)

    def test_invalid_skip_transition_blocked(self):
        from utils.credit_workflow import (
            CreditWorkflowEngine, ApplicationState)
        eng = CreditWorkflowEngine()
        eng.initialize("APP-1")
        with self.assertRaises(ValueError):
            eng.transition(
                application_id="APP-1",
                to_state=ApplicationState.DISBURSED,
                actor="sys", timestamp="t")

    def test_terminal_states_have_no_exits(self):
        from utils.credit_workflow import (
            ApplicationState, ALLOWED_TRANSITIONS, is_terminal_state)
        for state in ApplicationState:
            if is_terminal_state(state):
                self.assertEqual(ALLOWED_TRANSITIONS[state], ())


class TestV1013AutomationPolicy(unittest.TestCase):
    """ENH-CRD-R7 — 80/20 automation pattern."""

    def test_high_confidence_small_amount_automates(self):
        from utils.credit_workflow import (
            evaluate_automation, AutomationDecision)
        d = evaluate_automation(
            decision_confidence=Decimal("0.95"),
            amount_kes=Decimal("100000"))
        self.assertEqual(d, AutomationDecision.AUTOMATE)

    def test_large_amount_committee(self):
        from utils.credit_workflow import (
            evaluate_automation, AutomationDecision)
        d = evaluate_automation(
            decision_confidence=Decimal("0.95"),
            amount_kes=Decimal("60000000"))
        self.assertEqual(d, AutomationDecision.COMMITTEE)

    def test_low_confidence_routes_human(self):
        from utils.credit_workflow import (
            evaluate_automation, AutomationDecision)
        d = evaluate_automation(
            decision_confidence=Decimal("0.65"),
            amount_kes=Decimal("100000"))
        self.assertEqual(d, AutomationDecision.HUMAN_REVIEW)


class TestV1013Committee(unittest.TestCase):
    """ENH-130 — Credit committee automation."""

    def test_tier_2_quorum_2_pass(self):
        from utils.credit_workflow import (
            evaluate_committee_decision, CommitteeVote, CommitteeRole)
        votes = (
            CommitteeVote(voter_role=CommitteeRole.HEAD_OF_CREDIT,
                            voter_id="v1", decision="APPROVE",
                            timestamp="t"),
            CommitteeVote(voter_role=CommitteeRole.HEAD_OF_RISK,
                            voter_id="v2", decision="APPROVE",
                            timestamp="t"),
        )
        d = evaluate_committee_decision(
            application_id="A", committee_id="C",
            amount_kes=Decimal("3000000"), votes=votes)
        self.assertEqual(d.outcome, "APPROVED")

    def test_tier_3_higher_threshold(self):
        """Tier 3: 75% threshold. 3-of-4 votes = 75% — passes."""
        from utils.credit_workflow import (
            evaluate_committee_decision, CommitteeVote, CommitteeRole)
        votes = tuple(
            CommitteeVote(voter_role=r, voter_id=f"v{i}",
                            decision=("APPROVE" if i < 3 else "DECLINE"),
                            timestamp="t")
            for i, r in enumerate([
                CommitteeRole.HEAD_OF_CREDIT,
                CommitteeRole.HEAD_OF_RISK,
                CommitteeRole.HEAD_OF_BUSINESS,
                CommitteeRole.HEAD_OF_COMPLIANCE]))
        d = evaluate_committee_decision(
            application_id="A", committee_id="C",
            amount_kes=Decimal("20000000"), votes=votes)
        self.assertEqual(d.outcome, "APPROVED")

    def test_no_quorum(self):
        from utils.credit_workflow import (
            evaluate_committee_decision, CommitteeVote, CommitteeRole)
        votes = (
            CommitteeVote(voter_role=CommitteeRole.HEAD_OF_CREDIT,
                            voter_id="v1", decision="APPROVE",
                            timestamp="t"),
        )
        d = evaluate_committee_decision(
            application_id="A", committee_id="C",
            amount_kes=Decimal("3000000"), votes=votes)
        self.assertEqual(d.outcome, "NO_QUORUM")


class TestV1013Memo(unittest.TestCase):
    """ENH-CRD-R5 — Credit memo drafting."""

    def test_template_default_complete(self):
        from utils.credit_workflow import (
            draft_memo_template, CREDIT_MEMO_REQUIRED_SECTIONS)
        memo = draft_memo_template(
            application_id="A", drafted_at="t",
            applicant_name="ACME Ltd",
            requested_amount_kes=Decimal("1000000"),
            decision_summary="Recommend APPROVE")
        self.assertTrue(memo.is_complete())
        section_names = tuple(s.name for s in memo.sections)
        for required in CREDIT_MEMO_REQUIRED_SECTIONS:
            self.assertIn(required, section_names)

    def test_default_uses_rule_based_with_deviation(self):
        from utils.credit_workflow import (
            draft_memo_template, SPEC_DEVIATION_NOTE)
        memo = draft_memo_template(
            application_id="A", drafted_at="t",
            applicant_name="X")
        self.assertEqual(memo.drafted_by, "rule_based_template")
        self.assertIn(SPEC_DEVIATION_NOTE, memo.deviation_notes)

    def test_llm_hook_used_when_provided(self):
        """Rule 7 — LLM is callable, never silent."""
        from utils.credit_workflow import draft_memo_template
        called_sections = []

        def hook(name, ctx):
            called_sections.append(name)
            return f"LLM:{name}"

        memo = draft_memo_template(
            application_id="A", drafted_at="t",
            applicant_name="X", llm_hook=hook)
        self.assertEqual(memo.drafted_by, "gen_ai")
        # LLM hook was called for each section
        self.assertGreater(len(called_sections), 0)


class TestV1013ChainCoexistence(unittest.TestCase):
    def test_v10_11_v10_12_v10_13_engines_coexist(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.applicant_data_sources import ApplicantDataAggregator
        from utils.credit_workflow import CreditWorkflowEngine
        u = AIUnderwritingEngine(entity_name="X")
        d = ApplicantDataAggregator(entity_name="X")
        w = CreditWorkflowEngine(entity_name="X")
        self.assertEqual(u.entity_name, w.entity_name)
        self.assertEqual(d.entity_name, w.entity_name)


if __name__ == "__main__":
    unittest.main()
