# Reporting & Analytics Module — Dependency Monitoring

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 8 Anti-Deterioration: track external dependencies and version risk.

---

## Python dependencies

- Streamlit (frontend)
- FastAPI (API layer)
- pandas + openpyxl (data manipulation + XLSX)
- pydantic (validation)
- psycopg / sqlalchemy (PostgreSQL)

## Risks

- Pin versions in `requirements.txt`
- Run `pip-audit` regularly for CVEs
- Track end-of-life dates for runtimes
