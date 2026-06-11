// v10.531 Phase 5 Batch γ2 — useCustomerSearch debounced hook.
//
// Returns matches from GET /api/cbs/customers?q= after a debounce
// window. Cancels stale requests so the displayed results always
// match the most recent query (no jitter from out-of-order responses).
//
// Behavior:
//   - Query < 3 chars: returns immediately with empty list, no fetch.
//   - Query >= 3 chars: schedules a fetch after `debounceMs` (default 300)
//     of no further typing. Each new keystroke resets the timer.
//   - In-flight fetches are abandoned (via stale-request guard) when
//     the user keeps typing — only the latest query's result is shown.

import { useState, useEffect, useRef } from 'react';
import { searchCbsCustomers, AuthExpiredError } from '@/lib/api';
import type { CbsCustomer } from '@/types/cbs';


interface UseCustomerSearchValue {
  results:    CbsCustomer[];
  loading:    boolean;
  error:      string | null;
  /** True when a query >= 3 chars is active (whether or not loading). */
  active:     boolean;
}


export function useCustomerSearch(
  query: string,
  debounceMs: number = 300,
  limit: number = 10,
): UseCustomerSearchValue {
  const [results, setResults] = useState<CbsCustomer[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error,   setError]   = useState<string | null>(null);

  // Counter that increments on every fetch start; older fetches
  // discard their results if the counter has moved past them.
  const requestCounter = useRef<number>(0);

  const q = query.trim();
  const active = q.length >= 3;

  useEffect(() => {
    // Below-minimum: clear and return immediately.
    if (q.length < 3) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }

    // Schedule a debounced fetch.
    setLoading(true);
    const myRequestId = ++requestCounter.current;

    const timer = setTimeout(async () => {
      try {
        const response = await searchCbsCustomers(q, limit);
        // Stale-guard: only commit if no newer request has started.
        if (myRequestId === requestCounter.current) {
          setResults(response.customers);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (e instanceof AuthExpiredError) {
          // Let global handler redirect; stop the spinner.
          if (myRequestId === requestCounter.current) {
            setLoading(false);
          }
          return;
        }
        if (myRequestId === requestCounter.current) {
          const msg = e instanceof Error ? e.message : 'Search failed.';
          setError(msg);
          setResults([]);
          setLoading(false);
        }
      }
    }, debounceMs);

    // Cleanup: if effect re-runs (user typed another character) the
    // timer is cancelled before it fires. Combined with the stale-guard
    // this gives bulletproof out-of-order safety.
    return () => clearTimeout(timer);
  }, [q, debounceMs, limit]);

  return { results, loading, error, active };
}
