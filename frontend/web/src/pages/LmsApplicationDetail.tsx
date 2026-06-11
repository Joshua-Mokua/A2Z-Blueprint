// v10.520 Phase 4 Batch β5 — LMS application detail page.
//
// Single-application view at /lms/:appId. Shows full application info
// plus per-action inline panels gated by the α8 permissions object:
//   - Assign Analyst panel       (when can_assign)
//   - Edit Application panel     (when can_update)
//   - Record Decision panel      (when can_record_decision)
//
// Pattern mirrors PipelineDealDetail.tsx (β2): inline panels rather than
// modal dialogs, page-local fetch (not Provider), refetch after each
// successful mutation so the permissions object reflects new state.
//
// Routing: on success of any mutation, stays on the page and refetches.
// The panel that was used closes itself because its permission flag
// flipped (e.g. after assign, can_assign becomes false because status
// is now 'assigned').

import { useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useLmsApplication } from '@/hooks/useLmsApplication';
import { useLmsMutations } from '@/hooks/useLmsMutations';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import {
  statusTone,
  DECISION_VERDICTS,
  COMMON_AUTHORITIES,
  type DecisionVerdict,
  type LoanApplication,
  type LoanApplicationPermissions,
} from '@/types/lms';


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

export function LmsApplicationDetail() {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();

  const { application, permissions, loading, error, refetch } =
    useLmsApplication(appId);
  const mutations = useLmsMutations();

  // Panel toggles
  const [assignOpen,   setAssignOpen]   = useState(false);
  const [updateOpen,   setUpdateOpen]   = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  // ── Loading state ────────────────────────────────────────────────
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
          <Skeleton className="h-48 w-full" />
        </main>
      </div>
    );
  }

  // ── Error / not-found ─────────────────────────────────────────────
  if (error || !application || !permissions) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
          <div className="max-w-5xl mx-auto px-6 py-5">
            <h1 className="text-xl font-semibold">Application not found</h1>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-6">
          <Card stripe="danger">
            <Card.Body>
              <div className="text-sm text-red-800 mb-3">
                <div className="font-semibold">Could not load application</div>
                <div className="text-xs">{error || `No application with id ${appId} found.`}</div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => navigate('/lms')}>
                ← Back to applications
              </Button>
            </Card.Body>
          </Card>
        </main>
      </div>
    );
  }


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs text-white/70 mb-1 font-mono">{application.id}</div>
              <h1 className="text-xl font-semibold">{application.client_name}</h1>
              <div className="text-xs text-white/80 mt-1">
                {application.product || 'unknown product'} · {formatAmount(application.amount, currencySymbol)}
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Badge tone={statusTone(application.status)} size="md">
                {application.status}
              </Badge>
              {application.swim_lane && (
                <span className="text-xs text-white/70">{application.swim_lane}</span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">

        {/* Back to list */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={() => navigate('/lms')}>
            ← Back to applications
          </Button>
          <Badge tone="brand" size="sm">β5</Badge>
        </div>


        {/* ─────────── Application details card ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Application</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Field label="Client name" value={application.client_name} />
              <Field label="Client CIF" value={application.client_cif} mono />
              <Field label="Product" value={application.product} />
              <Field label="Amount" value={formatAmount(application.amount, currencySymbol)} mono />
              <Field label="Currency" value={application.currency || 'KES'} />
              <Field label="Application date" value={formatDate(application.application_date)} />
              <Field label="Last updated" value={formatDate(application.last_updated)} />
              <Field label="Pipeline deal" value={application.pipeline_deal_id} mono />
            </div>
          </Card.Body>
        </Card>


        {/* ─────────── Ownership card ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Ownership</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Field label="RM code" value={application.rm_code} mono />
              <Field label="RM name" value={application.rm_name} />
              <Field label="RM unit" value={application.rm_unit} />
              <Field
                label="Analyst"
                value={
                  application.analyst?.name
                    ? `${application.analyst.name} (${application.analyst.code})`
                    : 'unassigned'
                }
              />
            </div>
          </Card.Body>
        </Card>


        {/* ─────────── Decision card (only if recorded) ─────────── */}
        {application.decision?.verdict && (
          <Card stripe={
            application.decision.verdict === 'approved' ? 'success' :
            application.decision.verdict === 'declined' ? 'danger' :
            'warning'
          }>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                Decision: {application.decision.verdict}
              </h2>
            </Card.Header>
            <Card.Body>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <Field label="Authority" value={application.decision.authority} />
                <Field label="Date" value={formatDate(application.decision.date)} />
                {application.decision.reason && (
                  <Field label="Reason" value={application.decision.reason} fullWidth />
                )}
                {application.decision.comments && (
                  <Field label="Comments" value={application.decision.comments} fullWidth />
                )}
                {application.decision.conditions && application.decision.conditions.length > 0 && (
                  <div className="col-span-2">
                    <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Conditions
                    </div>
                    <ul className="text-sm text-gray-700 list-disc pl-5 space-y-1">
                      {application.decision.conditions.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ─────────── Documentation card ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Documentation</h2>
            {application.completeness_score !== undefined && (
              <span className="text-xs text-gray-500">
                {application.completeness_score}% complete
              </span>
            )}
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  Required ({application.docs_required?.length || 0})
                </div>
                {application.docs_required && application.docs_required.length > 0 ? (
                  <ul className="text-sm text-gray-700 space-y-1">
                    {application.docs_required.map((d, i) => {
                      const submitted = application.docs_submitted?.includes(d) ?? false;
                      return (
                        <li key={i} className={`flex items-center gap-2 ${submitted ? '' : 'text-gray-500'}`}>
                          <span className={submitted ? 'text-green-600' : 'text-gray-300'}>
                            {submitted ? '✓' : '○'}
                          </span>
                          <span>{d}</span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <div className="text-xs text-gray-400">No documents required</div>
                )}
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                  Underwriting flags
                </div>
                <ul className="text-sm text-gray-700 space-y-1">
                  <li>Repeat borrower: <span className="font-medium">{application.is_repeat_borrower ? 'yes' : 'no'}</span></li>
                  <li>Clean repayment history: <span className="font-medium">{application.clean_repayment_history ? 'yes' : 'no'}</span></li>
                  <li>Compliance flag: <span className="font-medium">{application.compliance_flag ? `yes (${application.compliance_type || 'unspecified'})` : 'no'}</span></li>
                </ul>
              </div>
            </div>
            {application.appraisal_notes && (
              <div className="mt-4 pt-4 border-t border-gray-100">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                  Appraisal notes
                </div>
                <div className="text-sm text-gray-700 whitespace-pre-line">
                  {application.appraisal_notes}
                </div>
              </div>
            )}
          </Card.Body>
        </Card>


        {/* ─────────── ACTION: Assign Analyst (if can_assign) ─────────── */}
        {permissions.can_assign && (
          <ActionPanelAssign
            appId={application.id}
            open={assignOpen}
            setOpen={setAssignOpen}
            mutations={mutations}
            onSuccess={async () => {
              await refetch();
              setAssignOpen(false);
              toast({ tone: 'success', message: 'Analyst assigned.' });
            }}
            toast={toast}
          />
        )}


        {/* ─────────── ACTION: Edit Application (if can_update) ─────────── */}
        {permissions.can_update && (
          <ActionPanelUpdate
            application={application}
            open={updateOpen}
            setOpen={setUpdateOpen}
            mutations={mutations}
            onSuccess={async () => {
              await refetch();
              setUpdateOpen(false);
              toast({ tone: 'success', message: 'Application updated.' });
            }}
            toast={toast}
          />
        )}


        {/* ─────────── ACTION: Record Decision (if can_record_decision) ─────────── */}
        {permissions.can_record_decision && (
          <ActionPanelDecision
            appId={application.id}
            open={decisionOpen}
            setOpen={setDecisionOpen}
            mutations={mutations}
            onSuccess={async (verdict) => {
              await refetch();
              setDecisionOpen(false);
              toast({
                tone: verdict === 'approved' ? 'success' : verdict === 'declined' ? 'danger' : 'warning',
                message: `Decision recorded: ${verdict}`,
              });
            }}
            toast={toast}
          />
        )}


        {/* If no actions available, show why */}
        {!permissions.can_assign && !permissions.can_update && !permissions.can_record_decision && (
          <Card>
            <Card.Body>
              <div className="text-xs text-gray-500 italic">
                No actions available for this application from your role at its current status (
                <span className="font-mono">{application.status}</span>).
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
  value:     string | number | null | undefined;
  mono?:     boolean;
  fullWidth?: boolean;
}

function Field({ label, value, mono, fullWidth }: FieldProps) {
  const display = value === null || value === undefined || value === '' ? '—' : String(value);
  return (
    <div className={fullWidth ? 'col-span-2' : ''}>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-sm text-gray-900 mt-0.5 ${mono ? 'font-mono' : ''}`}>{display}</div>
    </div>
  );
}


// ── ACTION PANEL: Assign Analyst ────────────────────────────────────────

interface ActionPanelProps {
  appId:       string;
  open:        boolean;
  setOpen:     (v: boolean) => void;
  mutations:   ReturnType<typeof useLmsMutations>;
  onSuccess:   (...args: unknown[]) => void | Promise<void>;
  toast:       ReturnType<typeof useToast>['toast'];
}

function ActionPanelAssign({ appId, open, setOpen, mutations, onSuccess, toast }: ActionPanelProps) {
  const [analystCode, setAnalystCode] = useState('');
  const [analystName, setAnalystName] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Card stripe="brand">
        <Card.Body>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Assign credit analyst</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Assign a credit analyst to review this submitted application.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
              Assign analyst
            </Button>
          </div>
        </Card.Body>
      </Card>
    );
  }

  const onSubmit = async () => {
    setError(null);
    if (!analystCode.trim()) { setError('Analyst code is required.'); return; }
    if (!analystName.trim()) { setError('Analyst name is required.'); return; }

    const result = await mutations.assign(appId, {
      analyst_code: analystCode.trim(),
      analyst_name: analystName.trim(),
    });
    if (result.ok) {
      await onSuccess();
    } else {
      setError(result.error);
      toast({ tone: 'danger', message: result.error });
    }
  };

  return (
    <Card stripe="brand">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Assign credit analyst</h3>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Analyst staff code *"
            placeholder="e.g. 300080"
            value={analystCode}
            onChange={(e) => setAnalystCode(e.target.value)}
            disabled={mutations.loading}
          />
          <Input
            label="Analyst name *"
            placeholder="e.g. Zainab Okello"
            value={analystName}
            onChange={(e) => setAnalystName(e.target.value)}
            disabled={mutations.loading}
          />
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
      </Card.Body>
      <Card.Footer>
        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={onSubmit} disabled={mutations.loading}>
            {mutations.loading ? 'Assigning…' : 'Confirm assignment'}
          </Button>
          <Button variant="ghost" onClick={() => { setOpen(false); setError(null); }} disabled={mutations.loading}>
            Cancel
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}


// ── ACTION PANEL: Update Application ────────────────────────────────────

function ActionPanelUpdate({
  application, open, setOpen, mutations, onSuccess, toast,
}: ActionPanelProps & { application: LoanApplication }) {
  const [completenessScore, setCompletenessScore] = useState<string>(
    application.completeness_score !== undefined ? String(application.completeness_score) : ''
  );
  const [appraisalNotes, setAppraisalNotes] = useState<string>(application.appraisal_notes || '');
  const [complianceFlag, setComplianceFlag] = useState<boolean>(application.compliance_flag || false);
  const [complianceType, setComplianceType] = useState<string>(application.compliance_type || '');
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Card stripe="brand">
        <Card.Body>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Update application</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Edit completeness score, compliance flags, appraisal notes.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
              Update fields
            </Button>
          </div>
        </Card.Body>
      </Card>
    );
  }

  const onSubmit = async () => {
    setError(null);
    const body: Record<string, unknown> = {};

    if (completenessScore.trim()) {
      const n = Number(completenessScore);
      if (!Number.isFinite(n) || n < 0 || n > 100) {
        setError('Completeness score must be a number 0–100.');
        return;
      }
      body.completeness_score = n;
    }
    if (appraisalNotes !== (application.appraisal_notes || '')) {
      body.appraisal_notes = appraisalNotes;
    }
    if (complianceFlag !== (application.compliance_flag || false)) {
      body.compliance_flag = complianceFlag;
    }
    if (complianceType !== (application.compliance_type || '')) {
      body.compliance_type = complianceType || undefined;
    }

    if (Object.keys(body).length === 0) {
      setError('No changes to save.');
      return;
    }

    const result = await mutations.update(application.id, body);
    if (result.ok) {
      await onSuccess();
    } else {
      setError(result.error);
      toast({ tone: 'danger', message: result.error });
    }
  };

  return (
    <Card stripe="brand">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Update application fields</h3>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Completeness score (0-100)"
            type="number"
            value={completenessScore}
            onChange={(e) => setCompletenessScore(e.target.value)}
            disabled={mutations.loading}
            placeholder="e.g. 75"
          />
          <div>
            <label className="text-sm font-medium text-gray-700">Compliance flag</label>
            <div className="mt-1 flex items-center gap-3 h-10">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={complianceFlag}
                  onChange={(e) => setComplianceFlag(e.target.checked)}
                  disabled={mutations.loading}
                />
                Flagged
              </label>
              {complianceFlag && (
                <input
                  type="text"
                  value={complianceType}
                  onChange={(e) => setComplianceType(e.target.value)}
                  disabled={mutations.loading}
                  placeholder="e.g. AML review"
                  className="flex-1 h-8 px-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary"
                />
              )}
            </div>
          </div>
        </div>
        <div className="mt-3">
          <label className="text-sm font-medium text-gray-700">Appraisal notes</label>
          <textarea
            value={appraisalNotes}
            onChange={(e) => setAppraisalNotes(e.target.value)}
            disabled={mutations.loading}
            rows={3}
            className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
          />
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
      </Card.Body>
      <Card.Footer>
        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={onSubmit} disabled={mutations.loading}>
            {mutations.loading ? 'Saving…' : 'Save changes'}
          </Button>
          <Button variant="ghost" onClick={() => { setOpen(false); setError(null); }} disabled={mutations.loading}>
            Cancel
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}


// ── ACTION PANEL: Record Decision ───────────────────────────────────────

function ActionPanelDecision({ appId, open, setOpen, mutations, onSuccess, toast }: ActionPanelProps) {
  const [verdict, setVerdict] = useState<DecisionVerdict>('approved');
  const [authority, setAuthority] = useState<string>(COMMON_AUTHORITIES[0]);
  const [reason, setReason]       = useState<string>('');
  const [conditions, setConditions] = useState<string>('');
  const [comments, setComments]   = useState<string>('');
  const [error, setError]         = useState<string | null>(null);

  if (!open) {
    return (
      <Card stripe="brand">
        <Card.Body>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Record decision</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Approve, decline, or return this application.
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
              Record decision
            </Button>
          </div>
        </Card.Body>
      </Card>
    );
  }

  const onSubmit = async () => {
    setError(null);
    if (!authority.trim()) { setError('Authority is required.'); return; }

    const conditionsList = conditions
      .split('\n')
      .map((c) => c.trim())
      .filter((c) => c.length > 0);

    const result = await mutations.recordDecision(appId, {
      verdict,
      authority: authority.trim(),
      reason: reason.trim() || undefined,
      conditions: conditionsList.length > 0 ? conditionsList : undefined,
      comments: comments.trim() || undefined,
    });

    if (result.ok) {
      await (onSuccess as (verdict: DecisionVerdict) => Promise<void>)(verdict);
    } else {
      setError(result.error);
      toast({ tone: 'danger', message: result.error });
    }
  };

  return (
    <Card stripe="brand">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Record decision</h3>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-700">Verdict *</label>
            <select
              value={verdict}
              onChange={(e) => setVerdict(e.target.value as DecisionVerdict)}
              disabled={mutations.loading}
              className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
            >
              {DECISION_VERDICTS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Authority *</label>
            <input
              type="text"
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              disabled={mutations.loading}
              list="authority-options"
              className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
            />
            <datalist id="authority-options">
              {COMMON_AUTHORITIES.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>
        </div>
        <div className="mt-3">
          <label className="text-sm font-medium text-gray-700">
            Reason {verdict !== 'approved' && <span className="text-gray-500">(recommended for {verdict})</span>}
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={mutations.loading}
            className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </div>
        {verdict === 'approved' && (
          <div className="mt-3">
            <label className="text-sm font-medium text-gray-700">Conditions (one per line)</label>
            <textarea
              value={conditions}
              onChange={(e) => setConditions(e.target.value)}
              disabled={mutations.loading}
              rows={3}
              placeholder="Board resolution&#10;Debenture&#10;Insurance certificate"
              className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
            />
            <p className="text-xs text-gray-500 mt-1">
              For conditional approvals. Each line becomes one condition on the credit-admin case.
            </p>
          </div>
        )}
        <div className="mt-3">
          <label className="text-sm font-medium text-gray-700">Comments</label>
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            disabled={mutations.loading}
            rows={2}
            className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
          />
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
      </Card.Body>
      <Card.Footer>
        <div className="flex items-center gap-2">
          <Button
            variant={verdict === 'declined' ? 'danger' : verdict === 'returned' ? 'secondary' : 'primary'}
            onClick={onSubmit}
            disabled={mutations.loading}
          >
            {mutations.loading ? 'Recording…' : `Confirm ${verdict}`}
          </Button>
          <Button variant="ghost" onClick={() => { setOpen(false); setError(null); }} disabled={mutations.loading}>
            Cancel
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}
