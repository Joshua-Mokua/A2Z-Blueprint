// tests/load/api_p95.js — Standard #5 metric: API response p95 < 200ms.
//
// Hits the read-heavy endpoints (the ones React dashboards will call
// most often) at moderate load. Asserts p95 < 200ms across the whole
// scenario.
//
// Run:
//   k6 run --summary-export=results/api_p95.json tests/load/api_p95.js
//
// Pass criteria:
//   - http_req_duration p95 < 200ms (the spec's Standard #5 target)
//   - http_req_failed rate < 1%
//   - All endpoints return 200
//
// Endpoints exercised (8 of the most common reads):
//   GET /api/auth/me
//   GET /api/health
//   GET /api/bsc/summary
//   GET /api/pipeline/summary
//   GET /api/credit/summary
//   GET /api/aml/summary
//   GET /api/dashboard/md
//   GET /api/v1/pipeline_deals?limit=50

import http from "k6/http";
import { check, sleep } from "k6";
import { login, authHeaders, BASE } from "./lib/auth.js";

// k6 init context — runs once. Acquire a token here.
const TOKEN = login();

export const options = {
  scenarios: {
    steady_load: {
      executor:           "constant-vus",
      vus:                50,    // moderate concurrency
      duration:           "60s",
      gracefulStop:       "10s",
    },
  },
  thresholds: {
    "http_req_failed":                ["rate<0.01"],          // <1% failures
    "http_req_duration":              ["p(95)<200"],          // STANDARD #5 TARGET
    "http_req_duration{kind:dashboard}": ["p(95)<3000"],      // dashboard < 3s
  },
};

// ENDPOINTS lists (path, kind-tag) pairs. The kind tag lets us slice
// thresholds — e.g. dashboards have a different SLA than micro-reads.
const ENDPOINTS = [
  { path: "/api/auth/me",                     kind: "auth"      },
  { path: "/api/health",                      kind: "health"    },
  { path: "/api/bsc/summary",                 kind: "summary"   },
  { path: "/api/pipeline/summary",            kind: "summary"   },
  { path: "/api/credit/summary",              kind: "summary"   },
  { path: "/api/aml/summary",                 kind: "summary"   },
  { path: "/api/dashboard/md",                kind: "dashboard" },
  { path: "/api/v1/pipeline_deals?limit=50",  kind: "list"      },
];

export default function () {
  const headers = authHeaders(TOKEN);
  // Pick a random endpoint each iteration to spread the load
  const ep = ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];
  const r = http.get(`${BASE}${ep.path}`, { headers, tags: { kind: ep.kind } });
  check(r, {
    [`${ep.path} returns 200`]: (resp) => resp.status === 200,
  });
  // Small think time between requests — realistic user behaviour
  sleep(0.1 + Math.random() * 0.4);
}
