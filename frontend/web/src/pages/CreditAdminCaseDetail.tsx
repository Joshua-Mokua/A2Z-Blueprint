// v10.522 Phase 4 Batch β6 — Credit Admin case detail page.
//
// Single-case view at /credit-admin/:caseId. Two action surfaces:
//   - Per-condition Fulfill (inline on each unfulfilled condition row,
//     when can_fulfill_condition is true)
//   - Disburse (bottom action panel, when can_disburse is true)
//
// Per-condition fulfillment is more interactive than β5's static
// docs list because each condition is its own state-changing target —
// users mark them one at a time as documents come in.
//
// Mutation flow:
//   1. User clicks "Fulfill" on an unfulfilled condition
//   2. Inline form expands under that row (officer name + notes)
//   3. Submit calls POST /api/credit-admin/cases/{id}/conditions/fulfill
//   4. On success: refetch → condition shows fulfilled state, form collapses,
//      maybe all_conditions_met flips True and Disburse panel becomes available

import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useCreditAdminCase } from '@/hooks/useCreditAdminCase';
import { useCreditAdminMutations } from '@/hooks/useCreditAdminMutations';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import { DisbursementGatePanel } from '@/components/DisbursementGatePanel';
import {
  FacilityClassificationPanel, CollateralPanel, ConditionsCpCsPanel,
  LegalReviewPanel, PerfectionPanel, InsurancePanel,
} from '@/components/SecuredLendingPanels';
import {
  caseStatusTone,
  caseStatusLabel,
  COMMON_DISBURSE_AUTHORITIES,
  type CreditAdminCondition,
} from '@/types/creditAdmin';


// ── Format helpers ──────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined | null): string {
  if (!s) return '—';
  return s.slice(0, 10);
}


// ── Page component ──────────────────────────────────────────────────────

