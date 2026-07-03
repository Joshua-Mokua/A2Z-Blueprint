// useAccountLookup — debounced account-number lookup hook.
//
// As the user types an account number, fires GET /api/cbs/accounts/{num}/360
// after the debounce window. Returns the combined account + loans payload.
//
// Minimum length before fetching is 7 chars (FlexCube account numbers are
// long — avoids spamming the API on the first few keystrokes).
// Stale-request guard ensures only the most recent result is committed.

import { useState, useEffect, useRef } from 'react';
import { fetchCbsAccount360, AuthExpiredError } from '@/lib/api';
import type { CbsAccount360 } from '@/types/cbs';

const MIN_CHARS    = 7;
const DEFAULT_WAIT = 400; // ms — slightly longer than name search (accounts are typed, not searched)

interface UseAccountLookupValue {
  account:  CbsAccount360 | null;
  loading:  boolean;
  error:    string | null;
  notFound: boolean;
}

export function useAccountLookup(
  accountNumber: string,
  debounceMs: number = DEFAULT_WAIT,
): UseAccountLookupValue {
  const [account,  setAccount]  = useState<CbsAccount360 | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const reqRef = useRef(0);

  const num = accountNumber.trim();

  useEffect(() => {
    if (num.length < MIN_CHARS) {
      setAccount(null);
      setError(null);
      setNotFound(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    setNotFound(false);
    const id = ++reqRef.current;

    const timer = setTimeout(async () => {
      try {
        const resp = await fetchCbsAccount360(num);
        if (id === reqRef.current) {
          setAccount(resp.account);
          setError(null);
          setNotFound(false);
          setLoading(false);
        }
      } catch (e: unknown) {
        if (e instanceof AuthExpiredError) {
          if (id === reqRef.current) setLoading(false);
          return;
        }
        if (id === reqRef.current) {
          const is404 = (e as { status?: number }).status === 404;
          setNotFound(is404);
          setError(is404 ? null : (e instanceof Error ? e.message : 'Lookup failed.'));
          setAccount(null);
          setLoading(false);
        }
      }
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [num, debounceMs]);

  return { account, loading, error, notFound };
}
