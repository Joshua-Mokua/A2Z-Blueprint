// tests/load/export_10k.js — Standard #5 metric: Export (10K rows) < 10s.
//
// Hits the /api/v1/pipeline_deals/export endpoint with limit=10000 and
// asserts the request completes in under 10 seconds. Uses 10 concurrent
// virtual users so we get a p95 distribution rather than a single
// measurement.
//
// Run:
//   k6 run --summary-export=results/export_10k.json tests/load/export_10k.js
//
// Pass criteria:
//   - Each export request completes < 10s (per-iteration check)
//   - p95 of total request duration < 10s (Standard #5 target)
//   - http_req_failed rate < 1%
//
// Setup notes:
//   - The pilot table (pipeline_deals) needs to actually have ≥10k rows
//     in PG for this test to be meaningful. In a fresh staging env you
//     may need to seed data:
//       python scripts/seed_pipeline_test_data.py --rows 12000
//     (To be added later — out of scope for v5.34.)
//   - If pipeline_deals has < 10k rows, the test still runs; it just
//     measures "export N rows" where N is whatever's there. The
//     duration threshold is still enforced.

import http from "k6/http";
import { check } from "k6";
import { login, authHeaders, BASE } from "./lib/auth.js";

const TOKEN = login();

export const options = {
  scenarios: {
    export_load: {
      executor: "constant-vus",
      vus:      10,           // moderate concurrency for export
      duration: "2m",
      gracefulStop: "15s",
    },
  },
  thresholds: {
    "http_req_failed":                          ["rate<0.01"],
    "http_req_duration{kind:export_10k}":       ["p(95)<10000"],   // STANDARD #5 TARGET
    "iteration_duration{scenario:export_load}": ["p(99)<15000"],   // hard upper bound
  },
};

export default function () {
  const headers = authHeaders(TOKEN);
  const body    = JSON.stringify({ limit: 10000, offset: 0 });
  const params  = { headers, tags: { kind: "export_10k" }, timeout: "30s" };

  const r = http.post(`${BASE}/api/v1/pipeline_deals/export`, body, params);

  check(r, {
    "status is 200":         (resp) => resp.status === 200,
    "duration under 10s":    (resp) => resp.timings.duration < 10000,
    "body has rows array":   (resp) => {
      try {
        const json = resp.json();
        return Array.isArray(json.rows);
      } catch (_e) {
        return false;
      }
    },
  });
}
