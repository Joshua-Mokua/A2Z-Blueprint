// v10.542 — fetcher for the canonical execute-initiatives list.
// Mirrors the fetchPortfolioSummary pattern: getJson prepends API_BASE='/api',
// so the path is '/initiatives' (NOT '/api/initiatives').
import { getJson } from '@/lib/api';
import type { ExecuteInitiativesResponse } from '@/types/executeInitiatives';

export async function fetchExecuteInitiatives(
  status: string = 'All',
): Promise<ExecuteInitiativesResponse> {
  return getJson<ExecuteInitiativesResponse>(
    `/initiatives?status=${encodeURIComponent(status)}`,
  );
}
