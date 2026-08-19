// v10.511 Phase 4 Batch β2 — PipelineDealDetail page.
//
// The single-deal view at /pipeline/:dealId. Shows full deal info plus
// per-action inline panels gated by the α7 permissions object:
//   - Advance Stage panel    (when can_advance_stage)
//   - Request Cancellation panel (when can_request_cancel)
//
// Future β-batches will add panels for Edit (β3-or-later), Validate
// (β4), Approve Cancel (β4). The pattern established here — one panel
// per action, conditionally rendered by permission flag, inline form
// rather than modal dialog — should scale to all of them.
//
// Why inline panels and not modal dialogs:
//   - The v10.496 primitive set has no Dialog component
//   - Inline panels are simpler and work on mobile without overlay logic
//   - Two consumers is too few to know what a Dialog primitive should do
//   - When a third consumer appears (β3 Create with α5 conflict UX),
//     we'll see the pattern and can decide whether Dialog earns its keep
//
// Data fetching:
//   This page is the FIRST consumer of GET /api/pipeline/deals/{id}.
//   It fetches independently (not via PipelineProvider, which is the
//   list provider). The fetch happens on mount and after each
//   successful mutation. No Context Provider — the data is page-local.
//
// Routing back to list:
//   On success of any mutation, we DON'T navigate away. The user
//   sees the updated deal state on the same page, with the relevant
//   action panel now closed (because the permission changed: e.g.
//   after request_cancel, can_request_cancel becomes false). They
//   navigate back to /pipeline when they want.

import { displayName } from "../lib/names";
import { useCallback, useEffect, useState } from 'react';
import { FacilitiesTable, facilitiesToPrintHtml } from '@/components/FacilitiesTable';
import { printDocument, escapeHtml } from '@/lib/print';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useToast } from '@/components/Toast';
import { fetchPipelineDealDetail, fetchCreditChecklist, fetchNextStep, type NextStep, getDealCr, saveDealCr, getDealCommitteeRecords, recordDealCommitteeDecision, castCommitteeVote, appealCommitteeDecision, closeDealAsLost, type CommitteeGate, type CommitteeRecordsResponse, type CrView, type CrField, submitDealToCredit, referExistingDeal, fetchDealSla, ApiValidationError, AuthExpiredError, listDealDocuments, uploadDealDocument, deleteDealDocument, createValidationRequest, resolveValidationRequest, liftDealHold, fetchDealJourney, type ValidationRequest, type StaffMember, type SlaViolation, type DealDocumentsResponse,
  fetchRateState, requestRate, acceptCounterRate, declineCounterRate, type RateRequestState,
} from '@/lib/api';
import { Timeline } from '@/components/Timeline';
import type { LoanAppHistoryEvent } from '@/types/lms';
import { useRole } from '@/hooks/useRole';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { DocumentViewerModal } from '@/components/DocumentViewerModal';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import { WorkbenchShell } from '@/components/WorkbenchShell';
import { StaffPicker } from '@/components/StaffPicker';
import {
  ADVANCE_TARGET_STAGES,
  type PipelineDeal,
  type DealPermissions,
  type CreditChecklistResponse,
} from '@/types/pipeline';


// ── Format helpers (mirroring Pipeline.tsx) ─────────────────────────────

function formatValue(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  // Backend sometimes returns ISO datetime, sometimes just date.
  // Take the first 10 chars (YYYY-MM-DD) which works for either.
  return s.slice(0, 10);
}


// ── Detail page component ───────────────────────────────────────────────

import { AffordabilityAppraisal } from '@/components/AffordabilityAppraisal';

