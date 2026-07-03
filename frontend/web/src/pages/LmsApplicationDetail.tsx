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

import { useState, useEffect } from 'react';
import { AffordabilityAppraisal } from '@/components/AffordabilityAppraisal';
import { getApplicationWorkbench, refreshWorkbench, addWorkbenchNote, type WorkbenchView } from '@/lib/api';
import { useNavigate, useParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useLmsApplication } from '@/hooks/useLmsApplication';
import { useLmsMutations } from '@/hooks/useLmsMutations';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  listLmsAttachments, addLmsAttachment, recordLmsBcc,
  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, setCommitteeReadiness, recordCommitteePreRead, fetchCommitteePreReads, type CommitteePreReadsResponse, type LmsCommitteeRecordsResponse, type AssignableAnalyst,
  type LmsAttachment, type CrView, type CrField, type CommitteeMember, type CommitteeTier,
} from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import { Timeline } from '@/components/Timeline';
import {
  statusTone,
  DECISION_VERDICTS,
  COMMON_AUTHORITIES,
  type DecisionVerdict,
  type LoanApplication,
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
  const { toast } = useToast();
  const { user } = useRole();

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
          <div className="max-w-6xl mx-auto px-6 py-5">
            <Skeleton className="h-7 w-72 bg-white/20" />
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-6 py-6 space-y-4">
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
          <Card >
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
              {application.sla && (
                <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
                  application.sla.state === 'breached' ? 'bg-red-500/90 text-white'
                  : application.sla.state === 'due_soon' ? 'bg-amber-400/90 text-amber-950'
                  : 'bg-green-500/90 text-white'}`}>
                  {application.sla.state === 'breached'
                    ? `SLA breached — ${application.sla.overdue_business_days}d over promise`
                    : application.sla.state === 'due_soon'
                    ? `SLA due soon — ${application.sla.remaining_business_days}d left`
                    : `SLA on track — ${application.sla.remaining_business_days}d left`}
                </span>
              )}
              {application.sla?.stage && (
                <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
                  application.sla.stage.state === 'breached' ? 'bg-red-500/90 text-white'
                  : application.sla.stage.state === 'due_soon' ? 'bg-amber-400/90 text-amber-950'
                  : 'bg-green-500/90 text-white'}`}>
                  {application.sla.stage.state === 'breached'
                    ? `My stage — ${application.sla.stage.overdue_business_days}d over`
                    : `My stage — ${application.sla.stage.remaining_business_days}d left of ${application.sla.stage.target_days}`}
                </span>
              )}
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

        {/* customer-summary-strip: key facts pinned at the top of the content */}
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-gray-400">CIF</span>
              <span className="font-mono font-medium text-gray-900">{application.client_cif || '—'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-gray-400">Product</span>
              <span className="text-gray-900">{application.product || '—'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-gray-400">Amount</span>
              <span className="font-medium text-gray-900">{formatAmount(application.amount, currencySymbol)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-gray-400">RM</span>
              <span className="text-gray-900">{application.rm_name || application.rm_code || '—'}</span>
            </div>
            {application.analyst?.name && (
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase tracking-wide text-gray-400">Analyst</span>
                <span className="text-gray-900">{application.analyst.name}</span>
              </div>
            )}
            <div className="ml-auto">
              <Badge tone={statusTone(application.status)} size="sm">{application.status}</Badge>
            </div>
          </div>
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
          <Card stripe="accent">
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

        {/* ─────────── Attachments & Branch Credit Committee ─────────── */}
        <AttachmentsBccCard appId={application.id} canEdit={!!permissions.can_view} toast={toast} />

        {/* ─────────── Credit Report (CR) ─────────── */}
        <CreditReportCard appId={application.id} canEdit={!!permissions.can_view} toast={toast} />
        <BranchCommitteeDecisionsCard appId={application.id} />
        {application.status === 'referred_to_committee' && (
          <CommitteePreReadPanel appId={application.id} toast={toast} />
        )}


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

        {/* C2: assignment purpose banner + correctness action set */}
        {application.assignment_purpose && (
          <div className={`mt-4 rounded-md px-4 py-2 text-sm ${
            application.assignment_purpose === 'correctness'
              ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
            {application.assignment_purpose === 'correctness'
              ? 'Assigned for correctness check — confirm the case is well-packaged (CR complete, docs attached) and mark it ready for committee, or return it for rework.'
              : 'Assigned for decisioning — analyse the case and record the credit decision.'}
          </div>
        )}
        {application.committee_readiness && (
          <div className={`mt-2 rounded-md px-4 py-2 text-xs ${
            application.committee_readiness.state === 'ready_for_committee'
              ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {application.committee_readiness.state === 'ready_for_committee'
              ? `Ready for committee — checked by ${application.committee_readiness.by_name}`
              : `Returned for rework — by ${application.committee_readiness.by_name}`}
            {application.committee_readiness.opinion
              && <div className="mt-1 italic">Opinion: {application.committee_readiness.opinion}</div>}
          </div>
        )}
        {application.assignment_purpose === 'correctness'
          && String(application.analyst?.code ?? '') === String(user?.staff_code ?? '')
          && (
          <CorrectnessPanel appId={application.id} onDone={refetch} toast={toast} />
        )}

        <CreditWorkbenchPanel appId={application.id} toast={toast} />

        <AffordabilityAppraisal defaultCif={application.client_cif} appId={application.id} />


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


        {/* ─────────── Credit workflow actions (v10.587) ─────────── */}
        {permissions.can_request_info && (
          <WfRequestInfo appId={application.id} mutations={mutations} toast={toast} onDone={refetch} />
        )}
        {permissions.can_escalate && (
          <WfSimple appId={application.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="warning" title="Escalate / seek guidance"
            desc="If you cannot decide this case alone, escalate it to your line manager for input. Give a brief reason."
            cta="Escalate to line manager"
            run={(id, note) => mutations.escalate(id, { reason: note })}
            okMsg="Escalated to your line manager." requireNote />
        )}
        {application.escalation?.escalated && !application.escalation?.resolved && (permissions.can_record_decision) && (
          <WfSimple appId={application.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="primary" title="Add your view (line manager)"
            desc={`Escalated by ${application.escalation?.by || 'the analyst'}: ${application.escalation?.reason || ''}`}
            cta="Record manager view"
            run={(id, note) => mutations.managerView(id, { view: note })}
            okMsg="Your view was recorded." requireNote />
        )}
        {permissions.can_provide_info && (
          <WfSimple appId={application.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="accent" title="Provide requested information"
            desc={application.info_request?.note || 'The analyst requested additional documentation.'}
            cta="Mark information provided"
            run={(id, note) => mutations.provideInfo(id, { note })} okMsg="Information provided." />
        )}
        {permissions.can_sign_offer && (
          <WfSignOffer appId={application.id} mutations={mutations} toast={toast} onDone={refetch} />
        )}
        {permissions.can_validate_offer && (
          <WfValidateOffer appId={application.id} mutations={mutations} toast={toast} onDone={refetch} />
        )}
        {permissions.can_confirm_to_credit_admin && (
          <WfSimple appId={application.id} mutations={mutations} toast={toast} onDone={refetch}
            stripe="primary" title="Confirm to Credit Admin"
            desc="Confirm the signed, validated offer to Credit Admin to open the disbursement case."
            cta="Confirm to Credit Admin"
            run={(id, note) => mutations.confirmToCreditAdmin(id, { note })} okMsg="Confirmed to Credit Admin." />
        )}
        {permissions.can_refer_committee && (
          <WfReferCommittee appId={application.id} mutations={mutations} toast={toast} onDone={refetch} />
        )}
        {(permissions.can_vote_committee || permissions.can_resolve_committee) && (
          <WfCommittee application={application} mutations={mutations} toast={toast} onDone={refetch}
            canVote={!!permissions.can_vote_committee} canResolve={!!permissions.can_resolve_committee} />
        )}

        {/* ─────────── Workflow timeline ─────────── */}
        <Card className="mt-6">
          <Card.Header>
            <h3 className="text-sm font-semibold text-gray-900">Workflow timeline</h3>
          </Card.Header>
          <Card.Body>
            <Timeline events={application.history} emptyHint="No workflow activity yet." />
          </Card.Body>
        </Card>

        {/* If no actions available, show why */}
        {!permissions.can_assign && !permissions.can_update && !permissions.can_record_decision &&
         !permissions.can_request_info && !permissions.can_provide_info && !permissions.can_sign_offer &&
         !permissions.can_validate_offer && !permissions.can_confirm_to_credit_admin &&
         !permissions.can_refer_committee && !permissions.can_vote_committee && !permissions.can_resolve_committee && (
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
  const [analysts, setAnalysts] = useState<AssignableAnalyst[]>([]);
  useEffect(() => {
    fetchMyAnalysts().then((r) => setAnalysts(r.analysts)).catch(() => setAnalysts([]));
  }, []);

  if (!open) {
    return (
      <Card stripe="accent">
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
    <Card stripe="accent">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Assign credit analyst</h3>
      </Card.Header>
      <Card.Body>
        {analysts.length > 0 ? (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Credit analyst *</label>
            <select
              className="w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              value={analystCode}
              disabled={mutations.loading}
              onChange={(e) => {
                const a = analysts.find((x) => x.staff_code === e.target.value);
                setAnalystCode(a?.staff_code ?? '');
                setAnalystName(a?.name ?? '');
              }}
            >
              <option value="">— select an analyst —</option>
              {analysts.map((a) => (
                <option key={a.staff_code} value={a.staff_code}>
                  {a.name} ({a.staff_code}){a.unit ? ` — ${a.unit}` : ''}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-400">{analysts.length} analyst(s) in your team.</p>
          </div>
        ) : (
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
        )}
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
//
// Has its own props interface (not extending ActionPanelProps) because
// Update uses application.id internally rather than receiving appId as
// a separate prop — the form needs the application object anyway to
// pre-fill fields.

interface ActionPanelUpdateProps {
  application:   LoanApplication;
  open:          boolean;
  setOpen:       (v: boolean) => void;
  mutations:     ReturnType<typeof useLmsMutations>;
  onSuccess:     () => void | Promise<void>;
  toast:         ReturnType<typeof useToast>['toast'];
}

function ActionPanelUpdate({
  application, open, setOpen, mutations, onSuccess, toast,
}: ActionPanelUpdateProps) {
  const [completenessScore, setCompletenessScore] = useState<string>(
    application.completeness_score !== undefined ? String(application.completeness_score) : ''
  );
  const [appraisalNotes, setAppraisalNotes] = useState<string>(application.appraisal_notes || '');
  const [complianceFlag, setComplianceFlag] = useState<boolean>(application.compliance_flag || false);
  const [complianceType, setComplianceType] = useState<string>(application.compliance_type || '');
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Card stripe="accent">
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
    <Card stripe="accent">
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
      <Card stripe="accent">
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
    <Card stripe="accent">
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


// ── Credit workflow panels (v10.587) ────────────────────────────────────

import type { MutationResult } from '@/hooks/useLmsMutations';
import type { LoanAppMutationResponse } from '@/types/lms';

type WfMutations = ReturnType<typeof useLmsMutations>;
type WfToast = ReturnType<typeof useToast>['toast'];
type WfRun = (id: string, note: string) => Promise<MutationResult<LoanAppMutationResponse>>;

interface WfSimpleProps {
  appId: string;
  mutations: WfMutations;
  toast: WfToast;
  onDone: () => Promise<unknown> | unknown;
  stripe: 'primary' | 'secondary' | 'accent' | 'brand' | 'warning';
  title: string;
  desc: string;
  cta: string;
  run: WfRun;
  okMsg: string;
  requireNote?: boolean;
}

function WfSimple({ appId, toast, onDone, stripe, title, desc, cta, run, okMsg, mutations, requireNote }: WfSimpleProps) {
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const onClick = async () => {
    setError(null);
    if (requireNote && note.trim().length < 3) {
      setError('Please enter a reason (at least a few characters).');
      return;
    }
    const res = await run(appId, note.trim());
    if (res.ok) {
      await onDone();
      toast({ tone: 'success', message: okMsg });
      setNote('');
    } else {
      setError(res.error);
    }
  };
  const cardStripe = stripe === 'brand' ? 'primary' : stripe === 'warning' ? 'accent' : stripe;
  return (
    <Card className="mt-6" stripe={cardStripe}>
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">{title}</h3></Card.Header>
      <Card.Body>
        <p className="text-sm text-gray-600 mb-3">{desc}</p>
        <Input label="Note (optional)" value={note}
               onChange={(e) => setNote(e.target.value)} disabled={mutations.loading} />
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

function WfRequestInfo({ appId, mutations, toast, onDone }: {
  appId: string; mutations: WfMutations; toast: WfToast; onDone: () => Promise<unknown> | unknown;
}) {
  const [docs, setDocs] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const onClick = async () => {
    setError(null);
    const documents = docs.split(',').map((d) => d.trim()).filter(Boolean);
    const res = await mutations.requestInfo(appId, { documents, note: note.trim() });
    if (res.ok) { await onDone(); toast({ tone: 'success', message: 'Information requested.' }); setDocs(''); setNote(''); }
    else setError(res.error);
  };
  return (
    <Card className="mt-6" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Request more information</h3></Card.Header>
      <Card.Body>
        <p className="text-sm text-gray-600 mb-3">Park the case and ask the deal owner for additional documents (pre-decision).</p>
        <Input label="Documents (comma-separated)" value={docs}
               onChange={(e) => setDocs(e.target.value)} disabled={mutations.loading}
               placeholder="Audited accounts, CRB report" />
        <div className="mt-2">
          <Input label="Note (optional)" value={note}
                 onChange={(e) => setNote(e.target.value)} disabled={mutations.loading} />
        </div>
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        <div className="mt-3">
          <Button variant="primary" onClick={onClick} disabled={mutations.loading}>
            {mutations.loading ? 'Working…' : 'Request information'}
          </Button>
        </div>
      </Card.Body>
    </Card>
  );
}

function WfSignOffer({ appId, mutations, toast, onDone }: {
  appId: string; mutations: WfMutations; toast: WfToast; onDone: () => Promise<unknown> | unknown;
}) {
  const [filename, setFilename] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const onClick = async () => {
    setError(null);
    const res = await mutations.signOffer(appId, {
      attachment_filename: filename.trim() || undefined, note: note.trim(),
    });
    if (res.ok) { await onDone(); toast({ tone: 'success', message: 'Offer signed.' }); }
    else setError(res.error);
  };
  return (
    <Card className="mt-6" stripe="primary">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Sign letter of offer</h3></Card.Header>
      <Card.Body>
        <p className="text-sm text-gray-600 mb-3">Mark the letter of offer signed by the customer and attach the signed copy.</p>
        <Input label="Signed copy filename" value={filename}
               onChange={(e) => setFilename(e.target.value)} disabled={mutations.loading}
               placeholder="signed_offer_ECO123.pdf" />
        <div className="mt-2">
          <Input label="Note (optional)" value={note}
                 onChange={(e) => setNote(e.target.value)} disabled={mutations.loading} />
        </div>
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        <div className="mt-3">
          <Button variant="primary" onClick={onClick} disabled={mutations.loading}>
            {mutations.loading ? 'Working…' : 'Mark signed + attach'}
          </Button>
        </div>
      </Card.Body>
    </Card>
  );
}

function WfValidateOffer({ appId, mutations, toast, onDone }: {
  appId: string; mutations: WfMutations; toast: WfToast; onDone: () => Promise<unknown> | unknown;
}) {
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const act = async (approve: boolean) => {
    setError(null);
    const res = await mutations.validateOffer(appId, { approve, note: note.trim() });
    if (res.ok) { await onDone(); toast({ tone: approve ? 'success' : 'warning', message: approve ? 'Offer validated.' : 'Sent back for re-handling.' }); }
    else setError(res.error);
  };
  return (
    <Card className="mt-6" stripe="secondary">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Validate signed offer</h3></Card.Header>
      <Card.Body>
        <p className="text-sm text-gray-600 mb-3">Line-manager checks &amp; balances on the signed offer before it proceeds.</p>
        <Input label="Note (optional)" value={note}
               onChange={(e) => setNote(e.target.value)} disabled={mutations.loading} />
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        <div className="mt-3 flex gap-2">
          <Button variant="primary" onClick={() => act(true)} disabled={mutations.loading}>Validate</Button>
          <Button variant="ghost" onClick={() => act(false)} disabled={mutations.loading}>Send back</Button>
        </div>
      </Card.Body>
    </Card>
  );
}

function WfReferCommittee({ appId, mutations, toast, onDone }: {
  appId: string; mutations: WfMutations; toast: WfToast; onDone: () => Promise<unknown> | unknown;
}) {
  const [tiers, setTiers] = useState<CommitteeTier[]>([]);
  const [entryTier, setEntryTier] = useState<number | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [suggested, setSuggested] = useState<{ tier: number | null; name: string | null; amount: number; finalName?: string | null; mustClimb?: boolean } | null>(null);

  useEffect(() => {
    let live = true;
    getCommitteeTiers().then((r) => { if (live) setTiers(r.tiers || []); }).catch(() => {});
    fetchCommitteeRouting(appId).then((r) => {
      if (!live) return;
      setSuggested({ tier: r.entry_tier ?? r.suggested_tier, name: r.entry_name ?? r.suggested_name, amount: r.amount, finalName: r.final_name, mustClimb: r.must_climb });
      const preselect = r.entry_tier ?? r.suggested_tier;
      if (preselect != null) setEntryTier(preselect);
    }).catch(() => {});
    return () => { live = false; };
  }, [appId]);

  const refer = async () => {
    setError(null);
    const res = await mutations.referCommittee(appId, entryTier === '' ? undefined : Number(entryTier));
    if (res.ok) { await onDone(); toast({ tone: 'success', message: 'Referred to committee.' }); }
    else setError(res.error);
  };

  return (
    <Card className="mt-6" stripe="primary">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Refer to credit committee</h3></Card.Header>
      <Card.Body>
        <p className="text-xs text-gray-500 mb-3">
          This facility is committee-tier under the bank's policy. Most cases enter at the Branch
          Credit Committee; CIB / head-office cases may enter a higher tier directly.
        </p>
        {suggested?.name && (
          <div className="mb-3 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800">
            {suggested.mustClimb ? (
              <>By limit, KES {suggested.amount.toLocaleString()} enters at <span className="font-semibold">{suggested.name}</span> and climbs to <span className="font-semibold">{suggested.finalName}</span> — each committee's verdict is captured before the next.</>
            ) : (
              <>By limit, KES {suggested.amount.toLocaleString()} is decided by <span className="font-semibold">{suggested.name}</span> (pre-selected). You can override below.</>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 items-end">
          <div>
            <label className="text-sm font-medium text-gray-700">Entry tier</label>
            <select value={entryTier} onChange={(e) => setEntryTier(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={mutations.loading}
              className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-base text-gray-900">
              <option value="">Default (Branch Credit Committee)</option>
              {tiers.filter((t) => t.can_be_entry).map((t) => (
                <option key={t.tier} value={t.tier}>Tier {t.tier}: {t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <Button variant="primary" onClick={refer} disabled={mutations.loading}>Refer to committee</Button>
          </div>
        </div>
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
      </Card.Body>
    </Card>
  );
}

function WfCommittee({ application, mutations, toast, onDone, canVote, canResolve }: {
  application: LoanApplication; mutations: WfMutations; toast: WfToast;
  onDone: () => Promise<unknown> | unknown; canVote: boolean; canResolve: boolean;
}) {
  const [memberId, setMemberId] = useState('');
  const [vote, setVote] = useState('YES');
  const [rationale, setRationale] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [members, setMembers] = useState<CommitteeMember[]>([]);
  const votes = application.committee?.votes ?? [];

  useEffect(() => {
    let live = true;
    getCommitteeCharter()
      .then((ch) => { if (live) setMembers(ch.members || []); })
      .catch(() => { /* dropdown falls back to manual entry */ });
    return () => { live = false; };
  }, []);

  const castVote = async () => {
    setError(null);
    if (!memberId.trim()) { setError('Member id required.'); return; }
    const res = await mutations.voteCommittee(application.id, { member_id: memberId.trim(), vote, rationale: rationale.trim() });
    if (res.ok) { await onDone(); toast({ tone: 'success', message: `Vote recorded: ${memberId} ${vote}` }); setRationale(''); }
    else setError(res.error);
  };
  const resolve = async () => {
    setError(null);
    const res = await mutations.resolveCommittee(application.id, {});
    if (res.ok) { await onDone(); toast({ tone: 'info', message: 'Committee resolved.' }); }
    else setError(res.error);
  };
  return (
    <Card className="mt-6" stripe="primary">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Credit committee</h3></Card.Header>
      <Card.Body>
        {application.committee?.current_tier_name && (
          <div className="mb-3 flex items-center gap-2">
            <Badge tone="brand">Tier {application.committee.current_tier}: {application.committee.current_tier_name}</Badge>
            {(application.committee.tier_history?.length ?? 0) > 0 && (
              <span className="text-xs text-gray-500">
                escalated from {application.committee.tier_history!.map((h) => h.tier_name || `Tier ${h.tier}`).join(' → ')}
              </span>
            )}
          </div>
        )}
        {votes.length > 0 && (
          <div className="mb-3 text-xs text-gray-600">
            Votes recorded: {votes.map((v) => `${v.member_id}:${v.vote}`).join(', ')}
          </div>
        )}
        {canVote && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
            <div>
              <label className="text-sm font-medium text-gray-700">Committee member</label>
              {members.length > 0 ? (
                <select value={memberId} onChange={(e) => setMemberId(e.target.value)} disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-base text-gray-900">
                  <option value="">Select member…</option>
                  {members.map((m) => (
                    <option key={m.member_id} value={m.member_id}>
                      {m.name} — {m.role.replace(/_/g, ' ').toLowerCase()}{m.is_independent ? ' (independent)' : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <Input label="" value={memberId}
                       onChange={(e) => setMemberId(e.target.value)} disabled={mutations.loading}
                       placeholder="m1" />
              )}
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Vote</label>
              <select value={vote} onChange={(e) => setVote(e.target.value)} disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-base text-gray-900">
                {['YES', 'NO', 'ABSTAIN', 'RECUSED'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <Input label="Rationale (optional)" value={rationale}
                   onChange={(e) => setRationale(e.target.value)} disabled={mutations.loading} />
          </div>
        )}
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        <div className="mt-3 flex gap-2">
          {canVote && <Button variant="ghost" onClick={castVote} disabled={mutations.loading}>Record vote</Button>}
          {canResolve && <Button variant="primary" onClick={resolve} disabled={mutations.loading}>Resolve committee</Button>}
          {canResolve && (
            <Button variant="secondary" onClick={async () => {
              setError(null);
              const res = await mutations.submitUpward(application.id, '');
              if (res.ok) { await onDone(); toast({ tone: 'info', message: 'Submitted to the next tier.' }); }
              else setError(res.error);
            }} disabled={mutations.loading}>Submit to next tier ↑</Button>
          )}
        </div>
      </Card.Body>
    </Card>
  );
}


// ─── Attachments & Branch Credit Committee (BCC) ──────────────────────
// Reference-mode attachments: the bank's document store holds the files;
// we record filename + ref. The BCC card captures the branch committee's
// signed outcome, which auto-files as a 'bcc_minutes' attachment.
const ATTACHMENT_KINDS = [
  'bcc_minutes', 'financials', 'kyc', 'valuation', 'collateral',
  'bank_statements', 'board_resolution', 'other',
];

function AttachmentsBccCard({ appId, canEdit, toast }: {
  appId: string; canEdit: boolean; toast: ReturnType<typeof useToast>['toast'];
}) {
  const [atts, setAtts] = useState<LmsAttachment[]>([]);
  const [bcc, setBcc] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  // Add-attachment form
  const [kind, setKind] = useState('financials');
  const [filename, setFilename] = useState('');
  const [ref, setRef] = useState('');
  // BCC form
  const [showBcc, setShowBcc] = useState(false);
  const [bccVerdict, setBccVerdict] = useState('recommended');
  const [bccBranch, setBccBranch] = useState('');
  const [bccChair, setBccChair] = useState('');
  const [bccAttendees, setBccAttendees] = useState('');
  const [bccMinutes, setBccMinutes] = useState('');
  const [bccFile, setBccFile] = useState('');

  const load = async () => {
    try {
      const r = await listLmsAttachments(appId);
      setAtts(r.attachments || []);
      setBcc(r.bcc || null);
    } catch { /* page-local, non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [appId]);

  const onAdd = async () => {
    if (!filename.trim() && !ref.trim()) {
      toast({ tone: 'danger', message: 'Enter a filename or reference.' }); return;
    }
    setBusy(true);
    try {
      await addLmsAttachment(appId, { kind, filename: filename.trim(), ref: ref.trim() });
      setFilename(''); setRef('');
      toast({ tone: 'success', message: 'Attachment added.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed.' });
    } finally { setBusy(false); }
  };

  const onBcc = async () => {
    if (!bccBranch.trim()) { toast({ tone: 'danger', message: 'Branch is required.' }); return; }
    setBusy(true);
    try {
      await recordLmsBcc(appId, {
        verdict: bccVerdict, branch: bccBranch.trim(), chaired_by: bccChair.trim(),
        attendees: bccAttendees.split(',').map((s) => s.trim()).filter(Boolean),
        minutes: bccMinutes.trim(), filename: bccFile.trim(),
      });
      setShowBcc(false);
      toast({ tone: 'success', message: 'BCC outcome recorded.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed.' });
    } finally { setBusy(false); }
  };

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Attachments &amp; Branch Credit Committee</h2>
      </Card.Header>
      <Card.Body>
        {/* BCC summary, if recorded */}
        {bcc ? (
          <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Branch Credit Committee</div>
            <div className="text-sm text-gray-800">
              <span className="font-medium capitalize">{String(bcc.verdict)}</span>
              {bcc.branch ? <> · {String(bcc.branch)}</> : null}
              {bcc.chaired_by ? <> · chaired by {String(bcc.chaired_by)}</> : null}
            </div>
            {Array.isArray(bcc.attendees) && bcc.attendees.length > 0 && (
              <div className="text-xs text-gray-500 mt-1">Signatories: {(bcc.attendees as string[]).join(', ')}</div>
            )}
            {bcc.minutes ? <div className="text-sm text-gray-600 mt-1 whitespace-pre-line">{String(bcc.minutes)}</div> : null}
          </div>
        ) : (
          <div className="mb-4 text-sm text-gray-500">
            No Branch Credit Committee outcome recorded yet.
          </div>
        )}

        {/* Attachments list */}
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
          Attachments ({atts.length})
        </div>
        {atts.length > 0 ? (
          <ul className="text-sm text-gray-700 space-y-1 mb-4">
            {atts.map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <span className="inline-block rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{a.kind}</span>
                <span className="font-medium">{a.filename || a.ref || '(reference)'}</span>
                {a.added_by ? <span className="text-xs text-gray-400">· {a.added_by}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-gray-400 mb-4">No attachments yet.</div>
        )}

        {canEdit && (
          <>
            {/* Add attachment */}
            <div className="rounded-lg border border-gray-100 p-3 mb-3">
              <div className="text-xs font-medium text-gray-700 mb-2">Add attachment (reference)</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <select value={kind} onChange={(e) => setKind(e.target.value)}
                  className="rounded-md border border-gray-300 px-2 py-1.5 text-sm">
                  {ATTACHMENT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
                <Input label="" placeholder="Filename" value={filename}
                  onChange={(e) => setFilename(e.target.value)} disabled={busy} />
                <Input label="" placeholder="Store ref / URL" value={ref}
                  onChange={(e) => setRef(e.target.value)} disabled={busy} />
              </div>
              <div className="mt-2">
                <Button onClick={onAdd} disabled={busy}>{busy ? 'Working…' : 'Add attachment'}</Button>
              </div>
            </div>

            {/* Record BCC */}
            {!showBcc ? (
              <Button variant="secondary" onClick={() => setShowBcc(true)}>Record Branch Credit Committee outcome</Button>
            ) : (
              <div className="rounded-lg border border-gray-100 p-3">
                <div className="text-xs font-medium text-gray-700 mb-2">Branch Credit Committee outcome</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <select value={bccVerdict} onChange={(e) => setBccVerdict(e.target.value)}
                    className="rounded-md border border-gray-300 px-2 py-1.5 text-sm">
                    {['recommended', 'approved', 'declined', 'deferred'].map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                  <Input label="" placeholder="Branch" value={bccBranch} onChange={(e) => setBccBranch(e.target.value)} disabled={busy} />
                  <Input label="" placeholder="Chaired by (Branch Manager)" value={bccChair} onChange={(e) => setBccChair(e.target.value)} disabled={busy} />
                  <Input label="" placeholder="Attendees (comma-separated)" value={bccAttendees} onChange={(e) => setBccAttendees(e.target.value)} disabled={busy} />
                  <Input label="" placeholder="Signed minutes filename" value={bccFile} onChange={(e) => setBccFile(e.target.value)} disabled={busy} />
                </div>
                <textarea placeholder="Minutes / committee notes" value={bccMinutes}
                  onChange={(e) => setBccMinutes(e.target.value)} disabled={busy}
                  className="mt-2 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" rows={3} />
                <div className="mt-2 flex gap-2">
                  <Button onClick={onBcc} disabled={busy}>{busy ? 'Working…' : 'Record BCC outcome'}</Button>
                  <Button variant="secondary" onClick={() => setShowBcc(false)} disabled={busy}>Cancel</Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card.Body>
    </Card>
  );
}


// ─── Credit Report (CR) — hybrid auto-populated appraisal memo ─────────
// Template-driven: renders sections/fields from the server. auto/cbs fields
// show prefilled (editable but tinted to signal provenance); rm fields are
// blank for the relationship owner. Save draft or mark complete (required
// fields enforced server-side).
function CreditReportCard({ appId, canEdit, toast }: {
  appId: string; canEdit: boolean; toast: ReturnType<typeof useToast>['toast'];
}) {
  const [cr, setCr] = useState<CrView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      const r = await getLmsCr(appId);
      setCr(r.cr);
    } catch { /* page-local, non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [appId]);

  const valueFor = (key: string): string => {
    if (key in edits) return edits[key];
    const v = cr?.values?.[key];
    return v === undefined || v === null ? '' : String(v);
  };

  const save = async (completed: boolean) => {
    setBusy(true);
    try {
      // Send only RM-edited fields; server re-derives auto/cbs on read.
      await saveLmsCr(appId, { values: edits, completed });
      setEdits({});
      toast({ tone: 'success', message: completed ? 'CR marked complete.' : 'CR saved.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed.' });
    } finally { setBusy(false); }
  };

  if (!cr) return null;

  const sourceTint = (f: CrField, hasValue: boolean) => {
    if (f.source === 'cbs') return hasValue ? 'bg-blue-50/50' : '';
    if (f.source === 'auto') return hasValue ? 'bg-gray-50' : '';
    return '';
  };

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Credit Report (CR)</h2>
        <div className="flex items-center gap-2">
          {cr.completed && <Badge tone="success">Complete</Badge>}
          {!cr.cbs_available && <span className="text-xs text-gray-400">CBS data unavailable — fill manually</span>}
          <button className="text-sm text-brand-primary" onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide' : 'Open'}
          </button>
        </div>
      </Card.Header>
      {open && (
        <Card.Body>
          <p className="text-xs text-gray-500 mb-4">
            Fields tinted blue come from CBS; grey from the application. Both are editable.
            Plain fields are for the relationship owner to complete.
          </p>
          <div className="space-y-6">
            {cr.template.sections.map((sec) => (
              <div key={sec.key}>
                <div className="text-sm font-semibold text-gray-800 mb-2 pb-1 border-b border-gray-100">
                  {sec.title}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {sec.fields.map((f) => {
                    const val = valueFor(f.key);
                    const isLong = ['strengths', 'weaknesses', 'mitigants', 'rm_recommendation', 'conditions', 'purpose'].includes(f.key);
                    return (
                      <div key={f.key} className={isLong ? 'md:col-span-2' : ''}>
                        <label className="block text-xs text-gray-600 mb-1">
                          {f.label}{f.required && <span className="text-red-500"> *</span>}
                          {f.source !== 'rm' && <span className="ml-1 text-[10px] uppercase text-gray-400">({f.source})</span>}
                        </label>
                        {isLong ? (
                          <textarea
                            value={val} disabled={!canEdit || busy} rows={2}
                            onChange={(e) => setEdits((p) => ({ ...p, [f.key]: e.target.value }))}
                            className={`w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm ${sourceTint(f, !!val)}`}
                          />
                        ) : (
                          <input
                            value={val} disabled={!canEdit || busy}
                            onChange={(e) => setEdits((p) => ({ ...p, [f.key]: e.target.value }))}
                            className={`w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm ${sourceTint(f, !!val)}`}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          {canEdit && (
            <div className="mt-4 flex gap-2">
              <Button onClick={() => save(false)} disabled={busy}>{busy ? 'Working…' : 'Save draft'}</Button>
              <Button variant="secondary" onClick={() => save(true)} disabled={busy}>Mark complete</Button>
            </div>
          )}
          {cr.updated_by && (
            <div className="mt-2 text-xs text-gray-400">Last saved by {cr.updated_by}</div>
          )}
        </Card.Body>
      )}
    </Card>
  );
}

// ── Branch committee decisions (4b-7b): read-only, carried from the deal ──
function BranchCommitteeDecisionsCard({ appId }: { appId: string }) {
  const [data, setData] = useState<LmsCommitteeRecordsResponse | null>(null);
  useEffect(() => {
    getLmsCommitteeRecords(appId).then(setData).catch(() => setData(null));
  }, [appId]);
  if (!data) return null;
  const codes = Object.keys(data.committee_records || {});
  if (codes.length === 0) return null;
  const tone = (o: string) => (o === 'APPROVED' ? 'success' : o === 'REJECTED' ? 'danger' : 'warning');
  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Branch Committee Decisions</h2>
        <Badge tone="info" size="sm">from branch</Badge>
      </Card.Header>
      <Card.Body>
        <p className="mb-3 text-xs text-gray-500">Recorded at the branch before submission (read-only).</p>
        <div className="space-y-3">
          {codes.map((code) => {
            const r = data.committee_records[code];
            return (
              <div key={code} className="rounded border p-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{code}</span>
                  <Badge tone={tone(r.outcome)} size="sm">{r.outcome}</Badge>
                </div>
                <p className="text-xs text-gray-500">Recorded by {r.recorded_by} on {r.recorded_at}.</p>
                {r.mode === 'voting' && r.votes.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-xs text-gray-600">
                    {r.votes.map((v, i) => <li key={i}>{v.name} ({v.role}): {v.vote}</li>)}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </Card.Body>
    </Card>
  );
}


// C2: correctness-check action set — mark ready for committee or return for rework,
// with an optional opinion for the Chief.
// ─────────── Credit Analyst Workbench panel (P3) ───────────
const WB_NOTE_CATEGORIES = ['OBSERVATION', 'CONCERN', 'FOLLOW_UP', 'RECOMMENDATION', 'DECISION_RATIONALE'];

function CreditWorkbenchPanel({ appId, toast }: {
  appId: string; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const { user } = useRole();
  const [wb, setWb] = useState<WorkbenchView | null>(null);
  const [busy, setBusy] = useState(false);
  const [noteCat, setNoteCat] = useState('OBSERVATION');
  const [noteBody, setNoteBody] = useState('');

  const load = async () => {
    try { setWb(await getApplicationWorkbench(appId)); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed to load workbench' }); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [appId]);

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await refreshWorkbench(appId);
      setWb((prev) => prev ? { ...prev, summary: r.summary, conflict_report: r.conflict_report } : prev);
      toast({ tone: 'success', message: 'Engines refreshed.' });
      await load();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Refresh failed' }); }
    finally { setBusy(false); }
  };

  const addNote = async () => {
    if (!noteBody.trim()) return;
    setBusy(true);
    try {
      await addWorkbenchNote(appId, noteCat, noteBody.trim());
      setNoteBody('');
      toast({ tone: 'success', message: 'Note recorded.' });
      await load();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Note failed' }); }
    finally { setBusy(false); }
  };

  if (!wb) return null;
  const cr = wb.conflict_report;
  const s = wb.summary;

  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Credit Analyst Workbench</h3>
          <span className="text-xs text-gray-500">Session {s.state ?? '—'}</span>
        </div>
      </Card.Header>
      <Card.Body>
        <p className="mb-3 text-xs text-gray-500">
          What each credit engine currently says for this customer, and where they conflict.
        </p>

        {/* Conflict report — front and centre */}
        <div className={`mb-3 rounded border p-3 text-sm ${cr.conflict_count > 0 ? 'border-amber-300 bg-amber-50' : 'border-green-200 bg-green-50'}`}>
          {cr.conflict_count > 0 ? (
            <div>
              <span className="font-medium text-amber-800">{cr.conflict_count} conflict{cr.conflict_count === 1 ? '' : 's'} across engines</span>
              <div className="mt-2 space-y-1">
                {cr.conflicts.map((c, i) => (
                  <div key={i} className="text-xs text-amber-900">
                    <span className="font-medium">{c.decision}</span> — {c.sources.join(', ')}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <span className="text-green-800">No conflicts across the engines pulled ({cr.total_pulls} pull{cr.total_pulls === 1 ? '' : 's'}).</span>
          )}
        </div>

        {/* WB role lens (P4): role-shaped read-side signals */}
        {wb.role_lens && (() => {
          const r = String(user?.role ?? '').toLowerCase();
          const ca = wb.role_lens.credit_admin;
          const isAdminOrTrops = r.includes('admin') || r.includes('trops') || r.includes('operations') || r.includes('disburs');
          const isRm = r.includes('relationship') || r.includes('personal banker') || r.includes(' ro ') || r.includes('officer');
          const roleLabel = isAdminOrTrops ? 'Credit Admin / Trops' : (r.includes('analyst') ? 'Analyst' : (isRm ? 'Relationship Manager' : 'Credit'));
          return (
            <div className="mb-3 rounded border border-gray-200 bg-gray-50 p-3 text-xs">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium text-gray-700">Your view: {roleLabel}</span>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-600">
                <span>Appraisal (CR): {wb.role_lens.cr.completed === null ? 'n/a' : (wb.role_lens.cr.completed ? 'complete ✓' : 'incomplete')}</span>
                {ca.linked ? (
                  <>
                    <span>Conditions: {ca.conditions_met}/{ca.conditions_total} met</span>
                    <span>All met: {ca.all_conditions_met ? 'yes ✓' : 'no'}</span>
                    <span>Cleared: {ca.cleared ? 'yes ✓' : 'no'}</span>
                    <span>Disbursed: {ca.disbursed ? 'yes ✓' : 'no'}</span>
                  </>
                ) : <span className="text-gray-400">No credit-admin case yet</span>}
              </div>
            </div>
          );
        })()}

        {/* Engine sources */}
        <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
          <div>
            <p className="font-medium text-gray-600">Engines pulled ({(s.sources_pulled ?? []).length})</p>
            {(s.sources_pulled ?? []).map((src) => <div key={src} className="text-green-700">✓ {src}</div>)}
          </div>
          <div>
            <p className="font-medium text-gray-600">Not yet pulled ({(s.sources_missing ?? []).length})</p>
            {(s.sources_missing ?? []).map((src) => <div key={src} className="text-gray-400">• {src}</div>)}
          </div>
        </div>

        <div className="mb-4">
          <Button variant="primary" onClick={() => void refresh()} disabled={busy}>
            {busy ? 'Refreshing…' : 'Refresh engines'}
          </Button>
        </div>

        {/* Analyst notes */}
        <div className="border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">
            Analyst notes {s.notes_count ? `(${s.notes_count})` : ''}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select value={noteCat} onChange={(e) => setNoteCat(e.target.value)}
              className="rounded border border-gray-300 px-2 py-1.5 text-sm">
              {WB_NOTE_CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
            <input value={noteBody} onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Record an observation, concern, or rationale…"
              className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm" />
            <Button variant="ghost" onClick={() => void addNote()} disabled={busy || !noteBody.trim()}>Add note</Button>
          </div>
          {s.notes_by_category && Object.keys(s.notes_by_category).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
              {Object.entries(s.notes_by_category).map(([cat, n]) => (
                <span key={cat} className="rounded bg-gray-100 px-2 py-0.5">{cat.replace(/_/g, ' ')}: {n}</span>
              ))}
            </div>
          )}
        </div>
      </Card.Body>
    </Card>
  );
}

function CorrectnessPanel({ appId, onDone, toast }: {
  appId: string; onDone: () => Promise<unknown> | unknown; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [opinion, setOpinion] = useState('');
  const [busy, setBusy] = useState(false);
  const act = async (decision: 'ready' | 'rework') => {
    setBusy(true);
    try {
      await setCommitteeReadiness(appId, decision, opinion.trim() || undefined);
      toast({ tone: 'success', message: decision === 'ready' ? 'Marked ready for committee.' : 'Returned for rework.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' });
    } finally { setBusy(false); }
  };
  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Correctness check</h3></Card.Header>
      <Card.Body>
        <p className="mb-2 text-xs text-gray-500">Confirm the case is well-packaged for committee, or return it for rework. You may add an opinion for the Chief.</p>
        <textarea
          value={opinion}
          onChange={(e) => setOpinion(e.target.value)}
          placeholder="Optional opinion / notes for the Chief…"
          className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          rows={3}
        />
        <div className="flex gap-2">
          <Button variant="primary" onClick={() => void act('ready')} disabled={busy}>Mark ready for committee</Button>
          <Button variant="ghost" onClick={() => void act('rework')} disabled={busy}>Return for rework</Button>
        </div>
      </Card.Body>
    </Card>
  );
}


// C3b: committee pre-read — members record a non-binding view; everyone sees leanings.
function CommitteePreReadPanel({ appId, toast }: {
  appId: string; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [data, setData] = useState<CommitteePreReadsResponse | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { setData(await fetchCommitteePreReads(appId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [appId]);
  const record = async (view: 'leaning_approve' | 'leaning_decline' | 'questions') => {
    setBusy(true);
    try {
      await recordCommitteePreRead(appId, view, note.trim() || undefined);
      toast({ tone: 'success', message: 'Pre-read recorded.' });
      setNote(''); await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not record' });
    } finally { setBusy(false); }
  };
  const label: Record<string, string> = {
    leaning_approve: 'Leaning approve', leaning_decline: 'Leaning decline', questions: 'Questions',
  };
  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Committee pre-read (non-binding)</h3></Card.Header>
      <Card.Body>
        <p className="mb-2 text-xs text-gray-500">Members review independently ahead of the convened meeting. This is a non-binding leaning, not the vote.</p>
        {data && (
          <div className="mb-3 flex gap-3 text-xs">
            <span className="rounded bg-green-50 px-2 py-1 text-green-700">Approve: {data.tally.leaning_approve ?? 0}</span>
            <span className="rounded bg-red-50 px-2 py-1 text-red-700">Decline: {data.tally.leaning_decline ?? 0}</span>
            <span className="rounded bg-amber-50 px-2 py-1 text-amber-700">Questions: {data.tally.questions ?? 0}</span>
          </div>
        )}
        <textarea value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note with your leaning…"
          className="mb-2 w-full rounded border border-gray-300 px-3 py-2 text-sm" rows={2} />
        <div className="flex gap-2">
          <Button variant="primary" size="sm" onClick={() => void record('leaning_approve')} disabled={busy}>Leaning approve</Button>
          <Button variant="ghost" size="sm" onClick={() => void record('leaning_decline')} disabled={busy}>Leaning decline</Button>
          <Button variant="ghost" size="sm" onClick={() => void record('questions')} disabled={busy}>Questions</Button>
        </div>
        {data && data.pre_reads.length > 0 && (
          <div className="mt-3 space-y-1">
            {data.pre_reads.map((r) => (
              <div key={r.by_code} className="rounded bg-gray-50 px-2 py-1 text-xs">
                <span className="font-medium">{r.by_name}</span>: {label[r.view] ?? r.view}
                {r.note && <span className="text-gray-500"> — {r.note}</span>}
              </div>
            ))}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
