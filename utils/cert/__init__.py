"""utils.cert - Olympic + Championship certification.

Olympic full (22 checks) proves per-organ reproducibility and soundness.
Championship full (51 checks across 11 organs) extends Olympic with phase
C1-C8 specifics and produces an explicit 33-item mandatory checklist
verdict per the Enterprise Revival Integrity Validation, Olympic
Rehabilitation & Championship Readiness Framework.

Run via:
    from utils.cert import Certifier, build_olympic_full
    report = Certifier().run(build_olympic_full())

For pre-React championship readiness:
    from utils.cert.championship import run_championship_cert
    report = run_championship_cert()
    print(report.checklist_markdown())
"""

from utils.cert.base import (
    CertCheck, CheckOutcome, CertReport, CertProtocol,
)
from utils.cert.certifier import (
    Certifier, build_olympic_full, build_olympic_quick,
)
from utils.cert.championship import (
    ChampionshipItem, ChampionshipReport,
    CHAMPIONSHIP_CHECKLIST,
    build_championship_full, run_championship_cert,
)

__all__ = [
    "CertCheck", "CheckOutcome", "CertReport", "CertProtocol",
    "Certifier", "build_olympic_full", "build_olympic_quick",
    "ChampionshipItem", "ChampionshipReport",
    "CHAMPIONSHIP_CHECKLIST",
    "build_championship_full", "run_championship_cert",
]
