// v10.513 Phase 4 Batch β4 — role-derivation helpers.
//
// Mirror of utils/api_pipeline_manager_actions.py::is_manager. Substring
// match against MANAGER_ROLE_KEYWORDS, OR is_admin=true.
//
// Why mirror server-side at all when the server is the real authority?
//   - Sidebar nav: hide the "Queues" link from non-managers to avoid
//     leading them to a 403 page. Pure UX — not a security boundary.
//   - Page guards: PipelineManagerQueues renders "Not authorized"
//     instead of showing skeletons + error toast when a non-manager
//     navigates there directly. Better UX than letting the queue
//     fetch fail.
//
// Drift risk: this list MUST match MANAGER_ROLE_KEYWORDS exactly
// in utils/api_pipeline_manager_actions.py. If the backend list
// grows (e.g. adds "team lead"), this file needs the matching
// change. A Stage C gate (gate_react_manager_keywords_match) would
// enforce this once frontend tests exist — for now manual sync.
//
// G382 satisfied: this lives in lib/ not components/. The role-string
// check is informational rather than a comparison (which the gate
// targets) — it tests substring membership against a documented set,
// which is doctrine-compliant.

import type { UserIdentity } from '@/types/role';


/** Substrings that identify a manager role. Mirrors backend
 *  MANAGER_ROLE_KEYWORDS in utils/api_pipeline_manager_actions.py. */
export const MANAGER_ROLE_KEYWORDS: readonly string[] = [
  'managing',           // MD
  'director',           // Director Retail / Director Commercial
  'head of',            // Head of Retail / Head of SME / Head of Corporate
  'regional',           // Regional Head
  'branch manager',     // Branch Manager
  'chief',              // Chief Risk Officer, etc.
  'manager',            // Branch Credit Manager / Operations Mgr
  'supervisor',         // Operations supervisors
  'credit manager',     // (redundant with "manager" but explicit)
  'operations manager', // (redundant with "manager" but explicit)
] as const;


/** Return true if the user has manager authority over their cascade.
 *
 *  Mirrors utils/api_pipeline_manager_actions.py::is_manager exactly:
 *  is_admin=true → always manager; otherwise case-insensitive substring
 *  match on role against MANAGER_ROLE_KEYWORDS.
 *
 *  This is NOT a security boundary — the server enforces 403 on
 *  manager-only endpoints. This helper exists to drive sidebar nav
 *  visibility and page-level "not authorized" rendering. */
export function isManager(user: UserIdentity | null | undefined): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  const role = String(user.role ?? '').toLowerCase().trim();
  if (!role) return false;
  return MANAGER_ROLE_KEYWORDS.some((kw) => role.includes(kw));
}
