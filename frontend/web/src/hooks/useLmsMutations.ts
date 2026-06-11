// v10.520 Phase 4 Batch β5 — useLmsMutations hook.
//
// Mirrors usePipelineDealMutations shape: each mutation returns
// MutationResult<T> = { ok: true, data } | { ok: false, error, status? }
// so call sites get TypeScript-enforced discriminated handling.
//
// Three mutations for α8 LMS routes:
//   - assign         POST /api/lms/applications/{id}/assign
//   - update         PUT  /api/lms/applications/{id}
//   - recordDecision POST /api/lms/applications/{id}/decision
//
// All require Bearer JWT. Server enforces tier checks (manager-only
// for assign/decision) and status guardrails. Validation failures
// come back as ApiValidationError (translated to ok:false).

import { useState, useCallback } from 'react';
import {
  assignLmsAnalyst,
  updateLmsApplication,
  recordLmsDecision,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  AssignAnalystRequest,
  LoanAppUpdateRequest,
  RecordDecisionRequest,
  LoanAppMutationResponse,
} from '@/types/lms';


// Reuse the same discriminated result type as pipeline mutations
export type MutationResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status?: number };


export interface LmsMutationsHookValue {
  /** Assign analyst (manager-tier, status=submitted). */
  assign:          (appId: string, body: AssignAnalystRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  /** Partial update (status=submitted|assigned, in-scope stake). */
  update:          (appId: string, body: LoanAppUpdateRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  /** Record decision (manager-tier, status=submitted|assigned). */
  recordDecision:  (appId: string, body: RecordDecisionRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  /** True while any mutation from this instance is in flight. */
  loading:         boolean;
}


export function useLmsMutations(): LmsMutationsHookValue {
  const [loading, setLoading] = useState(false);

  const runMutation = useCallback(async <TBody, TResponse>(
    fn: (appId: string, body: TBody) => Promise<TResponse>,
    appId: string,
    body: TBody,
  ): Promise<MutationResult<TResponse>> => {
    setLoading(true);
    try {
      const data = await fn(appId, body);
      return { ok: true, data };
    } catch (e) {
      if (e instanceof ApiValidationError) {
        return { ok: false, error: e.detail, status: e.status };
      }
      if (e instanceof AuthExpiredError) {
        throw e;  // Let global handler redirect
      }
      // Network errors, 5xx — return as failure but propagate later if needed
      const msg = e instanceof Error ? e.message : 'Mutation failed.';
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const assign = useCallback(
    (appId: string, body: AssignAnalystRequest) =>
      runMutation(assignLmsAnalyst, appId, body),
    [runMutation],
  );

  const update = useCallback(
    (appId: string, body: LoanAppUpdateRequest) =>
      runMutation(updateLmsApplication, appId, body),
    [runMutation],
  );

  const recordDecision = useCallback(
    (appId: string, body: RecordDecisionRequest) =>
      runMutation(recordLmsDecision, appId, body),
    [runMutation],
  );

  return { assign, update, recordDecision, loading };
}
