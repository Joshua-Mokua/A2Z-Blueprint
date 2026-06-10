// v10.511 Phase 4 Batch β2 — usePipelineDealMutations hook.
//
// Encapsulates the mutation lifecycle for the two owner-side actions
// shipped in β2: advance stage + request cancellation. Each mutation
// returns a discriminated result the page can switch on:
//   { ok: true,  data: <response> }
//   { ok: false, error: string, status?: number }
//
// Why a discriminated result instead of throw/try-catch:
//   - Mutation call sites are usually button handlers — the throw/catch
//     pattern requires every handler to wrap a try/catch, which is
//     boilerplate-heavy and easy to forget.
//   - With { ok, ... } the type system forces the call site to handle
//     both paths (TypeScript's discriminated union narrowing).
//   - Errors that should propagate (network failures, 5xx) still throw;
//     only "expected" validation errors return as { ok: false }.
//
// Doctrine note (CGR1): TanStack Query has an idiomatic useMutation
// hook that does this and more. β2 builds this manually to keep with
// the Context-Provider + bare hooks pattern Joshua chose for β1. When
// OI-63 lands, this hook becomes a thin wrapper over useMutation.
//
// Refetch semantics:
//   The hook does NOT call PipelineProvider.refetch automatically — it
//   has no way to (PipelineProvider lives above /pipeline only, not
//   above the detail route). The detail page is expected to refetch
//   its OWN deal data on success (via the usePipelineDealDetail hook
//   it'll own). The list will naturally refresh when the user navigates
//   back to /pipeline (PipelineProvider remounts).

import { useState, useCallback } from 'react';
import {
  advancePipelineDeal,
  requestPipelineDealCancel,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  AdvanceDealRequest, AdvanceDealResponse,
  RequestCancelRequest, RequestCancelResponse,
} from '@/types/pipeline';


// ── Discriminated result shape ──────────────────────────────────────────

export type MutationResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status?: number };


// ── Hook return shape ───────────────────────────────────────────────────

export interface PipelineDealMutationsHookValue {
  /** Submit an advance. Returns ok+data on success, ok=false+error on validation failure. */
  advance:        (dealId: string, body: AdvanceDealRequest) => Promise<MutationResult<AdvanceDealResponse>>;
  /** Submit a cancellation request. Same result shape. */
  requestCancel:  (dealId: string, body: RequestCancelRequest) => Promise<MutationResult<RequestCancelResponse>>;
  /** True while ANY mutation from this hook instance is in flight. */
  loading:        boolean;
}


// ── Hook implementation ─────────────────────────────────────────────────

export function usePipelineDealMutations(): PipelineDealMutationsHookValue {
  const [loading, setLoading] = useState(false);

  const runMutation = useCallback(async <TBody, TResponse>(
    fn: (dealId: string, body: TBody) => Promise<TResponse>,
    dealId: string,
    body: TBody,
  ): Promise<MutationResult<TResponse>> => {
    setLoading(true);
    try {
      const data = await fn(dealId, body);
      return { ok: true, data };
    } catch (e) {
      // ApiValidationError is the expected failure mode — server says
      // "your input was wrong" with a specific reason. Return as
      // structured failure so the form can show the message inline.
      if (e instanceof ApiValidationError) {
        return { ok: false, error: e.detail, status: e.status };
      }
      // AuthExpiredError was already handled by AuthProvider's 401
      // callback (token cleared, status → 'expired'). Surface a stable
      // message so the form shows something useful before the redirect
      // to /login happens.
      if (e instanceof AuthExpiredError) {
        return { ok: false, error: 'Your session expired. Please sign in again.' };
      }
      // Network failures, 5xx, anything else — surface the message
      // (typically "API ... failed: 500 Internal Server Error" or
      // a fetch network error).
      const msg = e instanceof Error ? e.message : 'Mutation failed';
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const advance = useCallback(
    (dealId: string, body: AdvanceDealRequest) =>
      runMutation(advancePipelineDeal, dealId, body),
    [runMutation],
  );

  const requestCancel = useCallback(
    (dealId: string, body: RequestCancelRequest) =>
      runMutation(requestPipelineDealCancel, dealId, body),
    [runMutation],
  );

  return { advance, requestCancel, loading };
}
