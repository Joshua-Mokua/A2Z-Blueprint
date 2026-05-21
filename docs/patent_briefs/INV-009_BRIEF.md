# Patent Brief — INV-009

**Deterministic Three-Tier Anti-Corruption Layer Fallback for Banking Core System Integration with Provenance-Stamped Output**

> **Status**: PRE-FILING TECHNICAL DISCLOSURE — FOR REGISTERED PATENT AGENT REVIEW
> **Version**: v9.3 (May 2026)
> **Inventor**: Joshua Mokua (sole inventor as of brief date; agent confirms)
> **Companion to**: `docs/A2Z_IP_STRATEGY_PLAN.md` Part 5
> **Codebase reference**: `utils/flexcube_adapter.py` (~1,300 lines as of v8.27)
> **First public disclosure**: github commit history for v7.10 (date stamp from `git log`)

---

## 1. Field of the invention

This invention relates to software systems for integrating banking management information platforms with core banking systems. More specifically, it relates to a method and system for deterministic multi-tier fallback in an Anti-Corruption Layer translating between a banking core system's vocabulary and a banking management information platform's vocabulary, with provenance-stamped output enabling downstream auditability.

---

## 2. Background of the invention

### 2.1 The problem

Banking management information platforms typically integrate with core banking systems (e.g. Oracle FLEXCUBE, Temenos T24) to obtain real-time portfolio data. This integration faces several operational challenges:

| Challenge | Consequence |
|---|---|
| Core system temporary unavailability | Platform queries return errors; user-facing reports are blank |
| Network partition between platform and core | Same as above; difficult to distinguish from "no data" |
| Authentication / token expiry | Authorization failures cause query failures |
| Schema or version mismatch | Translation errors; partial data returned |
| Data residency requirements | Cannot fall back to a different region's instance |
| Audit / regulatory traceability | Reports must indicate whether data came from live core, cache, or fallback |

Existing approaches to handling these challenges include:

| Approach | Limitation |
|---|---|
| Single live-only integration | Fails when core is unavailable; no fallback |
| Cache-and-serve-from-cache | Stale data; no clear indication of staleness |
| Synthetic / mock data for testing | Test-only; no production fallback path |
| Multi-region failover | Expensive; doesn't address data-residency rules |
| Anti-Corruption Layer (Evans 2003) | General pattern; not specific to multi-tier fallback semantics |

None of these existing approaches provides:

- Deterministic fallback semantics (same input + same health state always produces same output tier)
- Provenance-stamped output (consumers know which tier produced each value)
- Banking-domain-specific tier ordering (live > local-synthetic > demo-defaults)
- Integration with circuit-breaker and retry telemetry for tier-selection input

### 2.2 The need addressed

A mechanism is needed by which:

(a) a banking ACL provides three deterministic fallback tiers — primary live integration, secondary local-synthetic data, tertiary demo defaults;
(b) tier selection is deterministic given current system state (circuit breaker state, retry exhaustion, source-data presence);
(c) every output is stamped with provenance metadata identifying which tier produced the value;
(d) provenance metadata is auditable downstream (reports, dashboards, regulatory exports);
(e) tier semantics integrate with circuit-breaker state from runtime resilience layer;
(f) the mechanism is specifically tailored to banking-domain published-language between core and platform.

---

## 3. Summary of the invention

The invention is a method and system for deterministic multi-tier fallback in a banking Anti-Corruption Layer translating between a core banking system's vocabulary (e.g. Oracle FLEXCUBE) and a banking management information platform's vocabulary, with provenance-stamped output.

The method comprises:

1. **Defining three tiers of data sources** in priority order:
   - **Tier 1 — Live**: HTTP/SOAP integration with the core banking system's REST/SOAP API;
   - **Tier 2 — Local synthetic**: file-based data sources (e.g. JSON/CSV exports of CBS state);
   - **Tier 3 — Demo defaults**: hard-coded sentinel values guaranteed never to fail;

2. **Determining the active tier deterministically** based on system state, including:
   - Circuit breaker state (open or closed);
   - Retry exhaustion (whether all live retries have failed);
   - Source-data presence (whether local synthetic files exist and are valid);