export function PipelineDealDetail() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { toast } = useToast();
  const mutations = usePipelineDealMutations();

  const [deal, setDeal] = useState<PipelineDeal | null>(null);
  const [permissions, setPermissions] = useState<DealPermissions | null>(null);
  const [sla, setSla] = useState<SlaViolation | null>(null);
  const [stageFlow, setStageFlow] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { user: viewer } = useRole();

  // ── Fetch routine ─────────────────────────────────────────────────────
  // Called on mount and after each successful mutation. Refreshes the
  // deal + its permissions object (which may have shifted state).

  const reloadDeal = useCallback(async () => {
    if (!dealId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const response = await fetchPipelineDealDetail(dealId);
      setDeal(response.deal);
      setPermissions(response.permissions);
      setStageFlow(response.stage_flow ?? []);
      // Per-deal SLA — non-blocking; failure leaves the panel hidden, not the page.
      fetchDealSla(dealId).then((r) => setSla(r.sla)).catch(() => setSla(null));
    } catch (e) {
      if (e instanceof AuthExpiredError) {
        // AuthProvider's 401 callback already flipped state; the route
        // guard will redirect. Don't show our own error.
        return;
      }
      const msg = e instanceof Error ? e.message : 'Failed to load deal';
      setLoadError(msg);
      setDeal(null);
      setPermissions(null);
    } finally {
      setLoading(false);
    }
  }, [dealId]);

  // Initial load + re-fetch when dealId changes
  useEffect(() => {
    void reloadDeal();
  }, [reloadDeal]);

  // ── Render guard: deal id missing or 404 ──────────────────────────────

  if (!dealId) {
    return (
      <DetailFrame title="Deal">
        <Card className="mt-8">
          <Card.Body>
            <Badge tone="danger">Missing deal ID</Badge>
            <p className="mt-2 text-sm text-gray-700">
              No deal ID in URL. <Link to="/pipeline" className="text-brand-primary underline">Back to pipeline</Link>.
            </p>
          </Card.Body>
        </Card>
      </DetailFrame>
    );
  }

  if (loading && !deal) {
    return (
      <DetailFrame title={`Deal ${dealId}`}>
        <Card className="mt-8">
          <Card.Body>
            <Skeleton shape="line" className="w-1/2" />
            <div className="mt-4">
              <Skeleton shape="block" className="h-6 w-full" />
            </div>
            <div className="mt-2">
              <Skeleton shape="block" className="h-6 w-full" />
            </div>
          </Card.Body>
        </Card>
      </DetailFrame>
    );
  }

  if (loadError || !deal) {
    return (
      <DetailFrame title={`Deal ${dealId}`}>
        <Card className="mt-8">
          <Card.Header>
            <div className="flex items-center gap-3">
              <Badge tone="danger">Not found</Badge>
              <h2 className="text-base font-semibold text-gray-900">
                Deal {dealId} unavailable
              </h2>
            </div>
            <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
              Back to pipeline
            </Button>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-gray-700">
              {loadError ?? 'This deal could not be loaded. It may be outside your cascade scope, or the deal ID may not exist.'}
            </p>
            <p className="text-xs text-gray-400 mt-3">
              The server returns 404 (not 403) for out-of-scope deals to avoid leaking deal existence — this is α7 design.
            </p>
          </Card.Body>
        </Card>
      </DetailFrame>
    );
  }

  // ── Main render — deal + action panels ────────────────────────────────
  // Document/credit-review edit rights: the deal OWNER always; admins/executives retain
  // override rights, but every edit they make is audit-logged server-side (upload/CR/committee
  // all call _audit with the actor). Everyone else is view-only.
  // Edit override is restricted to the literal system Admin role (granted via config /
  // role-capability), NOT senior bankers like Heads/Directors — they view-only on deals
  // they don't own. Admin edits remain audit-logged server-side.
  const _viewerIsAdmin = String(viewer?.role ?? '').trim().toLowerCase() === 'admin';
  const canEditDocs = (!!viewer?.staff_code && String(viewer.staff_code) === String(deal.staff_code)) || _viewerIsAdmin;


  return (
    <DetailFrame title={`Deal ${deal.id}`}>
      {/* Phase L: origination lock banner — the deal is with Credit and edits/
          stage moves are disabled until it's returned or info is requested. */}
      {deal.locked && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <div className="flex items-start gap-2">
            <span className="text-amber-600" aria-hidden>🔒</span>
            <div className="text-sm text-amber-800">
              {/* "Locked - with Credit" is wrong at a committee stage: the
                  case is with the COMMITTEE, and the branch reading this
                  concluded it had gone to credit. Name where it actually is. */}
              <span className="font-semibold">
                Locked — with {String(deal.stage || '').toLowerCase().includes('committee')
                  ? (deal.stage || 'the committee')
                  : 'Credit'}.
              </span>{' '}
              {deal.lock_reason || 'Editing and stage changes are disabled until the case is returned for rework or information is requested.'}
            </div>
          </div>
        </div>
      )}

      {/* Cancellation-pending notice */}
      {deal.cancel_requested && !deal.cancel_approved && (
        <Card className="mb-4" stripe="accent">
          <Card.Body>
            <div className="flex items-start gap-3">
              <Badge tone="warning" size="md">Pending manager approval</Badge>
              <div className="flex-1">
                <div className="text-sm text-gray-800">
                  This deal has a cancellation request awaiting manager review.
                </div>
                <div className="text-xs text-gray-600 mt-1">
                  <span className="font-medium">Requested by:</span> {deal.cancel_requested_by || '—'}
                  {deal.cancel_reason && (
                    <>
                      {' · '}
                      <span className="font-medium">Reason:</span> {deal.cancel_reason}
                    </>
                  )}
                </div>
              </div>
            </div>
          </Card.Body>
        </Card>
      )}

      <WorkbenchShell
        title={deal.client_name || '—'}
        stage={deal.stage}
        badges={[
          ...(deal.locked ? [{ label: '🔒 Locked' }] : []),
          ...(deal.manager_validated ? [{ label: deal.validated_by_name ? `✓ Validated by ${deal.validated_by_name}` : '✓ Validated' }] : []),
          ...(deal.draft ? [{ label: 'Draft' }] : []),
        ]}
        idLabel={deal.id}
        onBack={() => navigate('/pipeline')}
        onRefresh={() => void reloadDeal()}
        details={sla && sla.state ? (
          <Card stripe={sla.state === 'breached' ? 'accent' : 'primary'}>
            <Card.Header>
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="text-sm font-semibold text-gray-900">SLA status</h3>
                <Badge
                  tone={sla.state === 'breached' ? 'danger' : sla.state === 'due_soon' ? 'warning' : 'success'}
                  size="sm"
                >
                  {sla.state === 'breached' ? 'Breached' : sla.state === 'due_soon' ? 'Due soon' : 'On track'}
                </Badge>
                <Badge tone={sla.clock === 'step' ? 'info' : 'neutral'} size="sm">
                  {sla.clock === 'step' ? (sla.step || 'step').replace(/_/g, ' ') : 'age clock'}
                </Badge>
                {sla.commitment_status === 'active' && (
                  <Badge tone="info" size="sm">committed {sla.commitment?.committed_date}</Badge>
                )}
                {sla.commitment_status === 'unfulfilled' && (
                  <Badge tone="danger" size="sm">commitment overdue</Badge>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <DetailField label="Elapsed" value={`${sla.elapsed_business_days} bd`} />
                <DetailField label="Target" value={`${sla.target_days} bd`} />
                <DetailField
                  label={sla.breached ? 'Overdue' : 'Remaining'}
                  value={sla.breached ? `+${sla.overdue_business_days} bd` : `${sla.remaining_business_days ?? '—'} bd`}
                />
                <DetailField label="Escalation" value={(sla.escalate_to || '—').replace(/_/g, ' ')} />
              </div>
              {sla.commitment && (
                <p className="text-xs text-gray-500 mt-3">
                  <span className="font-medium">Commitment:</span> {sla.commitment.reason}
                  {' · by '}{sla.commitment.committed_date}
                  {sla.commitment.recorded_by_name ? ` (${sla.commitment.recorded_by_name})` : ''}
                </p>
              )}
            </Card.Body>
          </Card>
        ) : undefined}
        defaultTabId="journey"
        tabs={[
          { id: 'journey', label: 'Case Journey', color: '#0082BB', content: <CaseJourneyTab deal={deal} /> },
          // ── THE RATE, FOR DEPOSIT PRODUCTS ONLY ───────────────────────────
          // A term deposit is priced, not underwritten: there is no committee
          // and no credit decision, only a rate the customer wants and a desk
          // that answers. Showing this tab on a mortgage would be as wrong as
          // showing a committee on a fixed deposit.
          ...(/deposit|savings|account/i.test(String(deal.product_type || deal.product || ''))
            ? [{ id: 'rate', label: 'Rate', color: '#00897B',
                 content: <RateRequestPanel deal={deal} canEdit={canEditDocs}
                                            onChanged={() => void reloadDeal()} /> }]
            : []),
          { id: 'documents', label: 'Documentation and Credit Review', color: '#0097A7', content: <CreditSubmissionPanel deal={deal} onChanged={() => void reloadDeal()} stageFlow={stageFlow} canEdit={canEditDocs} /> },
          { id: 'affordability', label: 'Affordability', color: '#00A65A', content: <AffordabilityAppraisal dealId={deal.id} /> },
          { id: 'cr', label: 'Transaction Memo', color: '#7E57C2', content: <DealCreditReportCard dealId={deal.id} canEdit={canEditDocs} /> },
          { id: 'committee', label: 'Branch Credit Committee', color: '#EF6C00', content: <CommitteeJourneyCard dealId={deal.id} canEdit={canEditDocs} /> },
          { id: 'forwarding', label: 'Forwarding Memo', color: '#5C6BC0', content: <ForwardingMemoCard dealId={deal.id} canEdit={canEditDocs} /> },
          { id: 'actions', label: 'Actions', color: '#C62828', content: (
            <div className="space-y-6">
              {permissions?.can_advance_stage && (
                <AdvancePanel
                  deal={deal}
                  mutations={mutations}
                  stageFlow={stageFlow}
                  onSuccess={() => {
                    toast({ tone: 'success', message: 'Deal advanced.' });
                    void reloadDeal();
                  }}
                />
              )}
              <ValidationPanel deal={deal} onChanged={() => void reloadDeal()} />
              {!deal.draft && deal.referral_status !== 'pending' && (
                <ReferPanel deal={deal} onSuccess={() => void reloadDeal()} />
              )}
              {permissions?.can_request_cancel && (
                <RequestCancelPanel
                  deal={deal}
                  mutations={mutations}
                  onSuccess={() => {
                    toast({
                      tone: 'success',
                      message: 'Cancellation requested. A manager will review it.',
                    });
                    void reloadDeal();
                  }}
                />
              )}
            </div>
          ) },
        ]}
      />

      {/* Footer */}
      <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
        {branding?.ip_notice}
      </footer>
    </DetailFrame>
  );
}


// ── Frame component (shared header + main wrap) ─────────────────────────

interface DetailFrameProps {
  title:    string;
  children: React.ReactNode;
}

function DetailFrame({ title, children }: DetailFrameProps) {
  useEffect(() => { document.title = title; }, [title]);
  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 pt-3 pb-6">
        {children}
      </main>
    </div>
  );
}


// ── Detail field (label + value cell) ───────────────────────────────────

function DetailField({
  label, value, sub,
}: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </div>
      <div className="mt-1 text-sm text-gray-900">
        {value ?? '—'}
      </div>
      {sub && (
        <div className="text-[11px] text-gray-400 mt-0.5 font-mono">{sub}</div>
      )}
    </div>
  );
}


// ── Action panel: Submit to Credit Analysis (v10.574 Batch B10) ─────────

interface CreditPanelProps {
  deal:      PipelineDeal;
  onChanged: () => void;
}

// Phase V/R: line-manager validation. Shows validation requests; lets the deal
// owner request a reopen of a declined case; lets the resolved line manager
// (or admin) approve/reject. Approval of a reopen returns the case for rework.
function CaseJourneyTab({ deal }: { deal: PipelineDeal }) {
  const [events, setEvents] = useState<LoanAppHistoryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const dealId = deal.id;
  const load = useCallback(() => {
    setLoading(true);
    return fetchDealJourney(dealId)
      .then((r) => setEvents(r.journey || []))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [dealId]);
  // Re-fetch on deal change (parent reloadDeal after any action) so the journey
  // stays live as the case travels — validation, votes, stage moves, submission.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchDealJourney(dealId)
      .then((r) => { if (alive) setEvents(r.journey || []); })
      .catch(() => { if (alive) setEvents([]); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [dealId, deal.updated_at]);

  const facts: [string, string, boolean][] = [
    ['Product', String(deal.product_type ?? deal.product ?? '—'), false],
    ['Category', String(deal.pipeline_category ?? deal.deal_category ?? '—'), false],
    ['Client type', String(deal.client_type ?? '—'), false],
    ['Value', formatValue(deal.amount_kes ?? deal.deal_value, deal.currency ?? 'KES'), false],
    ['Currency', String(deal.currency ?? 'KES'), false],
    ['Stage', String(deal.stage ?? '—'), false],
    ['Expected close', deal.expected_close ? formatDate(deal.expected_close) : '—', false],
    ['Owner', deal.staff_name ? displayName(deal.staff_name) : '—', false],
    ['Deal', String(deal.id), true],
  ];

  return (
    <Card stripe="primary">
      <Card.Header>
        <div className="flex w-full items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Case Journey</h3>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">{events.length} events · who did what, when</span>
            <button onClick={() => void load()} className="text-xs font-medium text-brand-primary hover:underline">Refresh</button>
          </div>
        </div>
      </Card.Header>
      <Card.Body>
        {/* Executive summary — key deal facts folded into the journey, mirroring
            the LMS analysis Case Journey. One place to read the case: the facts,
            then the travelling history. */}
        <div className="mb-4 flex flex-wrap gap-x-6 gap-y-1.5 border-b border-gray-100 pb-3 text-xs">
          {facts.map(([label, value, mono]) => (
            <span key={label} className="flex items-center gap-1.5">
              <span className="uppercase tracking-wide text-gray-400">{label}</span>
              <span className={mono ? 'font-mono text-gray-800' : 'text-gray-800'}>{value}</span>
            </span>
          ))}
        </div>
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <Timeline events={events} emptyHint="No activity recorded yet. Creation, manager validation, stage moves, committee votes, and submission appear here as the case travels." />
        )}
      </Card.Body>
    </Card>
  );
}


