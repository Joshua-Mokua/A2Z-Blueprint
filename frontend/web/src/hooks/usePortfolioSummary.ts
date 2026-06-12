// v10.541 Phase 8 Batch γ4b — usePortfolioSummary hook.

import { useState, useEffect, useCallback } from 'react';
import { fetchPortfolioSummary, AuthExpiredError } from '@/lib/api';
import type { PortfolioSummary } from '@/types/initiatives';


interface UsePortfolioSummaryValue {
  summary:  PortfolioSummary | null;
  status:   string;
  note:     string | null;
  loading:  boolean;
  error:    string | null;
  refetch:  () => Promise<void>;
}


export function usePortfolioSummary(): UsePortfolioSummaryValue {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [status,  setStatus]  = useState<string>('loading');
  const [note,    setNote]    = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchPortfolioSummary();
      setSummary(resp.summary || null);
      setStatus(resp.status || 'unknown');
      setNote(resp.note || null);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load portfolio summary.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { summary, status, note, loading, error, refetch: load };
}