3. **Translating between vocabularies** using domain-specific Published Language contracts (e.g. Loan Portfolio Aggregate, Customer Aggregate, NPL Aggregate);

4. **Stamping every output with provenance metadata** identifying:
   - Which tier produced the value (`data_source` field: `"live"` / `"cbs_synthetic"` / `"demo_default"`);
   - Timestamp of production;
   - Optionally, additional tier-specific metadata (e.g. circuit breaker state at time of production);

5. **Exposing provenance metadata through a stable public interface** so that consumers can:
   - Display tier indicator in dashboards;
   - Filter audit logs by provenance;
   - Comply with regulatory requirements for data lineage (e.g. CBK audit trail);
   - Distinguish between live and fallback data in reports.

The invention specifically applies to FLEXCUBE-derived portfolio aggregates with five canonical aggregates (Loans, Deposits, NPL, Customer, Account Dormancy), each translated through the same three-tier fallback structure.

---

## 4. Detailed description

### 4.1 The three-tier structure

Reference: `utils/flexcube_adapter.py` lines 600-1100 in the A2Z codebase.

#### Tier 1 — Live integration

The Tier 1 path issues an HTTP request to the core banking system's REST endpoint (e.g. `/PortfolioService/Loans/Aggregate`), translates the response into the platform's Published Language schema, and returns the result with `data_source="live"` provenance.

If the request fails (network error, authentication failure, HTTP 5xx, etc.), Tier 1 invokes the retry mechanism. Retries are subject to exponential backoff with jitter (per v8.8) and feed into the per-endpoint circuit breaker (per v8.17).

If retries are exhausted or the circuit breaker is open, Tier 1 returns `None` and the caller advances to Tier 2.

#### Tier 2 — Local synthetic

The Tier 2 path reads from local file-based data sources (`cbs_data/customers.json`, `cbs_data/accounts.json`, `cbs_data/transactions.json` etc.) and computes the same aggregate that Tier 1 would have produced from a live response.

Tier 2 is suitable for:
- Development environments without core-banking access
- Simulation environments testing platform behavior
- Production environments during planned core-banking maintenance windows

If the synthetic source files exist and produce a non-error result, Tier 2 returns the aggregate with `data_source="cbs_synthetic"` provenance.

If synthetic source files are missing or malformed, Tier 2 returns `None` and the caller advances to Tier 3.

#### Tier 3 — Demo defaults

The Tier 3 path returns hard-coded sentinel aggregates that are domain-plausible but explicitly identified as defaults. For example, a Loan Portfolio Aggregate with KES 1B total balance, 100 active loans, and 5% NPL ratio.

Tier 3 is **guaranteed to never fail** — it requires no external dependencies. This guarantees that the platform's reports are always renderable, even in degraded states.

Tier 3 returns the aggregate with `data_source="demo_default"` provenance, ensuring downstream consumers know the values are sentinel.

### 4.2 Deterministic tier selection

The tier-selection function (in `utils/flexcube_adapter.py`):

```python
def fetch_loan_portfolio_aggregate() -> Dict[str, Any]:
    # Tier 1: Live
    if circuit_is_closed("PortfolioService/Loans"):
        result = _live_request("/PortfolioService/Loans/Aggregate")
        if result is not None:
            return _stamp(result, "live")
    
    # Tier 2: Local synthetic  
    result = _try_cbs_synthetic_aggregate("loans")
    if result is not None:
        return _stamp(result, "cbs_synthetic")
    
    # Tier 3: Demo default (never fails)
    return _stamp(_demo_default_loan_aggregate(), "demo_default")
```

**Determinism**: given the same circuit-breaker state, retry-exhaustion state, and source-file presence, the tier selection always produces the same result.

**Provenance stamping** via `_stamp(result, tier_id)` adds the `data_source` field plus a timestamp.

### 4.3 The Published Language contract

Each aggregate's schema is fixed across all three tiers — Tier 1 (live response), Tier 2 (synthetic computation), and Tier 3 (demo default) all produce the same dict shape with the same keys.

