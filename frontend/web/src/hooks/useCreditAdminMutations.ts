// v10.522 Phase 4 Batch β6 — useCreditAdminMutations hook.
//
// Two mutations: fulfillCondition (anyone in scope) + disburse (manager-tier).
// Same MutationResult discriminated shape as β5 useLmsMutations.

import { useState, useCallback } from 'react';
import {
  fulfillCreditAdminCondition,
  disburseCreditAdminCase,
  requestCreditAdminAuthorization,
  authorizeCreditAdminCase,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  FulfillConditionRequest,
  DisburseCaseRequest,
  RequestAuthorizationRequest,
  AuthorizeRequest,
  CreditAdminMutationResponse,
} from '@/types/creditAdmin';


export type MutationResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status?: number };


export interface CreditAdminMutationsHookValue {
  /** Mark a condition fulfilled (anyone in scope, case not disbursed). */
  fulfillCondition:  (caseId: string, body: FulfillConditionRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
  /** Clear case for disbursement (manager-tier, ready_for_disbursement). */
  disburse:          (caseId: string, body: DisburseCaseRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
  /** Layer 1: officer requests manager authorization (all conditions met). */
  requestAuthorization: (caseId: string, body: RequestAuthorizationRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
  /** Layer 2: manager authorizes disbursement (pending request). */
  authorize:         (caseId: string, body: AuthorizeRequest) => Promise<MutationResult<CreditAdminMutationResponse>>;
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

  const requestAuthorization = useCallback(
    (caseId: string, body: RequestAuthorizationRequest) =>
      runMutation(requestCreditAdminAuthorization, caseId, body),
    [runMutation],
  );

  const authorize = useCallback(
    (caseId: string, body: AuthorizeRequest) =>
      runMutation(authorizeCreditAdminCase, caseId, body),
    [runMutation],
  );

  return { fulfillCondition, disburse, requestAuthorization, authorize, loading };
}
