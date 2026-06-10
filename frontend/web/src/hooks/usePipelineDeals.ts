// v10.510 Phase 4 Batch β1 — usePipelineDeals hook.
//
// Returns the cascade-scoped deal list from PipelineContext plus a
// refetch action. Pure context consumer — mirrors useAuth / useRole /
// useBranding patterns. All state, fetching, and error handling lives
// in PipelineProvider.
//
// Usage:
//   const { deals, count, loading, error, refetch } = usePipelineDeals();
//
//   if (loading) return <Skeleton />;
//   if (error)   return <ErrorPanel msg={error} />;
//   return <Table rows={deals} ... />;
//
// To refetch after a mutation (β2 onward):
//   await refetch();                       // re-run with last query
//   await refetch({ stage: 'Contacted' }); // new filter
//
// Each deal has a `permissions: DealPermissions` object (α7). The
// React UI consumes this directly — never recomputes authorization
// client-side.

import { useContext } from 'react';
import { PipelineContext } from '@/providers/PipelineProvider';

export function usePipelineDeals() {
  return useContext(PipelineContext);
}