This is the Published Language pattern from Domain-Driven Design (Evans 2003), applied specifically to banking-core integration with:

| Key | Type | Provenance from |
|---|---|---|
| `total_balance` | float (KES) | All three tiers |
| `active_loan_count` | int | All three tiers |
| `npl_ratio_pct` | float | All three tiers |
| `last_updated_iso` | str | All three tiers |
| `data_source` | str (`live` / `cbs_synthetic` / `demo_default`) | Stamped at tier exit |
| `payload_version` | str (`"1.0"`) | Stamped at tier exit (v8.4 contract) |

The fixed schema means downstream consumers do not need to know which tier produced the data — they treat all responses uniformly except for the `data_source` provenance indicator.

### 4.4 Integration with resilience layer

Tier 1 integrates with:

- **Per-endpoint circuit breaker** (v8.17): tier-selection checks `_circuit_is_open(endpoint_path)` before issuing live request
- **Retry mechanism with jitter** (v8.1 + v8.8): live request issues up to `RETRY_ATTEMPTS=3` with exponential backoff and `RETRY_JITTER_PCT=0.2`
- **Latency telemetry** (v8.2 + v8.24): per-endpoint p50/p95/p99 latency tracked across all live requests; persisted to disk
- **Retry telemetry** (v8.19): per-endpoint counters tracking recovery rate and avg retries per request
- **Per-endpoint timeout config** (v8.20): each endpoint has its own timeout (e.g. NPL=600s, CustomerService=120s)

This integration means tier selection is informed by detailed runtime resilience state, not just a single boolean health check.

### 4.5 Operational evidence

The A2Z platform's FLEXCUBE adapter has been operating with the three-tier pattern since v7.10 (May 2026 first-disclosure date). All five canonical aggregates (Loans, Deposits, NPL, Customer, Dormancy) use the same tier-selection logic. The audit-locked invariant G108 (v8.3) verifies that the resilience-and-fallback contract remains intact at every build.

---

## 5. Suggested claim language (FOR AGENT REFINEMENT)

### Independent claim 1 (broad)

A computer-implemented method for translating between a core banking system's vocabulary and a banking management information platform's vocabulary in an Anti-Corruption Layer with multi-tier fallback, the method comprising:

(a) defining three tiers of data sources, comprising: a primary live-data tier configured to retrieve data from the core banking system, a secondary synthetic-data tier configured to retrieve data from local file-based persistence, and a tertiary demo-default tier configured to return predetermined sentinel data;

(b) determining the active tier deterministically based on system state, the system state comprising at least one of: a state of a circuit breaker associated with the core banking system, a state of retry exhaustion for live requests, and a presence indicator for local synthetic source files;

(c) translating data from the active tier into a uniform schema defined by a Published Language contract;

(d) stamping each translated output with provenance metadata identifying which tier produced the data, the provenance metadata comprising at least: a tier identifier and a timestamp;

(e) exposing the provenance metadata through a stable public interface accessible to downstream consumers.

### Dependent claim 2

The method of claim 1, wherein the core banking system is Oracle FLEXCUBE and the platform is a banking management information platform.

### Dependent claim 3

The method of claim 1, wherein the primary live-data tier integrates with at least one of:

(i) a retry mechanism with exponential backoff and randomized jitter;
(ii) a per-endpoint circuit breaker maintaining state per banking-API endpoint;
(iii) latency telemetry capturing per-endpoint percentile measurements;
(iv) per-endpoint timeout configuration distinct from a global default timeout.

### Dependent claim 4

The method of claim 1, wherein the tertiary demo-default tier is guaranteed to never fail, such that the platform produces a renderable output even when both the live-data tier and synthetic-data tier are unavailable.

### Dependent claim 5

The method of claim 1, wherein the provenance metadata's tier identifier comprises one of:

(i) `"live"` indicating the primary live-data tier produced the value;
(ii) `"cbs_synthetic"` indicating the secondary synthetic-data tier produced the value;
(iii) `"demo_default"` indicating the tertiary demo-default tier produced the value.

### Dependent claim 6

