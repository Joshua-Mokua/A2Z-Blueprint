// React-A (P4-6 UI) — Disbursement gate checklist + tier-aware override.
//
// Self-contained: fetches GET /disbursement-gate, renders a green/red checklist
// of secured-lending controls, and (when blocked) a controlled-override flow
// that shows the authority tier and per-role approval status. Calls onChange
// after a successful override so the parent can refetch the case.

import { useEffect, useState, useCallback } from 'react';
import {
  fetchDisbursementGate, requestOverride, approveOverride,
  ApiValidationError, AuthExpiredError,
} from '@/lib/api';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import type { DisbursementGate, GateFailure } from '@/types/creditAdmin';

const CHECK_LABELS: Record<string, string> = {
  conditions_precedent: 'Conditions Precedent',
  legal_review:         'Legal Review',
  security_perfection:  'Security Perfection',
  insurance:            'Insurance',
  coverage:             'Collateral Coverage',
  valuation:            'Valuation Freshness',
};

const ROLE_LABELS: Record<string, string> = {
  head_of_credit: 'Head of Credit',
  cro:            'Chief Risk Officer',
  md:             'Managing Director',
  admin:          'Administrator',
};

function failureLine(f: GateFailure): string {
  if (f.check === 'coverage' && f.coverage_ratio != null && f.required_ratio != null) {
    return `${f.reason} (coverage ${f.coverage_ratio}× vs required ${f.required_ratio}×)`;
  }
  return f.reason;
}

interface Props {
  caseId: string;
  onChange?: () => void;   // parent refetch after override
}

export function DisbursementGatePanel({ caseId, onChange }: Props) {
  const toast = useToast();
  const [gate, setGate]       = useState<DisbursementGate | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy]       = useState(false);
  const [justification, setJustification] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setGate(await fetchDisbursementGate(caseId));
    } catch {
      setGate(null);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => { void load(); }, [load]);

  const handleError = (e: unknown) => {
    if (e instanceof AuthExpiredError) return 'Your session expired. Please sign in again.';
    if (e instanceof ApiValidationError) return e.message;
    return e instanceof Error ? e.message : 'Request failed.';
  };

  async function doRequest() {
    if (!justification.trim()) {
      toast.toast({ tone: 'warning', message: 'A justification is required to open an override.' });
      return;
    }
    setBusy(true);
    try {
      await requestOverride(caseId, { justification });
      toast.toast({ tone: 'success', message: 'Override requested. Awaiting authority approval.' });
      setJustification('');
      await load(); onChange?.();
    } catch (e) {
      toast.toast({ tone: 'danger', message: handleError(e) });
    } finally { setBusy(false); }
  }

  async function doApprove() {
    setBusy(true);
    try {
      const res = await approveOverride(caseId);
      toast.toast({ tone: 'success', message: `Override ${res.status.replace('override_', '')}.` });
      await load(); onChange?.();
    } catch (e) {
      toast.toast({ tone: 'danger', message: handleError(e) });
    } finally { setBusy(false); }
  }

  if (loading) return null;
  if (!gate || !gate.secured) return null;   // unsecured: standard disburse panel applies

  const ov = gate.override || null;
  const approvedRoles = new Set((ov?.approvals || []).map((a) => a.role));
  const requiredRoles = gate.high_value ? ['head_of_credit', 'cro', 'md'] : ['head_of_credit', 'cro', 'md'];
  const tierText = gate.high_value
    ? 'High-value facility — requires Head of Credit AND Chief Risk Officer AND Managing Director'
    : 'Standard facility — requires any one of Head of Credit, Chief Risk Officer, or Managing Director';

  return (
    <Card className="mt-6" stripe={gate.passed ? 'primary' : 'accent'}>
      <Card.Header>
        <div className="flex items-center justify-between">
          <span className="font-medium">Secured-lending disbursement gate</span>
          <Badge tone={gate.passed ? 'success' : 'danger'}>
            {gate.passed ? (gate.overridden ? 'Cleared (override)' : 'Ready') : 'Blocked'}
          </Badge>
        </div>
      </Card.Header>
      <Card.Body>
        {gate.failures.length === 0 ? (
          <p className="text-sm text-green-700">All secured-lending controls satisfied.</p>
        ) : (
          <ul className="space-y-2">
            {gate.failures.map((f) => (
              <li key={f.check} className="flex items-start gap-2 text-sm">
                <span className="text-red-600 mt-0.5">✕</span>
                <span>
                  <span className="font-medium">{CHECK_LABELS[f.check] || f.check}:</span>{' '}
                  <span className="text-gray-600">{failureLine(f)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}

        {!gate.passed && (
          <div className="mt-5 border-t pt-4">
            <div className="text-sm font-medium mb-1">Controlled override</div>
            <p className="text-xs text-gray-500 mb-3">{tierText}</p>

            {!ov && (
              <div className="space-y-2">
                <textarea
                  className="w-full border rounded px-3 py-2 text-sm"
                  rows={2}
                  placeholder="Justification (required) — recorded in the audit trail"
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                />
                <Button onClick={doRequest} disabled={busy}>
                  {busy ? 'Requesting…' : 'Request override'}
                </Button>
              </div>
            )}

            {ov && (
              <div className="space-y-3">
                <div className="text-xs text-gray-600">
                  Requested by {ov.requested_by} — “{ov.justification}”
                </div>
                <div className="flex flex-wrap gap-2">
                  {requiredRoles.map((r) => (
                    <Badge key={r} tone={approvedRoles.has(r) ? 'success' : 'neutral'}>
                      {approvedRoles.has(r) ? '✓ ' : ''}{ROLE_LABELS[r] || r}
                    </Badge>
                  ))}
                  {approvedRoles.has('admin') && <Badge tone="brand">✓ Administrator</Badge>}
                </div>
                {ov.status === 'authorized' ? (
                  <p className="text-sm text-green-700">
                    Override authorized — disbursement may proceed (it will be flagged as
                    disbursed under override).
                  </p>
                ) : (
                  <Button onClick={doApprove} disabled={busy}>
                    {busy ? 'Approving…' : 'Approve override (your authority)'}
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