function ValidationPanel({ deal, onChanged }: CreditPanelProps) {
  const { toast } = useToast();
  const { user } = useRole();
  const [reason, setReason] = useState('');
  const [holdReason, setHoldReason] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const requests = deal.validation_requests ?? [];
  const pending = requests.filter((r) => r.status === 'pending');
  const myCode = String(user?.staff_code ?? '');
  const isAdmin = Boolean(user?.role && /admin/i.test(user.role));
  const iAmDealValidator = !!myCode && myCode === String(deal.validator?.code ?? '');

  const request = async () => {
    if (!reason.trim()) { toast({ tone: 'danger', message: 'A reason is required.' }); return; }
    setBusy(true);
    try {
      await createValidationRequest(deal.id, 'reopen', reason.trim());
      toast({ tone: 'success', message: 'Reopen request sent to the line manager for validation.' });
      setReason(''); onChanged();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not send request.' });
    } finally { setBusy(false); }
  };

  const requestHold = async () => {
    if (!holdReason.trim()) { toast({ tone: 'danger', message: 'A reason is required.' }); return; }
    setBusy(true);
    try {
      await createValidationRequest(deal.id, 'hold', holdReason.trim());
      toast({ tone: 'success', message: 'Hold request sent to the line manager for validation.' });
      setHoldReason(''); onChanged();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not send request.' });
    } finally { setBusy(false); }
  };

  const liftHold = async () => {
    setBusy(true);
    try {
      await liftDealHold(deal.id, 'Hold lifted; clocks resumed.');
      toast({ tone: 'success', message: 'Hold lifted — clocks resumed.' });
      onChanged();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not lift hold.' });
    } finally { setBusy(false); }
  };

  const resolve = async (req: ValidationRequest, decision: 'approved' | 'rejected') => {
    setBusy(true);
    try {
      await resolveValidationRequest(deal.id, req.id, decision, (notes[req.id] ?? '').trim());
      toast({ tone: 'success', message: decision === 'approved' ? 'Request approved.' : 'Request rejected.' });
      onChanged();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not resolve request.' });
    } finally { setBusy(false); }
  };

  // Nothing to show unless a reopen/hold can be requested, it's on hold, or there are requests.
  if (!deal.reopen_available && !deal.hold_available && !deal.on_hold && requests.length === 0) return null;

  return (
    <Card>
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Line-manager validation</h2>
      </Card.Header>
      <Card.Body>
        {deal.on_hold && (
          <div className="mb-4 rounded-lg border border-orange-300 bg-orange-50 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-orange-900">⏸ On hold — SLA clocks frozen</span>
              {(iAmDealValidator || isAdmin) && (
                <Button variant="primary" onClick={() => void liftHold()} disabled={busy}>Lift hold</Button>
              )}
            </div>
            {deal.hold_reason ? <p className="mt-1 text-sm text-gray-700">{deal.hold_reason}</p> : null}
            {!(iAmDealValidator || isAdmin) && (
              <p className="mt-1 text-xs text-orange-700">Only the line manager can lift this hold.</p>
            )}
          </div>
        )}

        {deal.hold_available && (
          <div className="mb-4 rounded-lg border border-gray-200 p-3">
            <p className="mb-2 text-sm text-gray-700">
              Put this case on hold — this freezes all SLA clocks until lifted. Your line
              manager{deal.validator?.name ? ` (${displayName(deal.validator.name)})` : ''} must validate the request.
            </p>
            <Input value={holdReason} onChange={(e) => setHoldReason(e.target.value)}
              placeholder="Reason for placing on hold (required)" />
            <div className="mt-2">
              <Button variant="ghost" onClick={() => void requestHold()} disabled={busy || !holdReason.trim()}>
                Request hold
              </Button>
            </div>
          </div>
        )}

        {deal.reopen_available && (
          <div className="mb-4 rounded-lg border border-gray-200 p-3">
            <p className="mb-2 text-sm text-gray-700">
              This case was declined. You can request to reopen it for rework — your{' '}
              line manager{deal.validator?.name ? ` (${displayName(deal.validator.name)})` : ''} must validate the request.
            </p>
            <Input value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for reopening (required)" />
            <div className="mt-2">
              <Button variant="primary" onClick={() => void request()} disabled={busy || !reason.trim()}>
                Request reopen
              </Button>
            </div>
          </div>
        )}

        {pending.length > 0 && (
          <div className="space-y-3">
            {pending.map((r) => {
              const iAmValidator = !!myCode && myCode === String(r.validator_code ?? '');
              return (
                <div key={r.id} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-amber-900 capitalize">{r.kind} request — pending</span>
                    <span className="text-xs text-amber-700">
                      to validate: {r.validator_name || '—'}{r.admin_fallback ? ' (admin fallback)' : ''}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-gray-700">
                    <span className="text-gray-500">Reason:</span> {r.reason || '—'}
                    {r.requested_by_name ? <span className="text-gray-500"> · by {r.requested_by_name}</span> : null}
                  </p>
                  {(iAmValidator || isAdmin) ? (
                    <div className="mt-2">
                      <Input value={notes[r.id] ?? ''} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                        placeholder="Validation note (optional)" />
                      <div className="mt-2 flex gap-2">
                        <Button variant="primary" onClick={() => void resolve(r, 'approved')} disabled={busy}>Approve</Button>
                        <Button variant="ghost" onClick={() => void resolve(r, 'rejected')} disabled={busy}>Reject</Button>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-gray-400">Awaiting validation by the line manager.</p>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {requests.filter((r) => r.status !== 'pending').length > 0 && (
          <div className="mt-4 space-y-1">
            <p className="text-xs font-medium text-gray-500">History</p>
            {requests.filter((r) => r.status !== 'pending').map((r) => (
              <p key={r.id} className="text-xs text-gray-500">
                <span className="capitalize">{r.kind}</span> · {r.status}
                {r.validated_by_name ? ` by ${r.validated_by_name}` : ''}
                {r.note ? ` — ${r.note}` : ''}
              </p>
            ))}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}

// ── Credit Journey stepper: the credit stages in order, active one highlighted,
// future ones greyed. Reads checklist state (backend already enforces the sequence). ──
function creditSubmitLabel(checklist: CreditChecklistResponse, stageFlow?: string[]): string {
  const current = String(checklist.current_stage ?? '');
  // Only name CREDIT-JOURNEY stages (Documentation..Credit Analysis), never sales stages
  // like Negotiation. Slice the deal's flow to its credit portion first.
  const full = (stageFlow && stageFlow.length) ? stageFlow : CREDIT_JOURNEY_STAGES;
  const d = full.findIndex((st) => /documentation/i.test(st));
  const c = full.findIndex((st) => /^credit analysis$/i.test(st.trim()));
  const journey = (d >= 0 && c >= 0 && c >= d) ? full.slice(d, c + 1) : CREDIT_JOURNEY_STAGES;
  const idx = journey.findIndex((st) => st.toLowerCase() === current.toLowerCase());
  // If current is before/at the doc gate, submit enters the first gate after Documentation.
  const next =
    idx >= 0 && idx + 1 < journey.length ? journey[idx + 1]
    : idx < 0 && journey.length > 1 ? journey[1]
    : 'Credit Analysis';
  return `Submit to ${next}`;
}

const CREDIT_JOURNEY_STAGES = [
  'Documentation',
  'Branch Credit Committee Review',
  'Consumer Credit Analysis',
  'Department Credit Committee Review',
  'Credit Analysis',
];

function CreditJourneyStepper({ checklist, stageFlow }: { checklist: CreditChecklistResponse; stageFlow?: string[] }) {
  const current = String(checklist.current_stage ?? '');
  const submitted = Boolean(checklist.already_submitted);
  const journeyStages = (() => {
    const f = stageFlow ?? [];
    const d = f.findIndex((st) => /documentation/i.test(st));
    const c = f.findIndex((st) => /^credit analysis$/i.test(st.trim()));
    return (d >= 0 && c >= 0 && c >= d) ? f.slice(d, c + 1) : CREDIT_JOURNEY_STAGES;
  })();
  const currentIdx = journeyStages.findIndex(
    (st) => st.toLowerCase() === current.toLowerCase(),
  );
  const activeIdx = currentIdx >= 0 ? currentIdx : 0;

  return (
    <div className="mb-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-3">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Credit journey
      </div>
      <div className="flex items-start">
        {journeyStages.map((stage, i) => {
          const isDone = i < activeIdx;
          const isActive = i === activeIdx;
          const isAwaiting = isActive && submitted;
          let markCls = 'border-gray-300 text-gray-400 bg-white';
          let labelCls = 'text-gray-400';
          let mark = String(i + 1);
          if (isDone) { markCls = 'border-[#669438] bg-[#669438] text-white'; labelCls = 'text-[#669438]'; mark = '✓'; }
          else if (isAwaiting) { markCls = 'border-amber-500 text-amber-600 bg-white'; labelCls = 'text-amber-600 font-medium'; }
          else if (isActive) { markCls = 'border-[#0082BB] bg-[#0082BB] text-white'; labelCls = 'text-[#0082BB] font-semibold'; }
          return (
            <div key={stage} className="flex flex-1 flex-col items-center text-center">
              <div className="flex w-full items-center">
                <div className={`h-0.5 flex-1 ${i === 0 ? 'bg-transparent' : isDone || isActive ? 'bg-[#0082BB]' : 'bg-gray-200'}`} />
                <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${markCls}`}>
                  {mark}
                </div>
                <div className={`h-0.5 flex-1 ${i === journeyStages.length - 1 ? 'bg-transparent' : isDone ? 'bg-[#0082BB]' : 'bg-gray-200'}`} />
              </div>
              <div className={`mt-1 px-1 text-[11px] leading-tight ${labelCls}`}>
                {stage}
                {isActive && !submitted && <div className="text-[10px] text-gray-400">current step</div>}
                {isAwaiting && <div className="text-[10px] text-amber-500">awaiting decision</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CreditSubmissionPanel({ deal, onChanged, stageFlow, canEdit = true }: CreditPanelProps & { stageFlow?: string[]; canEdit?: boolean }) {
  const { toast } = useToast();
  const [checklist,  setChecklist]  = useState<CreditChecklistResponse | null>(null);
  // What the next stage actually is, and who owes which document. Fetched
  // rather than assumed - the flow is config-driven and per product, so the
  // page cannot know it without asking.
  const [nextStep, setNextStep] = useState<NextStep | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [docFiles,   setDocFiles]   = useState<Record<string, DealDocumentsResponse['files'][string]>>({});
  const [busyDoc,    setBusyDoc]    = useState<string | null>(null);
  const [otherLabel, setOtherLabel] = useState('');
  const [viewing,    setViewing]    = useState<{ docName: string; filename: string } | null>(null);
  const OTHER_PREFIX = 'Other: ';

  const reloadDocs = () => {
    listDealDocuments(deal.id)
      .then((d) => setDocFiles(d.files || {}))
      .catch(() => { /* leave as-is */ });
  };
  useEffect(() => { reloadDocs(); /* eslint-disable-next-line */ }, [deal.id]);

  const uploadFor = (doc: string) => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setBusyDoc(doc); setError(null);
      try {
        const buf = await f.arrayBuffer();
        let bin = '';
        const bytes = new Uint8Array(buf);
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        await uploadDealDocument(deal.id, doc, f.name, btoa(bin));
        reloadDocs();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Upload failed');
      } finally {
        setBusyDoc(null);
      }
    };
    inp.click();
  };

  const viewDoc = (doc: string) => {
    const meta = docFiles[doc];
    setViewing({ docName: doc, filename: meta?.filename || doc });
  };

  const removeDoc = async (doc: string) => {
    setBusyDoc(doc);
    try {
      await deleteDealDocument(deal.id, doc);
      reloadDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Remove failed');
    } finally {
      setBusyDoc(null);
    }
  };

  useEffect(() => {
    let alive = true;
    void fetchNextStep(deal.id).then((n) => { if (alive) setNextStep(n); })
      .catch(() => { /* label falls back to "Submit to next stage" */ });
    fetchCreditChecklist(deal.id)
      .then((c) => {
        if (!alive) return;
        setChecklist(c);
      })
      .catch(() => { /* checklist unavailable — panel stays hidden */ });
    return () => { alive = false; };
  }, [deal.id]);

  if (!checklist) return null;

  // Credit can return a deal (returned / info_requested). Phase L unlocks the
  // deal on those, so `already_submitted && !locked` means it's back with the
  // RM for more documents. Keep the upload form available so they can supply
  // documents until credit has everything, then resubmit.
  const reopenedForDocs = Boolean(checklist.already_submitted) && !deal.locked;

  // Already submitted and still locked — show the cross-link, no form.
  if (checklist.already_submitted && !reopenedForDocs) {
    return (
      <Card className="mt-6" stripe="accent">
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">Credit analysis</h3>
          <Badge tone="success" size="sm">Submitted</Badge>
        </Card.Header>
        <Card.Body>
          <CreditJourneyStepper checklist={checklist} stageFlow={stageFlow} />
          <p className="text-sm text-gray-700">
            {/* NAME THE STAGE IT IS ACTUALLY AT (ruling 2026-08-14, and again
                2026-08-17 from the pilot). This read "submitted to credit
                analysis" on a deal sitting at the BRANCH COMMITTEE - three
                stages before credit analysis - so the screen told the branch
                its case had left them when it had not.

                The stage is on the deal. Use it. */}
            This deal has moved on to{' '}
            <span className="font-medium">{deal.stage || 'the next stage'}</span>. It is now with
            Credit; you can follow its progress in the Case Journey.
          </p>
        </Card.Body>
      </Card>
    );
  }

  // Gate reasons that block the FINAL submit. Shown as a soft banner in the
  // upload UI below — they no longer hide the document upload. The CR
  // prerequisite is intentionally NOT listed here: the RM completes the CR on
  // its own tab, so surfacing it on the Documents tab is noise.
  const gateReasons: string[] = [];
  if (checklist.manager_validated === false) {
    gateReasons.push('This deal has not been validated by a manager. A manager must validate it (from their Manager Queue) before it can be submitted to credit.');
  }
  if (checklist.stage_ok === false && checklist.stage_required) {
    gateReasons.push(`Deal must be at stage "${checklist.stage_required}"${checklist.current_stage ? ` (currently "${checklist.current_stage}")` : ''}.`);
  }
  if ((checklist.committee_rejected ?? []).length > 0) {
    gateReasons.push(`Committee rejected: ${(checklist.committee_rejected ?? []).join(', ')}. The deal returns to the owner (appeal or close).`);
  }
  if ((checklist.committee_pending ?? []).length > 0) {
    gateReasons.push(`Committee decision outstanding: ${(checklist.committee_pending ?? []).join(', ')}.`);
  }

  // Hide the panel only when there is genuinely nothing for this viewer to do:
  // can't submit, no gates, no required documents and no CR path (e.g. a
  // non-owner, or a deal with no credit journey). Otherwise fall through and
  // show the upload UI so the owner can attach documents even before the deal
  // is submit-ready.
  if (!checklist.can_submit && gateReasons.length === 0
      && checklist.required.length === 0 && !checklist.cr_required) {
    return null;
  }

  const missing = checklist.required.filter((d) => !docFiles[d]);

  const onSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitDealToCredit(deal.id, checklist.required.filter((d) => docFiles[d]));
      toast({
        tone: 'success',
        message: `✓ Submitted to credit — application ${res.application_id}.`,
      });
      onChanged();
    } catch (e) {
      if (e instanceof ApiValidationError) setError(e.detail);
      else if (e instanceof AuthExpiredError) { /* handled globally */ }
      else setError('Submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="mt-6" stripe="accent">
      <Card.Header>
        <CreditJourneyStepper checklist={checklist} stageFlow={stageFlow} />
        <h3 className="text-sm font-semibold text-gray-900">{creditSubmitLabel(checklist, stageFlow)}</h3>
        <Badge tone="info" size="sm">document gate</Badge>
      </Card.Header>
      <Card.Body>
        {reopenedForDocs && (
          <div className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
            Credit returned this deal for more information. Supply the outstanding documents below, then resubmit.
          </div>
        )}
        {gateReasons.length > 0 && (
          <div className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
            <div className="font-medium">Submission is blocked until:</div>
            <ul className="list-disc pl-5">
              {gateReasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}
        <p className="text-xs text-gray-500 mb-3">
          {canEdit
            ? `Upload each required document. All required documents must be attached before the deal can be submitted${nextStep?.next_stage ? ` to ${nextStep.next_stage}` : ''}.`
            : 'Documents for this deal (managed by the owner). You have view access — open any attached document below.'}
        </p>
        <div className="space-y-2">
          {checklist.required.map((doc) => {
            const attached = docFiles[doc];
            return (
              <div key={doc} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className={attached ? 'text-green-700' : 'text-gray-800'}>
                    {attached ? '✓' : '○'} {doc}
                  </span>
                  {attached && (
                    <span className="text-xs text-gray-500">{attached.filename}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {attached && (
                    <button type="button" className="text-brand-primary hover:underline text-xs"
                      onClick={() => void viewDoc(doc)}>View</button>
                  )}
                  {canEdit && (
                    <button type="button" className="text-brand-primary hover:underline text-xs"
                      onClick={() => uploadFor(doc)} disabled={busyDoc === doc}>
                      {busyDoc === doc ? 'Uploading…' : attached ? 'Replace' : 'Upload'}
                    </button>
                  )}
                  {canEdit && attached && (
                    <button type="button" className="text-red-600 hover:underline text-xs"
                      onClick={() => void removeDoc(doc)} disabled={busyDoc === doc}>Remove</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {/* BO1: attached ad-hoc "Other" documents */}
        {Object.keys(docFiles).filter((k) => k.startsWith(OTHER_PREFIX)).length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-gray-600">Other documents</p>
            {Object.keys(docFiles).filter((k) => k.startsWith(OTHER_PREFIX)).map((k) => (
              <div key={k} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
                <span className="text-green-700">✓ {k.slice(OTHER_PREFIX.length)}</span>
                <div className="flex items-center gap-2">
                  <button type="button" className="text-brand-primary hover:underline text-xs"
                    onClick={() => void viewDoc(k)}>View</button>
                  {canEdit && (
                    <button type="button" className="text-red-600 hover:underline text-xs"
                      onClick={() => void removeDoc(k)} disabled={busyDoc === k}>Remove</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {/* BO1: add an ad-hoc "Other" document */}
        {canEdit && <div className="mt-3 flex items-center gap-2">
          <input
            type="text"
            className="flex-1 rounded border px-2 py-1.5 text-sm"
            placeholder="Other (describe) — e.g. board resolution, extra KYC…"
            value={otherLabel}
            onChange={(e) => setOtherLabel(e.target.value)}
          />
          <button
            type="button"
            className="rounded border px-3 py-1.5 text-sm text-brand-primary hover:bg-gray-50 disabled:opacity-50"
            disabled={!otherLabel.trim() || busyDoc !== null}
            onClick={() => { const label = otherLabel.trim(); if (label) { uploadFor(OTHER_PREFIX + label); setOtherLabel(''); } }}
          >
            Attach other
          </button>
        </div>}
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {!error && missing.length > 0 && (
          <div className="mt-3 text-xs text-amber-600">
            {missing.length} document{missing.length === 1 ? '' : 's'} still required.
          </div>
        )}
        {canEdit ? (
          <div className="mt-4 flex items-center justify-end gap-3">
            {!checklist.can_submit && (
              <span className="text-xs text-gray-500">Submission opens once all prerequisites are complete.</span>
            )}
            {/* THE BUTTON NAMES THE REAL DESTINATION (ruling 2026-08-12). The
                advance was always right - one stage, config-driven - but the
                label named a step three transitions away, which teaches people
                the wrong shape of their own process.

                And it is no longer disabled by outstanding paperwork: only
                MANDATORY documents block now, so the deal can move while the
                rest is still being gathered. */}
            <Button
              onClick={() => void onSubmit()}
              loading={submitting}
              disabled={(nextStep?.blocking?.length ?? 0) > 0 || !checklist.can_submit}
            >
              {nextStep?.submit_label ?? 'Submit to next stage'}
            </Button>
          </div>
        ) : (
          <div className="mt-4 text-xs text-gray-400">Submission is managed by the deal owner.</div>
        )}
        {viewing && (
          <DocumentViewerModal
            dealId={deal.id}
            docName={viewing.docName}
            filename={viewing.filename}
            canDownload
            onClose={() => setViewing(null)}
          />
        )}
      </Card.Body>
    </Card>
  );
}


// ── Action panel: Advance Stage ─────────────────────────────────────────

/**
 * Shared props for action panels (Advance + RequestCancel).
 *
 * δ1 (2026-06-12): onSuccess accepts an optional meta arg. Advance
 * passes { targetStage } so the parent can render a stage-aware toast
 * (e.g. "Loan application created" when targetStage was 'Compliance').
 * RequestCancelPanel calls onSuccess() with no args — backward-compatible
 * because the meta arg is optional.
 */
interface ActionPanelProps {
  deal:      PipelineDeal;
  mutations: ReturnType<typeof usePipelineDealMutations>;
  onSuccess: (meta?: { targetStage?: string }) => void;
  /** This deal's product-class stage flow (B17). When present, the advance
   *  dropdown follows it instead of the flat ADVANCE_TARGET_STAGES list. */
  stageFlow?: string[];
}

function AdvancePanel({ deal, mutations, onSuccess, stageFlow }: ActionPanelProps) {
  // B17: follow this deal's product-class flow (loan vs deposit vs …) from the
  // detail response; fall back to the flat list only if config didn't load.
  const stages = stageFlow && stageFlow.length > 0 ? stageFlow : ADVANCE_TARGET_STAGES;
  // Default to the next plausible stage if current is in the flow.
  const currentIndex = stages.indexOf(deal.stage);
  const defaultTarget = currentIndex >= 0 && currentIndex < stages.length - 1
    ? stages[currentIndex + 1]
    : stages[0];

  const [targetStage, setTargetStage] = useState<string>(defaultTarget);
  const [note,        setNote]        = useState('');
  const [error,       setError]       = useState<string | null>(null);

  const onSubmit = async () => {
    setError(null);
    const result = await mutations.advance(deal.id, {
      target_stage: targetStage,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      onSuccess({ targetStage });
      setNote('');
    } else {
      setError(result.error);
    }
  };

  // v10.588: lock manual advance at the credit-assessment gate. The stage only
  // progresses via the document-gated "Submit to Credit Analysis" panel below
  // (which the backend blocks until every required document is attached). Once
  // submitted (the deal carries an lms_application_id), this unlocks.
  const isCreditGate = /credit/i.test(deal.stage) && /(assess|analys)/i.test(deal.stage);
  const submittedToCredit = !!deal.lms_application_id;
  if (isCreditGate && !submittedToCredit) {
    return (
      <Card className="mt-6" stripe="secondary">
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">Advance stage</h3>
          <Badge tone="warning" size="sm">locked at Credit Assessment</Badge>
        </Card.Header>
        <Card.Body>
          <p className="text-sm text-gray-600">
            This deal is at <span className="font-medium">{deal.stage}</span>. The stage can&apos;t be
            advanced manually from here — complete the document checklist and use the{' '}
            <span className="font-medium">Submit to Credit Analysis</span> panel below. Submission is
            blocked until every required document is attached, and it moves the deal forward
            automatically once it succeeds.
          </p>
        </Card.Body>
      </Card>
    );
  }

  return (
    <Card className="mt-6" stripe="primary">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Advance stage</h3>
        <Badge tone="info" size="sm">can_advance_stage</Badge>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">
              Target stage
            </label>
            <select
              value={targetStage}
              onChange={(e) => setTargetStage(e.target.value)}
              disabled={mutations.loading}
              className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-base text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
            >
              {stages.map((s) => (
                <option key={s} value={s} disabled={s === deal.stage}>
                  {s}{s === deal.stage ? ' (current)' : ''}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Current: {deal.stage}. Server validates the transition.
            </p>
          </div>
          <Input
            label="Note (optional)"
            placeholder="Context for the change"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={mutations.loading}
            helper="Recorded on the deal's audit trail."
          />
        </div>
        {error && (
          <div className="mt-4 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
      </Card.Body>
      <Card.Footer>
        <Button
          variant="primary"
          size="md"
          onClick={() => void onSubmit()}
          loading={mutations.loading}
          disabled={!targetStage || targetStage === deal.stage}
        >
          Advance to {targetStage}
        </Button>
      </Card.Footer>
    </Card>
  );
}


// ── Action panel: Request Cancellation ──────────────────────────────────

function RequestCancelPanel({ deal, mutations, onSuccess }: ActionPanelProps) {
  const [reason, setReason] = useState('');
  const [error,  setError]  = useState<string | null>(null);

  const MIN_REASON_LEN = 5;
  const tooShort = reason.trim().length < MIN_REASON_LEN;

  const onSubmit = async () => {
    setError(null);
    const result = await mutations.requestCancel(deal.id, {
      reason: reason.trim(),
    });
    if (result.ok) {
      onSuccess();
      setReason('');
    } else {
      setError(result.error);
    }
  };

  return (
    <Card className="mt-6" stripe="accent">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Request cancellation</h3>
        <Badge tone="warning" size="sm">can_request_cancel</Badge>
      </Card.Header>
      <Card.Body>
        <Input
          label={`Reason (min ${MIN_REASON_LEN} chars)`}
          placeholder="e.g. duplicate of D0042, lost to NCBA"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={mutations.loading}
          helper={`A manager will see this reason when deciding whether to approve.`}
          error={
            reason.length > 0 && tooShort
              ? `Reason is ${reason.trim().length} character${reason.trim().length === 1 ? '' : 's'} — need at least ${MIN_REASON_LEN}.`
              : undefined
          }
        />
        {error && (
          <div className="mt-4 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
            {error}
          </div>
        )}
        <p className="text-xs text-gray-500 mt-3">
          This sends the request to your manager's queue. The deal stays
          active until they approve or reject. You can't request again
          while one is pending.
        </p>
      </Card.Body>
      <Card.Footer>
        <Button
          variant="danger"
          size="md"
          onClick={() => void onSubmit()}
          loading={mutations.loading}
          disabled={tooShort}
        >
          Submit cancellation request
        </Button>
      </Card.Footer>
    </Card>
  );
}


/**
 * ReferPanel — refer this existing deal to a chosen recipient (A1).
 * Self-contained: uses the StaffPicker (segment → person) + a note, posts to
 * /api/pipeline/deals/{id}/refer, then asks the parent to reload the deal so the
 * new "Referral: pending" badge appears.
 */
function ReferPanel({ deal, onSuccess }: { deal: PipelineDeal; onSuccess: () => void }) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<StaffMember | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    if (!picked) {
      toast({ tone: 'warning', message: 'Select a recipient first.' });
      return;
    }
    setBusy(true);
    try {
      await referExistingDeal(deal.id, {
        referred_to_code: picked.staff_code,
        referred_to_name: picked.name,
        referral_note: note.trim(),
      });
      toast({ tone: 'success', message: `Referred to ${displayName(picked.name)}. They'll need to accept it.` });
      setOpen(false); setPicked(null); setNote('');
      onSuccess();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Referral failed.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-6" stripe="primary">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Refer deal</h3>
        {deal.referral_status === 'declined' && (
          <Badge tone="warning" size="sm">previously returned</Badge>
        )}
      </Card.Header>
      <Card.Body>
        {!open ? (
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-gray-600">
              Hand this deal to a colleague — pick their segment, then the person. They
              progress it once they accept; you keep following it.
            </p>
            <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
              Refer to someone…
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <StaffPicker value={picked} onChange={setPicked} />
            <Input
              label="Note (optional)"
              placeholder="Why you're referring this deal"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={busy}
            />
            <div className="flex gap-2">
              <Button variant="primary" size="sm" onClick={() => void onSubmit()}
                loading={busy} disabled={!picked}>
                Refer deal
              </Button>
              <Button variant="ghost" size="sm" disabled={busy}
                onClick={() => { setOpen(false); setPicked(null); setNote(''); }}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}

// ── Deal Credit Report (4b-3): CR originates at the branch, on the deal ──
function ForwardingMemoCard({ dealId, canEdit }: { dealId: string; canEdit: boolean }) {
  const { toast } = useToast();
  const [to, setTo] = useState('Bank Credit Committee');
  const [recommendation, setRecommendation] = useState('');
  const [roName, setRoName] = useState('');
  const [bmName, setBmName] = useState('');
  const [busy, setBusy] = useState(false);

  const printMemo = () => {
    const esc = escapeHtml;
    const body = `
      <table>
        <tr><th style="width:32%">To</th><td>${esc(to)}</td></tr>
        <tr><th>Re</th><td>Deal ${esc(dealId)}</td></tr>
        <tr><th>Forwarding recommendation</th><td>${esc(recommendation) || '\u2014'}</td></tr>
      </table>
      <h2>Sign-off</h2>
      <table>
        <tr><th style="width:32%">Relationship Officer</th><td>${esc(roName) || '________________'}&nbsp;&nbsp;Signature: ____________&nbsp;&nbsp;Date: __________</td></tr>
        <tr><th>Branch Manager</th><td>${esc(bmName) || '________________'}&nbsp;&nbsp;Signature: ____________&nbsp;&nbsp;Date: __________</td></tr>
      </table>
      <h2>Branch Credit Committee</h2>
      <table>
        <tr><td>Name: ________________&nbsp;&nbsp;Signature: ____________&nbsp;&nbsp;Date: __________</td></tr>
        <tr><td>Name: ________________&nbsp;&nbsp;Signature: ____________&nbsp;&nbsp;Date: __________</td></tr>
      </table>
      <h2>Bank Credit Committee \u2014 Approver&apos;s Comments</h2>
      <table><tr><td style="height:80px">&nbsp;</td></tr></table>
    `;
    const head = `<div class="head"><h1>Forwarding Memo \u2014 ${esc(dealId)}</h1><span class="muted">printed ${esc(new Date().toLocaleString())}</span></div>`;
    printDocument(`Forwarding Memo ${dealId}`, head + body);
  };

  const uploadSigned = () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setBusy(true);
      try {
        const buf = await f.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        await uploadDealDocument(dealId, 'Forwarding Memo', f.name, btoa(bin));
        toast({ tone: 'success', message: 'Signed Forwarding Memo uploaded.' });
      } catch (e) {
        toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Upload failed.' });
      } finally { setBusy(false); }
    };
    inp.click();
  };

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Forwarding Memo</h2>
        <div className="flex items-center gap-2">
          <button className="text-sm text-brand-primary" onClick={printMemo}>Print</button>
          {canEdit && (
            <button className="text-sm text-brand-primary disabled:opacity-50" onClick={uploadSigned} disabled={busy}>Upload signed</button>
          )}
        </div>
      </Card.Header>
      <Card.Body>
        <p className="mb-4 text-xs text-gray-500">
          Complete after the Branch Credit Committee gives its input, then Print for wet
          signatures and Upload the signed copy. The signed copy travels with the case.
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-gray-600">To</label>
            <input value={to} onChange={(e) => setTo(e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-600">Relationship Officer</label>
            <input value={roName} onChange={(e) => setRoName(e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" />
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-gray-600">Forwarding recommendation</label>
            <textarea value={recommendation} onChange={(e) => setRecommendation(e.target.value)} rows={3} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-600">Branch Manager</label>
            <input value={bmName} onChange={(e) => setBmName(e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" />
          </div>
        </div>
      </Card.Body>
    </Card>
  );
}

function DealCreditReportCard({ dealId, canEdit }: { dealId: string; canEdit: boolean }) {
  const { toast } = useToast();
  const [cr, setCr] = useState<CrView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setCr(await getDealCr(dealId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [dealId]);

  const valueFor = (key: string): string => {
    if (key in edits) return edits[key];
    const v = cr?.values?.[key];
    return v === undefined || v === null ? '' : String(v);
  };

  const save = async (completed: boolean) => {
    setBusy(true);
    try {
      await saveDealCr(dealId, { values: edits, completed });
      setEdits({});
      toast({ tone: 'success', message: completed ? 'Transaction Memo marked complete.' : 'Transaction Memo saved.' });
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

  const printTm = () => {
    const secs = (cr.template?.sections ?? []).map((sec) => {
      const tableField = (sec.fields ?? []).find((f) => f.type === 'table');
      if (tableField) {
        return `<h2>${escapeHtml(sec.title)}</h2>${facilitiesToPrintHtml(valueFor(tableField.key))}`;
      }
      const rows = (sec.fields ?? []).map((f) =>
        `<tr><th style="width:42%">${escapeHtml(f.label)}</th><td>${escapeHtml(valueFor(f.key)) || '—'}</td></tr>`).join('');
      return `<h2>${escapeHtml(sec.title)}</h2><table>${rows}</table>`;
    }).join('');
    const head = `<div class="head"><h1>Transaction Memo — ${escapeHtml(dealId)}</h1><span class="muted">${cr.completed ? 'Complete' : 'Draft'} · printed ${escapeHtml(new Date().toLocaleString())}</span></div>`;
    printDocument(`Transaction Memo ${dealId}`, head + secs);
  };

  const uploadSignedTm = () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setBusy(true);
      try {
        const buf = await f.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        await uploadDealDocument(dealId, 'Transaction Memo', f.name, btoa(bin));
        toast({ tone: 'success', message: 'Signed Transaction Memo uploaded.' });
      } catch (e) {
        toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Upload failed.' });
      } finally { setBusy(false); }
    };
    inp.click();
  };

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Transaction Memo (TM)</h2>
        <div className="flex items-center gap-2">
          {cr.completed && <Badge tone="success">Complete</Badge>}
          {!cr.cbs_available && <span className="text-xs text-gray-400">CBS data unavailable — fill manually</span>}
          <button className="text-sm text-brand-primary" onClick={printTm}>Print</button>
          {canEdit && (
            <button className="text-sm text-brand-primary disabled:opacity-50" onClick={uploadSignedTm} disabled={busy}>Upload signed</button>
          )}
        </div>
      </Card.Header>
      <Card.Body>
          <p className="text-xs text-gray-500 mb-4">
            Complete the Transaction Memo at the branch (after documents). Blue = CBS, grey = deal;
            both editable. Plain fields are for the deal owner.
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
                    if (f.type === 'table') {
                      return (
                        <div key={f.key} className="md:col-span-2">
                          <label className="mb-1 block text-xs text-gray-600">{f.label}</label>
                          <FacilitiesTable value={val} onChange={(v) => setEdits((p) => ({ ...p, [f.key]: v }))} disabled={!canEdit || busy} />
                        </div>
                      );
                    }
                    const isLong = ['strengths', 'weaknesses', 'mitigants', 'rm_recommendation', 'conditions', 'purpose', 'background', 'statements', 'crb_arrears', 'risk_summary', 'other_bank_facilities', 'other_bank_securities', 'dsr_computation', 'policy_exception', 'account_conduct', 'repayment_source'].includes(f.key);
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
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => void save(false)} disabled={busy}>Save draft</Button>
              <Button onClick={() => void save(true)} disabled={busy}>Mark complete</Button>
            </div>
          )}
        </Card.Body>
    </Card>
  );
}

// ── Committee Journey capture (4b-4): record each gate's decision on the deal ──
function CommitteeJourneyCard({ dealId, canEdit }: { dealId: string; canEdit: boolean }) {
  const { toast } = useToast();
  const [data, setData] = useState<CommitteeRecordsResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [outcomeDraft, setOutcomeDraft] = useState<Record<string, string>>({});
  const [appealReason, setAppealReason] = useState<Record<string, string>>({});
  const doAppeal = async (code: string) => {
    const reason = (appealReason[code] ?? '').trim();
    if (!reason) { toast({ tone: 'danger', message: 'Enter an appeal reason.' }); return; }
    setBusy(code);
    try {
      const r = await appealCommitteeDecision(dealId, code, reason);
      toast({ tone: 'success', message: r.message });
      setAppealReason((p) => ({ ...p, [code]: '' }));
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Appeal failed' });
    } finally { setBusy(null); }
  };
  const doCloseLost = async (code: string) => {
    setBusy(code);
    try {
      await closeDealAsLost(dealId, `Committee ${code} rejected`);
      toast({ tone: 'success', message: 'Deal closed as Lost.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Close failed' });
    } finally { setBusy(null); }
  };

  const load = async () => {
    try { setData(await getDealCommitteeRecords(dealId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [dealId]);

  // ---- HOOKS BEFORE THE EARLY RETURN ------------------------------------
  // These three were declared AFTER `if (!data ...) return null` - so on a
  // render where data was absent React saw six hooks and on the next it saw
  // nine. That is the Rules of Hooks violation, and it does not fail quietly:
  // it throws, and the page renders blank.
  //
  //     Warning: React has detected a change in the order of Hooks called by
  //     CommitteeJourneyCard ... 7. undefined -> useState
  //
  // Every hook must run on every render, so they belong above any return.
  const [myVote, setMyVote] = useState<Record<string, string>>({});
  const [myDocs, setMyDocs] = useState<Record<string, boolean>>({});
  const [myComment, setMyComment] = useState<Record<string, string>>({});

  if (!data || data.cr_only) return null;



  // ── YOUR OWN VOTE, NOT THE WHOLE COMMITTEE'S ─────────────────────────────
  // This used to post every member's row at once, so one member pressing the
  // button submitted a committee's worth of votes - one vote, below quorum,
  // DEFERRED, case closed before anybody else had seen it. Each member now
  // records their own view from their own login and the case stays open until
  // enough of them have.

  const castMyVote = async (gate: CommitteeGate) => {
    const vote = myVote[gate.code];
    if (!vote) { toast({ tone: 'danger', message: 'Pick your vote.' }); return; }
    if (vote === 'YES' && !myDocs[gate.code]) {
      toast({ tone: 'danger', message: 'Confirm the documentation was checked before voting YES.' });
      return;
    }
    setBusy(gate.code);
    try {
      const r = await castCommitteeVote(dealId, gate.code, {
        vote,
        documents_validated: !!myDocs[gate.code],
        comment: myComment[gate.code] ?? '',
      });
      // THE MESSAGE SAYS WHAT ACTUALLY HAPPENED. "Decision recorded" after one
      // vote is what made people think the case had been decided.
      toast({
        tone: 'success',
        message: r.decided
          ? `Committee decided: ${r.outcome === 'APPROVED' ? 'recommended'
              : r.outcome === 'REJECTED' ? 'not recommended' : 'deferred'}.`
          : `Your vote is in — ${r.votes_cast} of ${r.quorum}.`
            + (r.awaiting.length ? ` Awaiting ${r.awaiting.join(', ')}.` : ''),
      });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' });
    } finally { setBusy(null); }
  };

  const recordSingle = async (gate: CommitteeGate) => {
    const outcome = outcomeDraft[gate.code];
    if (!outcome) { toast({ tone: 'danger', message: 'Pick an outcome.' }); return; }
    setBusy(gate.code);
    try {
      await recordDealCommitteeDecision(dealId, { code: gate.code, outcome });
      toast({ tone: 'success', message: `${gate.code} decision recorded.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' });
    } finally { setBusy(null); }
  };

  const outcomeTone = (o: string) => (o === 'APPROVED' ? 'success' : o === 'REJECTED' ? 'danger' : 'warning');
  // The same stored values, read back as what the committee actually did.
  const outcomeLabel = (o: string) => (
    o === 'APPROVED' ? 'Recommended'
      : o === 'REJECTED' ? 'Not recommended'
        : o === 'DEFERRED' ? 'Deferred' : o);

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Credit Committee Journey</h2>
        <div className="flex items-center gap-2">
          {/* THE PAPERS, ONE CLICK AWAY (ruling 2026-08-13: "they need to be
              able to view documentation, otherwise how do they know what they
              are approving"). A committee member reaching this card from their
              queue has no reason to know the documents live under another tab
              further up the page - so it is named here, where the decision is
              actually made. */}
          <button
            type="button"
            onClick={() => window.dispatchEvent(
              new CustomEvent('workbench:open-tab', { detail: 'documents' }))}
            className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            View documentation
          </button>
          <Badge tone="info" size="sm">{data.gates.length} gate{data.gates.length === 1 ? '' : 's'}</Badge>
        </div>
      </Card.Header>
      <Card.Body>
        <div className="space-y-4">
          {data.gates.map((gate) => (
            <div key={gate.code} className="rounded border p-3">
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <span className="text-sm font-semibold">{gate.code} — {gate.name}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {gate.recording_mode === 'voting' ? `voting · ${gate.voting_rule}` : 'single record'}
                  </span>
                </div>
                {gate.record && <Badge tone={outcomeTone(gate.record.outcome)} size="sm">{outcomeLabel(gate.record.outcome)}</Badge>}
              </div>

              {gate.record ? (
                <div className="text-xs text-gray-600">
                  Recorded by {gate.record.recorded_by} on {gate.record.recorded_at}.
                  {gate.record.mode === 'voting' && gate.record.votes.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {gate.record.votes.map((v, i) => (
                        <li key={i}>
                          {v.name} ({v.role}): {v.vote}
                          {v.documents_validated ? ' · ✓ docs validated' : ''}
                          {v.comment ? ` — ${v.comment}` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                  {gate.record.outcome === 'REJECTED' && canEdit && (
                    <div className="mt-3 rounded bg-red-50 p-2">
                      <p className="mb-2 font-medium text-red-700">Rejected — appeal or close as lost.</p>
                      <textarea className="mb-2 w-full rounded border px-2 py-1 text-xs" rows={2}
                        placeholder="Appeal reason / justification"
                        value={appealReason[gate.code] ?? ''}
                        onChange={(e) => setAppealReason((p) => ({ ...p, [gate.code]: e.target.value }))} />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => void doAppeal(gate.code)} disabled={busy === gate.code}>
                          {busy === gate.code ? 'Working…' : 'Appeal (re-open)'}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void doCloseLost(gate.code)} disabled={busy === gate.code}>
                          Close as Lost
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (gate.can_vote ?? canEdit) ? (
                /* CAN THIS PERSON VOTE, not can they edit the deal. canEdit
                   means owner or admin; a committee member is neither, so the
                   voting bench never rendered for the one person who needed
                   it. The server answers from the roster, and falls back to
                   canEdit for a build where the gate does not carry it. */
                gate.recording_mode === 'voting' ? (
                  <div>
                    {(gate.members ?? []).length === 0 && (
                      <p className="mb-2 text-xs text-amber-600">No members configured for this committee — add them in Credit Committees admin.</p>
                    )}

                    {/* ── YOUR VOTE ────────────────────────────────────────
                        One member, one vote, from their own login. This used
                        to be a row per member with a single "Record votes"
                        button, so whoever pressed it submitted the whole
                        committee - and one vote below quorum closed the case
                        as DEFERRED before anybody else had seen it.

                        Who is voting comes from the session, not a name typed
                        here, so it cannot be misattributed. */}
                    <div className="rounded-md border border-gray-200 p-3">
                      <div className="mb-2 text-xs font-semibold text-gray-700">
                        Your vote
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <select
                          className="rounded border px-2 py-1 text-xs"
                          value={myVote[gate.code] ?? ''}
                          onChange={(e) => setMyVote((m) => ({ ...m, [gate.code]: e.target.value }))}
                        >
                          <option value="">— your view —</option>
                          <option value="YES">Recommend</option>
                          <option value="NO">Do not recommend</option>
                          <option value="ABSTAIN">Abstain</option>
                          <option value="RECUSED">Recuse myself</option>
                        </select>
                        <label className="flex items-center gap-1.5 text-xs text-gray-700">
                          <input
                            type="checkbox"
                            checked={!!myDocs[gate.code]}
                            onChange={(e) => setMyDocs((m) => ({ ...m, [gate.code]: e.target.checked }))}
                          />
                          Documentation checked
                        </label>
                      </div>
                      <input
                        className="mt-2 w-full rounded border px-2 py-1 text-xs"
                        placeholder="Comment (optional)"
                        value={myComment[gate.code] ?? ''}
                        onChange={(e) => setMyComment((m) => ({ ...m, [gate.code]: e.target.value }))}
                      />
                      <div className="mt-2 flex items-center justify-between gap-2">
                        {/* WHO HAS ALREADY VOTED, so a member can see whether
                            the committee is waiting on them or on somebody
                            else. */}
                        <span className="text-[11px] text-gray-500">
                          {(gate.votes_cast ?? 0) > 0
                            ? `${gate.votes_cast} of ${gate.quorum ?? 2} voted`
                            : 'No votes yet'}
                          {(gate.awaiting ?? []).length > 0
                            ? ` · awaiting ${(gate.awaiting ?? []).join(', ')}`
                            : ''}
                        </span>
                        <Button size="sm" onClick={() => void castMyVote(gate)} disabled={busy === gate.code}>
                          {busy === gate.code ? 'Submitting…' : 'Submit my vote'}
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <select className="rounded border px-2 py-1.5 text-sm"
                      value={outcomeDraft[gate.code] ?? ''}
                      onChange={(e) => setOutcomeDraft((p) => ({ ...p, [gate.code]: e.target.value }))}>
                      {/* A COMMITTEE RECOMMENDS; the approval comes from
                          credit (ruling 2026-08-13). The stored values stay
                          APPROVED / REJECTED / DEFERRED because the gate, the
                          journey and the reports all read them - renaming the
                          data would break those for a wording change. What a
                          person reads now matches what they are actually
                          doing. */}
                      <option value="">— recommendation —</option>
                      <option value="APPROVED">Recommend</option>
                      <option value="REJECTED">Do not recommend</option>
                      <option value="DEFERRED">Defer — more information needed</option>
                    </select>
                    <Button size="sm" onClick={() => void recordSingle(gate)} disabled={busy === gate.code}>
                      {busy === gate.code ? 'Recording…' : 'Record recommendation'}
                    </Button>
                  </div>
                )
              ) : (
                <p className="text-xs text-gray-400">Not yet decided.</p>
              )}
            </div>
          ))}
        </div>
      </Card.Body>
    </Card>
  );
}


/* ─────────── The rate on a term deposit ───────────
   RULING (2026-08-19): "the owner of the deal indicates the rate the customer
   wants ... if they counter it goes back to the branch for discussion with the
   customer, and if the customer is agreeable then they can accept the counter
   WITHOUT returning it back to treasury."

   So the branch has two moments here and they are different in kind: asking,
   and then closing. Between them the case belongs to treasury and there is
   nothing to press - which the panel says, rather than showing disabled
   buttons that invite a click. */
function RateRequestPanel({ deal, canEdit, onChanged }: {
  deal: PipelineDeal; canEdit: boolean; onChanged: () => void;
}) {
  const { toast } = useToast();
  const [state, setState] = useState<RateRequestState | null>(null);
  const [busy, setBusy] = useState(false);
  const [amount, setAmount] = useState(String(deal.deal_value ?? ''));
  const [tenor, setTenor] = useState('');
  const [asked, setAsked] = useState('');
  const [why, setWhy] = useState('');

  const load = () => {
    fetchRateState(deal.id).then(setState).catch(() => setState(null));
  };
  useEffect(load, [deal.id]);

  const rr = (state?.rate_request ?? {}) as Record<string, unknown>;
  const status = String(rr.status ?? '');
  const offered = rr.offered_rate as number | undefined;
  const requested = rr.requested_rate as number | undefined;

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); toast({ tone: 'success', message: ok }); load(); onChanged(); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' }); }
    finally { setBusy(false); }
  };

  return (
    <Card>
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">Rate</h3>
      </Card.Header>
      <Card.Body>
        {!status && (
          <>
            <p className="mb-3 text-sm text-gray-700">
              Ask treasury for a rate. The whole desk sees it, and whoever picks
              it up either approves what you asked or comes back with their own.
            </p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-gray-700">Amount (KES)</label>
                <input type="number" value={amount} disabled={!canEdit || busy}
                       onChange={(e) => setAmount(e.target.value)}
                       className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700">Tenor (days)</label>
                <input type="number" value={tenor} disabled={!canEdit || busy}
                       onChange={(e) => setTenor(e.target.value)}
                       className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700">Rate the customer wants (%)</label>
                <input type="number" step="0.01" value={asked} disabled={!canEdit || busy}
                       onChange={(e) => setAsked(e.target.value)}
                       className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="mt-3">
              <Button size="sm" disabled={!canEdit || busy}
                      onClick={() => void run(
                        () => requestRate(deal.id, {
                          amount: Number(amount), tenor_days: tenor,
                          requested_rate: Number(asked) }),
                        'Sent to the treasury desk.')}>
                Ask treasury
              </Button>
            </div>
          </>
        )}

        {status === 'awaiting_treasury' && (
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3">
            <p className="text-sm text-gray-800">
              With treasury — asked {Number(requested).toFixed(2)}% for {String(rr.tenor)} days.
            </p>
            <p className="mt-1 text-xs text-gray-600">
              Any dealer on the desk can price it. Nothing to do here until they do.
            </p>
          </div>
        )}

        {status === 'countered' && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
            <p className="text-sm text-gray-900">
              Treasury came back at <span className="font-semibold">{Number(offered).toFixed(2)}%</span>
              {' '}against the {Number(requested).toFixed(2)}% asked.
            </p>
            {Boolean(rr.note) && (
              <p className="mt-1 text-xs text-gray-700">{String(rr.note)}</p>
            )}
            <p className="mt-2 text-xs text-gray-600">
              Put it to the customer. If they take it, close it here — it does
              not go back to treasury.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <Button size="sm" disabled={!canEdit || busy}
                      onClick={() => void run(() => acceptCounterRate(deal.id, {}),
                        'Accepted — booked and closed.')}>
                The customer accepts {Number(offered).toFixed(2)}%
              </Button>
              <div className="min-w-[14rem] flex-1">
                <label className="text-xs font-medium text-gray-700">
                  Or why they did not
                </label>
                <input type="text" value={why} onChange={(e) => setWhy(e.target.value)}
                       placeholder="Placed elsewhere at 11%…"
                       className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm" />
              </div>
              <Button size="sm" variant="secondary" disabled={!canEdit || busy}
                      onClick={() => void run(
                        () => declineCounterRate(deal.id, { reason: why.trim() }),
                        'Closed as lost. Treasury will see it.')}>
                No agreement
              </Button>
            </div>
          </div>
        )}

        {['approved', 'accepted_at_counter', 'declined_at_counter'].includes(status) && (
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-sm text-gray-900">
              {status === 'declined_at_counter'
                ? `Lost at ${Number(offered).toFixed(2)}%.`
                : `Won at ${Number(offered).toFixed(2)}%.`}
              {rr.priced_by_name ? ` Priced by ${String(rr.priced_by_name)}.` : ''}
            </p>
          </div>
        )}

        {(state?.history ?? []).length > 0 && (
          <div className="mt-4 border-t pt-3">
            <p className="mb-1 text-xs font-medium text-gray-700">What happened</p>
            {(state?.history ?? []).map((h, i) => (
              <div key={i} className="flex justify-between py-0.5 text-xs text-gray-700">
                <span>
                  {h.what}
                  {h.rate !== undefined ? ` at ${Number(h.rate).toFixed(2)}%` : ''}
                  {h.by ? ` — ${h.by}` : ''}
                </span>
                <span className="text-gray-400">{String(h.at ?? '').slice(0, 16)}</span>
              </div>
            ))}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