The method of claim 1, wherein the Published Language contract specifies a fixed schema across all three tiers, the schema comprising at least:

(i) a numeric balance field;
(ii) a count field;
(iii) a percentage or ratio field;
(iv) an ISO-8601 timestamp field;
(v) a data_source provenance field;
(vi) a payload_version field.

### Dependent claim 7

The method of claim 1, further comprising:

(a) maintaining circuit breaker state per banking-API endpoint, such that a failure in one endpoint does not affect the tier-selection for other endpoints;

(b) maintaining retry telemetry per banking-API endpoint, such that a recovery rate metric can be computed per endpoint indicating how often retries successfully recovered transient failures.

### System claim 8

A computer system for translating between a core banking system's vocabulary and a banking management information platform's vocabulary, the system comprising:

(a) at least one processor;
(b) memory storing executable instructions;
(c) an Anti-Corruption Layer that, when executed by the processor, performs the method of claim 1;
(d) a circuit breaker module maintaining per-endpoint state;
(e) a retry module configured for exponential backoff with randomized jitter;
(f) a latency telemetry module persisting per-endpoint percentile measurements.

### Computer-readable medium claim 9

A non-transitory computer-readable medium storing executable instructions that, when executed by one or more processors, cause the processors to perform the method of claim 1.

---

## 6. Suggested prior-art search categories and terms

### Search categories

| Category | Suggested databases |
|---|---|
| Anti-Corruption Layer pattern (DDD) | Evans 2003 + subsequent literature, ACM, IEEE |
| Banking core integration | Google Patents, Espacenet, KIPI |
| Multi-tier fallback systems | USPTO, ACM, IEEE |
| Provenance tracking in data systems | arXiv, academic literature |
| Circuit breaker + bulkhead patterns | Nygard 2007 + subsequent literature |

### Suggested search terms

- "anti-corruption layer" + "banking"
- "multi-tier fallback" + "core banking"
- "deterministic fallback" + "API integration"
- "data provenance" + "banking" + "audit"
- "FLEXCUBE" + "anti-corruption layer"
- "circuit breaker" + "banking API"
- "published language" + "banking" + "domain-driven design"
- "synthetic data fallback" + "production"

### Patent classifications likely relevant (CPC / IPC)

- G06F 9/54 (program communication)
- G06F 16/00 (information retrieval)
- G06Q 40/00 (finance)
- H04L 67/00 (network arrangements)

---

## 7. Identified distinguishing arguments

### 7.1 vs. generic Anti-Corruption Layer pattern (Evans 2003)

The DDD ACL pattern is general — translate between bounded contexts. The invention applies it specifically to banking-core integration with **three deterministic fallback tiers** (not just two), **provenance-stamped output**, and **integration with banking-specific resilience patterns**. The combination is novel.

### 7.2 vs. generic circuit-breaker + fallback (Hystrix, resilience4j, Polly)

These libraries provide circuit-breaker primitives. The invention applies them to a **banking-specific multi-tier fallback structure** with **provenance stamping** and **Published Language contract** spanning all three tiers. The integration is novel.

### 7.3 vs. cache-and-serve patterns

Cache-and-serve typically has two tiers (fresh vs. cached) with limited provenance. The invention has three deterministic tiers with each output explicitly identified. The third tier (demo-default) is guaranteed-never-fail, providing a renderability guarantee that cache-and-serve cannot.

### 7.4 vs. failover and disaster-recovery systems

Failover systems typically replicate the primary's data shape. The invention's three tiers each produce data of the same shape but from fundamentally different sources (live API vs. local files vs. hard-coded defaults). The Published Language contract is the unifying schema.

### 7.5 vs. patent prior art (initial scan)

A preliminary scan suggests the closest patent prior art may be:

- US 10,469,544 (Microsoft, 2019) — Service-mesh fallback; generic
- US 9,612,914 (IBM, 2017) — Multi-tier caching; cache-focused, not banking
- US 11,030,196 (Oracle, 2021) — Database fallback; database-focused

