// P4-1c — useFxMutations hook. Mirrors useCreditAdminMutations' MutationResult
// discriminated-union shape. Single mutation: upsertRate (admin-only server-side).

import { useState, useCallback } from 'react';
import {
  upsertFxRate,
  ApiValidationError,
  AuthExpiredError,
} from '@/lib/api';
import type { FxRateUpsertRequest, FxRateUpsertResponse } from '@/types/fx';

export type MutationResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status?: number };

export interface FxMutationsHookValue {
  upsertRate: (body: FxRateUpsertRequest) => Promise<MutationResult<FxRateUpsertResponse>>;
  loading:    boolean;
}

export function useFxMutations(): FxMutationsHookValue {
  const [loading, setLoading] = useState(false);

  const upsertRate = useCallback(
    async (body: FxRateUpsertRequest): Promise<MutationResult<FxRateUpsertResponse>> => {
      setLoading(true);
      try {
        const data = await upsertFxRate(body);
        return { ok: true, data };
      } catch (e) {
        if (e instanceof AuthExpiredError) {
          return { ok: false, error: 'Your session expired. Please sign in again.', status: 401 };
        }
        if (e instanceof ApiValidationError) {
          return { ok: false, error: e.message, status: 400 };
        }
        const msg = e instanceof Error ? e.message : 'Failed to save the FX rate.';
        return { ok: false, error: msg };
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return { upsertRate, loading };
}
