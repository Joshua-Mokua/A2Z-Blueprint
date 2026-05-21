// tests/load/concurrent_users.js — Standard #5 metric: 1,000+ concurrent users.
//
// Ramps virtual users from 0 → 1,000 over 2 minutes, holds at 1,000 for
// 3 minutes, ramps back to 0. Asserts the API stays responsive
// (p95 < 500ms) and error rate < 2% under peak load.
//
// IMPORTANT: This is a heavy test. Don't run against production. Don't
// run against shared staging without coordination. Run against a
// dedicated load-test environment with at least 4 vCPU + 8 GB RAM.
//
// Run:
//   k6 run --summary-export=results/concurrent_users.json \
//          tests/load/concurrent_users.js
//
// Pass criteria:
//   - http_req_failed rate < 2% (some failures are expected at 1k VUs)
//   - http_req_duration p95 < 500ms (5x the steady-load threshold;
//     1k concurrent users adds connection contention even on good
//     infrastructure)
//   - vus_max reaches at least 1000 (the spec's target)
//
// Why p95 < 500ms instead of < 200ms here?
//   The < 200ms target in api_p95.js is for STEADY-STATE moderate load.
//   Under 1k concurrent users, connection pool saturation, OS-level
//   socket contention, and FastAPI's worker model all add latency.
//   500ms is the realistic upper bound for "still responsive" under
//   peak. If we measured < 200ms at 1k VUs that'd be a heroic result.

import http from "k6/http";
import { check, sleep } from "k6";
import { login, authHeaders, BASE } from "./lib/auth.js";

const TOKEN = login();

export const options = {
  scenarios: {
    ramp_to_1000: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 1000 },   // ramp up
        { duration: "3m", target: 1000 },   // sustained peak
        { duration: "1m", target: 0    },   // ramp down
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    "http_req_failed":   ["rate<0.02"],     // <2% failures at peak
    "http_req_duration": ["p(95)<500"],     // <500ms under peak load
    "vus_max":           ["value>=1000"],   // STANDARD #5 TARGET
  },
};

// Mostly read endpoints — write endpoints would mutate state and
// invalidate the test on rerun. The dashboard endpoint is a good
// proxy for what users actually do during peak hours (refreshing
// summaries).
const READ_ENDPOINTS = [
  "/api/dashboard/md",
  "/api/bsc/summary",
  "/api/pipeline/summary",
  "/api/credit/summary",
  "/api/aml/summary",
  "/api/v1/pipeline_deals?limit=20",
  "/api/v1/pipeline_deals/dashboard",
];

export default function () {
  const headers = authHeaders(TOKEN);
  const path = READ_ENDPOINTS[Math.floor(Math.random() * READ_ENDPOINTS.length)];
  const r = http.get(`${BASE}${path}`, { headers });
  check(r, {
    "status is 200":  (resp) => resp.status === 200,
    "body non-empty": (resp) => resp.body && resp.body.length > 0,
  });
  // Realistic think time: 1-3s between user actions
  sleep(1 + Math.random() * 2);
}
