"""utils.scenarios — Phase O3-C banking scenario library.

100 scenarios across 5 categories (20 each), driving realistic Kenyan
banking traffic through the 7 channel simulators (RTGS / SWIFT / ATM /
USSD / M-Pesa / KIC / Cards).

Categories:
  - operational         — payroll, EOM, salary surges, supplier runs
  - fraud               — card testing, account takeover, mule flows
  - operational_risk    — channel outages, settlement failures
  - regulatory          — AML, KYC, sanctions, CBK circulars
  - customer_behaviour  — salary cycle, retiree, diaspora, SME quarterly
"""

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioSeverity, ScenarioContext,
    ScenarioResult, ScenarioRunner,
)
from utils.scenarios.registry import (
    SCENARIOS, get_scenario, list_scenarios, list_categories,
    run_scenario, scenarios_by_category, scenarios_by_severity,
    scenarios_by_tag,
)

__all__ = [
    "Scenario", "ScenarioCategory", "ScenarioSeverity", "ScenarioContext",
    "ScenarioResult", "ScenarioRunner",
    "SCENARIOS", "get_scenario", "list_scenarios", "list_categories",
    "run_scenario", "scenarios_by_category", "scenarios_by_severity",
    "scenarios_by_tag",
]
