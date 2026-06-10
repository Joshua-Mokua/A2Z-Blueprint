// v10.511 Phase 4 Batch β2 — usePipelineDealMutations hook.
// v10.512 Phase 4 Batch β3 — extended with create + refer methods.
//
// Encapsulates the mutation lifecycle for owner-side actions:
//   β2: advance stage + request cancellation
//   β3: create deal + refer to portfolio owner
//
// Each mutation returns a discriminated result the page can switch on:
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
//   above the detail or create routes). Pages that need a re-render
//   after success handle it themselves (detail page reloads its own
//   deal; create page navigates to detail of the new deal).

import { useState, useCallback } from 'react';
import {
  advancePipelineDeal,
  requestPipelineDealCancel,
  createPipelineDeal,
  referPipelineDeal,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type {
  AdvanceDealRequest, AdvanceDealResponse,
  RequestCancelRequest, RequestCancelResponse,
  CreateDealRequest, CreateDealResponse,
  ReferDealRequest, ReferDealResponse,
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
  /** Create a new deal (β3). Same result shape. */
  create:         (body: CreateDealRequest)  => Promise<MutationResult<CreateDealResponse>>;
  /** Refer a deal to its portfolio owner (β3). Same result shape. */
  refer:          (body: ReferDealRequest)   => Promise<MutationResult<ReferDealResponse>>;
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

  // Body-only mutation runner — for endpoints that don't take a path
  // param (create, refer). Mirrors runMutation but without dealId.
  const runBodyMutation = useCallback(async <TBody, TResponse>(
    fn: (body: TBody) => Promise<TResponse>,
    body: TBody,
  ): Promise<MutationResult<TResponse>> => {
    setLoading(true);
    try {
      const data = await fn(body);
      return { ok: true, data };
    } catch (e) {
      if (e instanceof ApiValidationError) {
        return { ok: false, error: e.detail, status: e.status };
      }
      if (e instanceof AuthExpiredError) {
        return { ok: false, error: 'Your session expired. Please sign in again.' };
      }
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

  const create = useCallback(
    (body: CreateDealRequest) =>
      runBodyMutation(createPipelineDeal, body),
    [runBodyMutation],
  );

  const refer = useCallback(
    (body: ReferDealRequest) =>
      runBodyMutation(referPipelineDeal, body),
    [runBodyMutation],
  );

  return { advance, requestCancel, create, refer, loading };
}
