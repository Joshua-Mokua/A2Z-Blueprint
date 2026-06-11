// v10.533 Phase 5 Batch γ3b — useMyCascade hook.
//
// Combines 3 parallel fetches the Cascade landing page needs:
//   - Bank-level targets (the 21 KPIs at MD level)
//   - What was given to me (incoming allocations)
//   - What I've allocated out (outgoing cascade entries)
//
// Parallel fetch: independent endpoints, no ordering dependency.
// If any fails, that section shows its own error message but the
// other two still render. The whole-hook `loading` is true until
// ALL three finish (success or failure).

import { useState, useEffect, useCallback } from 'react';
import {
  fetchBankTargets,
  fetchMyCascadeAllocations,
  fetchGivenToMe,
  AuthExpiredError,
} from '@/lib/api';
import {
  normalizeCascadeEntries,
  type BankTarget,
  type CascadeEntry,
  type IncomingAllocation,
} from '@/types/cascade';


interface UseMyCascadeValue {
  // Bank targets
  bankTargets:           BankTarget[];
  bankTargetsLoading:    boolean;
  bankTargetsError:      string | null;

  // Incoming
  incoming:              IncomingAllocation[];
  incomingLoading:       boolean;
  incomingError:         string | null;

  // Outgoing (my allocations)
  outgoing:              CascadeEntry[];
  outgoingLoading:       boolean;
  outgoingError:         string | null;

  // Aggregate
  allLoaded:             boolean;
  refetch:               () => Promise<void>;
}


export function useMyCascade(period: string = '2026'): UseMyCascadeValue {
  // Bank targets
  const [bankTargets, setBankTargets] = useState<BankTarget[]>([]);
  const [bankTargetsLoading, setBankTargetsLoading] = useState<boolean>(true);
  const [bankTargetsError,   setBankTargetsError]   = useState<string | null>(null);

  // Incoming
  const [incoming, setIncoming] = useState<IncomingAllocation[]>([]);
  const [incomingLoading, setIncomingLoading] = useState<boolean>(true);
  const [incomingError,   setIncomingError]   = useState<string | null>(null);

  // Outgoing
  const [outgoing, setOutgoing] = useState<CascadeEntry[]>([]);
  const [outgoingLoading, setOutgoingLoading] = useState<boolean>(true);
  const [outgoingError,   setOutgoingError]   = useState<string | null>(null);


  const loadBankTargets = useCallback(async () => {
    setBankTargetsLoading(true);
    setBankTargetsError(null);
    try {
      const resp = await fetchBankTargets(period);
      setBankTargets(resp.targets || []);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load bank targets.';
      setBankTargetsError(msg);
    } finally {
      setBankTargetsLoading(false);
    }
  }, [period]);

  const loadIncoming = useCallback(async () => {
    setIncomingLoading(true);
    setIncomingError(null);
    try {
      const resp = await fetchGivenToMe(period);
      setIncoming(resp.allocations || []);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load incoming allocations.';
      setIncomingError(msg);
    } finally {
      setIncomingLoading(false);
    }
  }, [period]);

  const loadOutgoing = useCallback(async () => {
    setOutgoingLoading(true);
    setOutgoingError(null);
    try {
      const resp = await fetchMyCascadeAllocations(period);
      setOutgoing(normalizeCascadeEntries(resp.allocations));
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load outgoing allocations.';
      setOutgoingError(msg);
    } finally {
      setOutgoingLoading(false);
    }
  }, [period]);


  const refetch = useCallback(async () => {
    // Parallel — don't block one on another
    await Promise.allSettled([loadBankTargets(), loadIncoming(), loadOutgoing()]);
  }, [loadBankTargets, loadIncoming, loadOutgoing]);


  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  const allLoaded = !bankTargetsLoading && !incomingLoading && !outgoingLoading;

  return {
    bankTargets,    bankTargetsLoading,    bankTargetsError,
    incoming,       incomingLoading,       incomingError,
    outgoing,       outgoingLoading,       outgoingError,
    allLoaded,
    refetch,
  };
}
