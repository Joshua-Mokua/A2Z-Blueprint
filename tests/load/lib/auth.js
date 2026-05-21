// tests/load/lib/auth.js — Shared k6 helper for V-001 JWT auth.
//
// Every endpoint except /api/health requires a Bearer JWT (per v5.17).
// Each load test calls login() once during init() and reuses the token
// across all requests. Don't put the login call inside the per-iteration
// scenario function or you'll DDoS the auth endpoint.
//
// Environment variables:
//   A2Z_API_BASE     base URL, default "http://localhost:8502"
//   A2Z_TEST_USER    username for login, default "william001"
//   A2Z_TEST_PASS    password for login, default "ECOStaff001"
//
// Usage:
//   import { login, authHeaders, BASE } from "./lib/auth.js";
//   const TOKEN = login();
//   export default function () {
//     http.get(`${BASE}/api/v1/pipeline_deals`, { headers: authHeaders(TOKEN) });
//   }

import http from "k6/http";
import { check } from "k6";

export const BASE = __ENV.A2Z_API_BASE || "http://localhost:8502";
const TEST_USER = __ENV.A2Z_TEST_USER || "william001";
const TEST_PASS = __ENV.A2Z_TEST_PASS || "ECOStaff001";

// login() exchanges username+password for a JWT bearer token. Run once
// during k6 init (before scenarios start). The returned string is the
// full bearer token (without the "Bearer " prefix); pass it through
// authHeaders() when making requests.
export function login() {
  const body = JSON.stringify({ username: TEST_USER, password: TEST_PASS });
  const params = { headers: { "Content-Type": "application/json" } };
  const r = http.post(`${BASE}/api/auth/login`, body, params);
  check(r, {
    "login returns 200":          (resp) => resp.status === 200,
    "login response has token":   (resp) => resp.json("access_token") != null,
  });
  if (r.status !== 200) {
    throw new Error(`Login failed (HTTP ${r.status}): ${r.body}`);
  }
  return r.json("access_token");
}

// authHeaders(token) builds a headers object with Authorization +
// Content-Type for JSON. Call inside the scenario function for each
// request.
export function authHeaders(token) {
  return {
    "Authorization": `Bearer ${token}`,
    "Content-Type":  "application/json",
  };
}
