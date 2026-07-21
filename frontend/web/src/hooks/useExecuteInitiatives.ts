// v10.542 — useExecuteInitiatives: load the milestone-bearing initiatives.
import { useState, useEffect, useCallback } from 'react';
import { fetchExecuteInitiatives } from '@/lib/executeInitiativesFetch';
import type { ExecuteInitiative } from '@/types/executeInitiatives';

interface Value {
  initiatives: ExecuteInitiative[];
  status: string;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useExecuteInitiatives(statusFilter: string = 'All'): Value {
  const [initiatives, setInitiatives] = useState<ExecuteInitiative[]>([]);
  const [status, setStatus] = useState<string>('loading');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchExecuteInitiatives(statusFilter);
      setInitiatives(Array.isArray(res.initiatives) ? res.initiatives : []);
      setStatus(res.status || 'ok');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load initiatives');
      setStatus('error');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { void load(); }, [load]);
  return { initiatives, status, loading, error, refetch: load };
}
