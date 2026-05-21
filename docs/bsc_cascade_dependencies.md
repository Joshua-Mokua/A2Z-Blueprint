# BSC & Target Cascade — Dependency Monitoring

**Module key:** `bsc_cascade` · **Organ role:** Brain Intelligence, Direction & Decision Flow
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 100.0%

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