export function CreditAdminCaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();

  const { caseRecord, permissions, loading, error, refetch } =
    useCreditAdminCase(caseId);
  const mutations = useCreditAdminMutations();

  // Which condition's fulfillment form is currently expanded? Keyed by
  // condition.type since types are unique within a case.
  const [activeFulfillType, setActiveFulfillType] = useState<string | null>(null);

  // Disburse panel state — ALL useState calls MUST be before any
  // conditional return below per Rules of Hooks. Even though these
  // are only used inside the DisbursePanel which itself is only
  // rendered when permissions.can_disburse, the hook calls themselves
  // must always happen in the same order on every render.
  const [disburseOpen,      setDisburseOpen]      = useState(false);
  const [disburseAuthority, setDisburseAuthority] = useState<string>(COMMON_DISBURSE_AUTHORITIES[0]);
  const [disburseComments,  setDisburseComments]  = useState<string>('');
  const [disburseError,     setDisburseError]     = useState<string | null>(null);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  // ── Loading ──
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
          <div className="max-w-5xl mx-auto px-6 py-5">
            <Skeleton className="h-7 w-72 bg-white/20" />
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </main>
      </div>
    );
  }

  // ── Error / not found ──
  if (error || !caseRecord || !permissions) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
          <div className="max-w-5xl mx-auto px-6 py-5">
            <h1 className="text-xl font-semibold">Case not found</h1>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-6">
          <Card>
            <Card.Body>
              <div className="text-sm text-red-800 mb-3">
                <div className="font-semibold">Could not load case</div>
                <div className="text-xs">{error || `No case with id ${caseId} found.`}</div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => navigate('/credit-admin')}>
                ← Back to cases
              </Button>
            </Card.Body>
          </Card>
        </main>
      </div>
    );
  }

  const conditions = caseRecord.conditions || [];
  const fulfilledCount = conditions.filter((c) => c.fulfilled).length;
  const requiredCount = conditions.filter((c) => c.required !== false).length;


  // ── Condition-fulfill submit ──
  const onFulfillSubmit = async (
    conditionType: string,
    officerName: string,
    notes: string,
  ) => {
    if (!caseId) return;
    if (!officerName.trim()) {
      toast({ tone: 'danger', message: 'Officer name is required.' });
      return;
    }
    const result = await mutations.fulfillCondition(caseId, {
      condition_type: conditionType,
      officer_name: officerName.trim(),
      notes: notes.trim() || undefined,
    });
    if (result.ok) {
      await refetch();
      setActiveFulfillType(null);
      toast({ tone: 'success', message: `Condition "${conditionType}" fulfilled.` });
    } else {
      toast({ tone: 'danger', message: result.error });
    }
  };


  // ── Disburse submit ──
  const onDisburseSubmit = async () => {
    if (!caseId) return;
    setDisburseError(null);
    if (!disburseAuthority.trim()) {
      setDisburseError('Authority is required.');
      return;
    }
    const result = await mutations.disburse(caseId, {
      authority: disburseAuthority.trim(),
      comments: disburseComments.trim() || undefined,
    });
    if (result.ok) {
      await refetch();
      setDisburseOpen(false);
      toast({ tone: 'success', message: 'Case cleared for disbursement.' });
    } else {
      setDisburseError(result.error);
      toast({ tone: 'danger', message: result.error });
    }
  };


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs text-white/70 mb-1 font-mono">{caseRecord.id}</div>
              <h1 className="text-xl font-semibold">{caseRecord.client_name}</h1>
              <div className="text-xs text-white/80 mt-1">
                {caseRecord.product || 'unknown product'} · {formatAmount(caseRecord.amount, currencySymbol)}
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Badge tone={caseStatusTone(caseRecord)} size="md">
                {caseStatusLabel(caseRecord)}
              </Badge>
              <span className="text-xs text-white/70">
                {fulfilledCount} / {conditions.length} conditions
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">

        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={() => navigate('/credit-admin')}>
            ← Back to cases
          </Button>
          <Badge tone="brand" size="sm">β6</Badge>
        </div>


        {/* Identity card */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Case identity</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Field label="Case ID" value={caseRecord.id} mono />
              <Field label="Source application">
                <span className="font-mono text-sm text-gray-900">
                  {caseRecord.application_id}{' '}
                  <button
                    onClick={() => navigate(`/lms/${encodeURIComponent(caseRecord.application_id)}`)}
                    className="text-xs text-brand-primary hover:underline ml-2"
                  >
                    view LMS →
                  </button>
                </span>
              </Field>
              <Field label="Client" value={caseRecord.client_name} />
              <Field label="Product" value={caseRecord.product} />
              <Field label="Amount" value={formatAmount(caseRecord.amount, currencySymbol)} mono />
              <Field label="Approval date" value={formatDate(caseRecord.approval_date)} />
              <Field label="RM" value={caseRecord.rm_name} />
              <Field label="Last updated" value={formatDate(caseRecord.last_updated)} />
            </div>
          </Card.Body>
        </Card>


        {/* Lifecycle gates card */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Disbursement gates</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <GateChip
                label="All conditions met"
                met={!!caseRecord.all_conditions_met}
              />
              <GateChip
                label="Cleared by manager"
                met={!!caseRecord.ready_for_disbursement}
              />
              <GateChip
                label="Funds disbursed"
                met={!!caseRecord.disbursed}
              />
            </div>
            {caseRecord.disbursed && caseRecord.disbursement_date && (
              <div className="mt-3 text-xs text-gray-500">
                Disbursed on {formatDate(caseRecord.disbursement_date)}.
              </div>
            )}
          </Card.Body>
        </Card>


        {/* Conditions card — the interactive heart of this page */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Conditions ({fulfilledCount} of {conditions.length} fulfilled)
            </h2>
            {requiredCount < conditions.length && (
              <span className="text-xs text-gray-500">
                {requiredCount} required, {conditions.length - requiredCount} optional
              </span>
            )}
          </Card.Header>
          <Card.Body className="p-0">
            {conditions.length === 0 ? (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                No conditions on this case.
              </div>
            ) : (
              <ul className="divide-y divide-gray-100">
                {conditions.map((cond) => (
                  <ConditionRow
                    key={cond.type}
                    condition={cond}
                    isActive={activeFulfillType === cond.type}
                    canFulfill={permissions.can_fulfill_condition}
                    onOpenFulfill={() => setActiveFulfillType(cond.type)}
                    onCloseFulfill={() => setActiveFulfillType(null)}
                    onSubmitFulfill={(officer, notes) =>
                      onFulfillSubmit(cond.type, officer, notes)
                    }
                    loading={mutations.loading}
                    defaultOfficerName={user?.full_name || ''}
                  />
                ))}
              </ul>
            )}
          </Card.Body>
        </Card>


        {/* Two-layer authorization status (v10.585 / B20) */}
        {(caseRecord.authorization_requested || caseRecord.authorized) && (
          <Card className="mt-6" stripe="primary">
            <Card.Body>
              <div className="text-sm text-gray-700 space-y-1">
                {caseRecord.authorization_requested && (
                  <div>
                    <span className="font-medium">Authorization requested</span>
                    {caseRecord.authorization_requested_by ? ` by ${caseRecord.authorization_requested_by}` : ''}
                  </div>
                )}
                {caseRecord.authorized
                  ? <div className="text-green-700"><span className="font-medium">Authorized</span>{caseRecord.authorized_by ? ` by ${caseRecord.authorized_by}` : ''}</div>
                  : caseRecord.authorization_requested
                    ? <div className="text-amber-700">Awaiting manager authorization.</div>
                    : null}
              </div>
            </Card.Body>
          </Card>
        )}

        {/* Layer 1: officer requests authorization */}
        {permissions.can_request_authorization && (
          <CaAuthPanel
            caseId={caseRecord.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="accent" title="Request disbursement authorization"
            desc="All conditions are met. Confirm the case and request manager authorization (Layer 1)."
            cta="Request authorization"
            run={(id, note) => mutations.requestAuthorization(id, { note })}
            okMsg="Authorization requested." />
        )}

        {/* Layer 2: manager authorizes */}
        {permissions.can_authorize && (
          <CaAuthPanel
            caseId={caseRecord.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="primary" title="Authorize disbursement"
            desc="A Layer-1 request is pending. Authorize this case for disbursement (Layer 2)."
            cta="Authorize"
            run={(id, note) => mutations.authorize(id, { note })}
            okMsg="Case authorized for disbursement." />
        )}

        {/* P4 secured-lending entry panels (credit-admin drives the workflow). */}
        <FacilityClassificationPanel caseRecord={caseRecord} onChange={refetch} />
        <ConditionsCpCsPanel caseRecord={caseRecord} onChange={refetch} />
        <CollateralPanel caseRecord={caseRecord} onChange={refetch} />
        <LegalReviewPanel caseRecord={caseRecord} onChange={refetch} />
        <PerfectionPanel caseRecord={caseRecord} onChange={refetch} />
        <InsurancePanel caseRecord={caseRecord} onChange={refetch} />

        {/* P4-6: secured-lending disbursement gate + controlled override.
            Renders only for secured facilities (component self-hides otherwise). */}
        <DisbursementGatePanel caseId={caseRecord.id} onChange={refetch} />

        {/* Disburse action panel (if can_disburse) */}
        {permissions.can_disburse && (
          <DisbursePanel
            open={disburseOpen}
            setOpen={setDisburseOpen}
            authority={disburseAuthority}
            setAuthority={setDisburseAuthority}
            comments={disburseComments}
            setComments={setDisburseComments}
            error={disburseError}
            setError={setDisburseError}
            loading={mutations.loading}
            onSubmit={onDisburseSubmit}
          />
        )}


        {/* If no actions, hint */}
        {!permissions.can_fulfill_condition && !permissions.can_disburse &&
         !permissions.can_request_authorization && !permissions.can_authorize && (
          <Card>
            <Card.Body>
              <div className="text-xs text-gray-500 italic">
                No actions available for this case from your role.
                {caseRecord.disbursed && ' Case has been disbursed.'}
                {!caseRecord.disbursed && !caseRecord.all_conditions_met && ' Waiting on conditions to be fulfilled.'}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}


// ── Field display helper ────────────────────────────────────────────────

interface FieldProps {
  label:      string;
  value?:     string | number | null;
  mono?:      boolean;
  children?:  React.ReactNode;
}

function Field({ label, value, mono, children }: FieldProps) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-sm text-gray-900 mt-0.5 ${mono ? 'font-mono' : ''}`}>
        {children !== undefined
          ? children
          : (value === null || value === undefined || value === '' ? '—' : String(value))}
      </div>
    </div>
  );
}


// ── Gate chip helper ────────────────────────────────────────────────────

function GateChip({ label, met }: { label: string; met: boolean }) {
  return (
    <div className={`px-3 py-2 rounded-md border ${
      met
        ? 'bg-green-50 border-green-200 text-green-900'
        : 'bg-gray-50 border-gray-200 text-gray-600'
    }`}>
      <div className="flex items-center gap-2">
        <span className={`text-base leading-none ${met ? 'text-green-600' : 'text-gray-300'}`}>
          {met ? '✓' : '○'}
        </span>
        <span className="text-sm font-medium">{label}</span>
      </div>
    </div>
  );
}


// ── ConditionRow component ──────────────────────────────────────────────

interface ConditionRowProps {
  condition:          CreditAdminCondition;
  isActive:           boolean;
  canFulfill:         boolean;
  onOpenFulfill:      () => void;
  onCloseFulfill:     () => void;
  onSubmitFulfill:    (officer: string, notes: string) => void;
  loading:            boolean;
  defaultOfficerName: string;
}

function ConditionRow({
  condition,
  isActive,
  canFulfill,
  onOpenFulfill,
  onCloseFulfill,
  onSubmitFulfill,
  loading,
  defaultOfficerName,
}: ConditionRowProps) {
  const [officer, setOfficer] = useState<string>(defaultOfficerName);
  const [notes,   setNotes]   = useState<string>('');

  return (
    <li className="px-6 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1">
          <span className={`text-lg leading-none mt-0.5 ${
            condition.fulfilled ? 'text-green-600' : 'text-gray-300'
          }`}>
            {condition.fulfilled ? '✓' : '○'}
          </span>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900">{condition.type}</span>
              {condition.required === false && (
                <Badge tone="neutral" size="sm">optional</Badge>
              )}
              {condition.required !== false && !condition.fulfilled && (
                <Badge tone="warning" size="sm">required</Badge>
              )}
            </div>
            {condition.fulfilled && (
              <div className="mt-1 text-xs text-gray-500">
                Fulfilled by <span className="font-medium text-gray-700">{condition.officer || 'unknown'}</span>
                {condition.date_met && <> on {condition.date_met.slice(0, 10)}</>}
                {condition.notes && (
                  <span className="block mt-0.5 italic text-gray-600">"{condition.notes}"</span>
                )}
              </div>
            )}
            {!condition.fulfilled && condition.date_set && (
              <div className="mt-1 text-xs text-gray-500">
                Set on {condition.date_set.slice(0, 10)}
              </div>
            )}
          </div>
        </div>

        {!condition.fulfilled && canFulfill && !isActive && (
          <Button variant="primary" size="sm" onClick={onOpenFulfill}>
            Fulfill
          </Button>
        )}
      </div>

      {/* Inline fulfill form */}
      {isActive && !condition.fulfilled && (
        <div className="mt-3 pl-7 pt-3 border-t border-gray-100">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-700">Officer name *</label>
              <input
                type="text"
                value={officer}
                onChange={(e) => setOfficer(e.target.value)}
                disabled={loading}
                placeholder="Who fulfilled this condition?"
                className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-700">Notes</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={loading}
                placeholder="Optional notes about fulfillment"
                className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => onSubmitFulfill(officer, notes)}
              disabled={loading}
            >
              {loading ? 'Submitting…' : 'Mark fulfilled'}
            </Button>
            <Button variant="ghost" size="sm" onClick={onCloseFulfill} disabled={loading}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}


// ── Disburse action panel ───────────────────────────────────────────────

interface DisbursePanelProps {
  open:          boolean;
  setOpen:       (v: boolean) => void;
  authority:     string;
  setAuthority:  (v: string) => void;
  comments:      string;
  setComments:   (v: string) => void;
  error:         string | null;
  setError:      (v: string | null) => void;
  loading:       boolean;
  onSubmit:      () => void;
}

function DisbursePanel({
  open, setOpen, authority, setAuthority, comments, setComments,
  error, setError, loading, onSubmit,
}: DisbursePanelProps) {
  if (!open) {
    return (
      <Card stripe="accent">
        <Card.Body>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Clear for disbursement</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                All conditions met. Clear this case so the finance system can disburse funds.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
              Clear for disbursement
            </Button>
          </div>
        </Card.Body>
      </Card>
    );
  }

  return (
    <Card stripe="accent">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Clear for disbursement</h3>
      </Card.Header>
      <Card.Body>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-gray-700">Clearing authority *</label>
            <input
              type="text"
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              disabled={loading}
              list="disburse-authority-options"
              className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
            />
            <datalist id="disburse-authority-options">
              {COMMON_DISBURSE_AUTHORITIES.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Comments</label>
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              disabled={loading}
              rows={2}
              className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
            />
          </div>
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
      </Card.Body>
      <Card.Footer>
        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={onSubmit} disabled={loading}>
            {loading ? 'Clearing…' : 'Confirm clearance'}
          </Button>
          <Button variant="ghost" onClick={() => { setOpen(false); setError(null); }} disabled={loading}>
            Cancel
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}


// ── Two-layer authorization panel (v10.585 / B20) ───────────────────────

import type { MutationResult } from '@/hooks/useCreditAdminMutations';
import type { CreditAdminMutationResponse } from '@/types/creditAdmin';

function CaAuthPanel({ caseId, mutations, toast, onDone, stripe, title, desc, cta, run, okMsg }: {
  caseId: string;
  mutations: ReturnType<typeof useCreditAdminMutations>;
  toast: ReturnType<typeof useToast>['toast'];
  onDone: () => Promise<unknown> | unknown;
  stripe: 'primary' | 'secondary' | 'accent';
  title: string;
  desc: string;
  cta: string;
  run: (id: string, note: string) => Promise<MutationResult<CreditAdminMutationResponse>>;
  okMsg: string;
}) {
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const onClick = async () => {
    setError(null);
    const res = await run(caseId, note.trim());
    if (res.ok) { await onDone(); toast({ tone: 'success', message: okMsg }); setNote(''); }
    else setError(res.error);
  };
  return (
    <Card className="mt-6" stripe={stripe}>
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">{title}</h3></Card.Header>
      <Card.Body>
        <p className="text-sm text-gray-600 mb-3">{desc}</p>
        <div>
          <label className="text-sm font-medium text-gray-700">Note (optional)</label>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={mutations.loading}
            className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-base text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </div>
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        <div className="mt-3">
          <Button variant="primary" onClick={onClick} disabled={mutations.loading}>
            {mutations.loading ? 'Working…' : cta}
          </Button>
        </div>
      </Card.Body>
    </Card>
  );
}
