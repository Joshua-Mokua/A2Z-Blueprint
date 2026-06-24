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
  requestLmsInfo,
  provideLmsInfo,
  escalateLmsApplication,
  addLmsManagerView,
  signLmsOffer,
  validateLmsOffer,
  confirmLmsToCreditAdmin,
  referLmsCommittee,
  voteLmsCommittee,
  resolveLmsCommittee,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  AssignAnalystRequest,
  LoanAppUpdateRequest,
  RecordDecisionRequest,
  RequestInfoRequest,
  ProvideInfoRequest,
  SignOfferRequest,
  ValidateOfferRequest,
  ConfirmToCreditAdminRequest,
  CommitteeVoteRequest,
  ResolveCommitteeRequest,
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
  requestInfo:     (appId: string, body: RequestInfoRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  provideInfo:     (appId: string, body: ProvideInfoRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  escalate:        (appId: string, body: { reason: string; to_manager?: string }) => Promise<MutationResult<LoanAppMutationResponse>>;
  managerView:     (appId: string, body: { view: string }) => Promise<MutationResult<LoanAppMutationResponse>>;
  signOffer:       (appId: string, body: SignOfferRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  validateOffer:   (appId: string, body: ValidateOfferRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  confirmToCreditAdmin: (appId: string, body: ConfirmToCreditAdminRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  referCommittee:  (appId: string) => Promise<MutationResult<LoanAppMutationResponse>>;
  voteCommittee:   (appId: string, body: CommitteeVoteRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
  resolveCommittee:(appId: string, body: ResolveCommitteeRequest) => Promise<MutationResult<LoanAppMutationResponse>>;
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

  const requestInfo = useCallback(
    (appId: string, body: RequestInfoRequest) => runMutation(requestLmsInfo, appId, body), [runMutation]);
  const provideInfo = useCallback(
    (appId: string, body: ProvideInfoRequest) => runMutation(provideLmsInfo, appId, body), [runMutation]);
  const escalate = useCallback(
    (appId: string, body: { reason: string; to_manager?: string }) => runMutation(escalateLmsApplication, appId, body), [runMutation]);
  const managerView = useCallback(
    (appId: string, body: { view: string }) => runMutation(addLmsManagerView, appId, body), [runMutation]);
  const signOffer = useCallback(
    (appId: string, body: SignOfferRequest) => runMutation(signLmsOffer, appId, body), [runMutation]);
  const validateOffer = useCallback(
    (appId: string, body: ValidateOfferRequest) => runMutation(validateLmsOffer, appId, body), [runMutation]);
  const confirmToCreditAdmin = useCallback(
    (appId: string, body: ConfirmToCreditAdminRequest) => runMutation(confirmLmsToCreditAdmin, appId, body), [runMutation]);
  const referCommittee = useCallback(
    (appId: string) => runMutation((id: string, _b: Record<string, never>) => referLmsCommittee(id), appId, {} as Record<string, never>), [runMutation]);
  const voteCommittee = useCallback(
    (appId: string, body: CommitteeVoteRequest) => runMutation(voteLmsCommittee, appId, body), [runMutation]);
  const resolveCommittee = useCallback(
    (appId: string, body: ResolveCommitteeRequest) => runMutation(resolveLmsCommittee, appId, body), [runMutation]);

  return {
    assign, update, recordDecision,
    requestInfo, provideInfo, signOffer, validateOffer, confirmToCreditAdmin,
    escalate, managerView,
    referCommittee, voteCommittee, resolveCommittee,
    loading,
  };
}
