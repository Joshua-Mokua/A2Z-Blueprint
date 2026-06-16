// P4-1c — useFxRates list hook. Plain useState/useEffect, mirrors
// useCreditAdminCases (β6).

import { useState, useEffect, useCallback } from 'react';
import { fetchFxRates, AuthExpiredError } from '@/lib/api';
import type { FxRate } from '@/types/fx';

interface UseFxRatesValue {
  rates:         FxRate[];
  baseCurrency:  string;
  loading:       boolean;
  error:         string | null;
  refetch:       () => Promise<void>;
}

export function useFxRates(activeOnly = false): UseFxRatesValue {
  const [rates, setRates]               = useState<FxRate[]>([]);
  const [baseCurrency, setBaseCurrency] = useState<string>('KES');
  const [loading, setLoading]           = useState<boolean>(true);
  const [error, setError]               = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchFxRates(undefined, activeOnly);
      setRates(response.rates);
      setBaseCurrency(response.base_currency);
    } catch (e) {
      if (e instanceof AuthExpiredError) {
        setError('Your session expired. Please sign in again.');
      } else {
        setError(e instanceof Error ? e.message : 'Failed to load FX rates.');
      }
    } finally {
      setLoading(false);
    }
  }, [activeOnly]);

  useEffect(() => { void refetch(); }, [refetch]);

  return { rates, baseCurrency, loading, error, refetch };
}
