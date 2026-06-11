// v10.522 Phase 4 Batch β6 — useCreditAdminMutations hook.
//
// Two mutations: fulfillCondition (anyone in scope) + disburse (manager-tier).
// Same MutationResult discriminated shape as β5 useLmsMutations.

import { useState, useCallback } from 'react';
import {
  fulfillCreditAdminCondition,
  disburseCreditAdminCase,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  FulfillConditionRequest,
  DisburseCaseRequest,
  CreditAdminMutationResponse,
} from '@/types/creditAdmin';


export type MutationResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status?: number };


export interface CreditAdminMutationsHookValue {
  /** Mark a condition fulfilled (anyone in scope, case not disbursed). */
  fulfillCondition:  (caseId: string, body: FulfillConditionRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
  /** Clear case for disbursement (manager-tier, all conditions met). */
  disburse:          (caseId: string, body: DisburseCaseRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
  /** True while any mutation from this instance is in flight. */
  loading:           boolean;
}


export function useCreditAdminMutations(): CreditAdminMutationsHookValue {
  const [loading, setLoading] = useState(false);

  const runMutation = useCallback(async <TBody, TResponse>(
    fn: (caseId: string, body: TBody) => Promise<TResponse>,
    caseId: string,
    body: TBody,
  ): Promise<MutationResult<TResponse>> => {
    setLoading(true);
    try {
      const data = await fn(caseId, body);
      return { ok: true, data };
    } catch (e) {
      if (e instanceof ApiValidationError) {
        return { ok: false, error: e.detail, status: e.status };
      }
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Mutation failed.';
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const fulfillCondition = useCallback(
    (caseId: string, body: FulfillConditionRequest) =>
      runMutation(fulfillCreditAdminCondition, caseId, body),
    [runMutation],
  );

  const disburse = useCallback(
    (caseId: string, body: DisburseCaseRequest) =>
      runMutation(disburseCreditAdminCase, caseId, body),
    [runMutation],
  );

  return { fulfillCondition, disburse, loading };
}
