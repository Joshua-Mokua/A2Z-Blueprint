// tests/load/baseline_smoke.js — Sanity check before running the real
// load tests. 1 virtual user, hits /api/health (which has NO auth by
// design — V-001 fix exempts only /api/health), confirms the API is
// reachable.
//
// If this fails, none of the other load tests will work. Run this first.
//
// Run:
//   k6 run --summary-export=results/baseline_smoke.json \
//          tests/load/baseline_smoke.js
//
// Pass criteria:
//   - All requests return 200
//   - p95 < 100ms (health check should be sub-100ms; if it isn't,
//     something's wrong before we even start the real tests)

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.A2Z_API_BASE || "http://localhost:8502";

export const options = {
  vus:        1,
  duration:   "10s",
  thresholds: {
    "http_req_failed":   ["rate<0.01"],   // <1% failures
    "http_req_duration": ["p(95)<100"],   // p95 < 100ms (sanity)
  },
};

export default function () {
  const r = http.get(`${BASE}/api/health`);
  check(r, {
    "status is 200": (resp) => resp.status === 200,
    "body has status field": (resp) => {
      try {
        return resp.json("status") != null;
      } catch (_e) {
        return false;
      }
    },
  });
  sleep(1);
}