The invention's distinctive combination is: (a) banking-domain Published Language contract, (b) provenance-stamped output, (c) three-tier deterministic fallback (not two), (d) integration with per-endpoint circuit breaker + retry telemetry. Agent's professional search will identify additional references.

---

## 8. Honest grant-probability calibration

Per v8.13 IP Plan Part 2:

| Jurisdiction | Realistic grant probability | Rationale |
|---|---|---|
| Kenya KIPI | Moderate (40-60%) | Provenance-stamped multi-tier fallback is a specific technical pattern with technical effect on system behavior; the banking-domain combination may clear §21(d) |
| US USPTO | Low-moderate (20-40%) | Alice analysis subjective; the deterministic semantics + provenance stamping may clear "abstract idea" if claims emphasize the technical integration with circuit breaker / retry / latency |
| EPO | Low (15-30%) | Same considerations as INV-008; existing github disclosure (v7.10) likely forecloses EPO grant |
| China CNIPA | Variable | Same considerations as INV-008 |
| India IPO | Low | Same Section 3(k) considerations |

### 8.1 Github disclosure consideration

The v7.10 first disclosure (June-July 2025 estimated) puts Kenya/US grace period at significant pressure. Filing within 60 days is recommended.

### 8.2 Co-filing strategy

The two inventions (INV-008 + INV-009) are conceptually related. Agent should evaluate whether to:

(a) file as **separate** provisionals — cleaner claims, easier prosecution
(b) file as **consolidated** provisional — single application with multiple claim sets
(c) file INV-008 only — focus on the architectural-discipline pattern as the strongest claim

Agent's recommendation drives the strategy.

---

## 9. References to A2Z codebase

| Reference | Description | First commit |
|---|---|---|
| `utils/flexcube_adapter.py` | The Anti-Corruption Layer with three-tier fallback | v7.10 (~600 lines) → v8.27 (~1,300 lines) |
| `utils/flexcube_adapter.py` lines 600-1100 | Live tier + synthetic tier + demo-default tier implementations | v7.10 → v8.27 |
| `utils/flexcube_adapter.py` `_endpoint_key()` | Per-endpoint normalization helper | v8.17 |
| `utils/flexcube_adapter.py` `get_circuit_state()` | Circuit state with per-endpoint detail | v8.17 |
| `utils/flexcube_adapter.py` `get_retry_telemetry()` | Retry telemetry per endpoint | v8.19 |
| `cbs_data/` | Tier 2 synthetic data source files | v7.14 (cbs_data scaffold) → v8.10 (--from-cbs aggregation) |
| `scripts/audit.py` G108 | Resilience contract gate | v8.3 |
| `scripts/audit.py` G111 | Resilience v2 contract gate | v8.22 |
| `docs/A2Z_SYSTEMS_CHARTER.md` | First public technical disclosure | v7.0 |

---

## 10. Defensive publication chain

| Date stamp | Disclosure |
|---|---|
| v7.0 (charter) | ACL pattern named in architecture overview |
| v7.10 | First three-tier ACL implementation in `flexcube_adapter.py` |
| v7.11 | Provenance-stamping convention via `data_source` field |
| v8.0 | Five live FLEXCUBE handler implementations |
| v8.1 | Retry + circuit breaker integration with ACL |
| v8.2 | Latency telemetry integration |
| v8.17 | Per-endpoint circuit state |
| v8.19 | Per-endpoint retry telemetry |
| v8.20 | Per-endpoint timeout config |

Defensive publication value preserved regardless of patent filing outcome.

---

## 11. What the agent should evaluate

1. **Prior-art search** — comprehensive search per Section 6
2. **Filing strategy** — separate vs. consolidated with INV-008 (Section 8.2)
3. **Claim refinement** — convert suggested claims into legally sufficient form
4. **Inventorship** — confirm Joshua is sole inventor
5. **Strategic decision** — file Kenya provisional, refine, or abandon
6. **Filing prep** — if proceeding, draft provisional within 60 days

---

*v9.3 — INV-009 patent brief. Companion to docs/A2Z_IP_STRATEGY_PLAN.md Part 5. Pre-filing technical disclosure for registered patent agent review.*
