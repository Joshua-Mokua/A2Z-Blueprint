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

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useToast } from '@/components/Toast';
import { fetchPipelineDealDetail, fetchCreditChecklist, submitDealToCredit, referExistingDeal, fetchDealSla, ApiValidationError, AuthExpiredError, type StaffMember, type SlaViolation } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import { PermissionBadges } from '@/components/PermissionBadges';
import { StaffPicker } from '@/components/StaffPicker';
import {
  stageTone,
  ADVANCE_TARGET_STAGES,
  type PipelineDeal,
  type DealPermissions,
  type CreditChecklistResponse,
} from '@/types/pipeline';


// ── Format helpers (mirroring Pipeline.tsx) ─────────────────────────────

function formatValue(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  if (n >= 1e9) return `${symbol} ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  // Backend sometimes returns ISO datetime, sometimes just date.
  // Take the first 10 chars (YYYY-MM-DD) which works for either.
  return s.slice(0, 10);
}


// ── Detail page component ───────────────────────────────────────────────

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

  const currency = branding?.currency_symbol ?? '';

  return (
    <DetailFrame title={`Deal ${deal.id}`}>
      {/* Top action bar */}
      <div className="flex items-center justify-between mt-8 mb-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
          ← Back to pipeline
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void reloadDeal()}
          loading={loading}
        >
          Refresh
        </Button>
      </div>

      {/* Primary identity card */}
      <Card stripe="primary">
        <Card.Header>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-lg font-semibold text-brand-secondary">
              {deal.client_name || '—'}
            </h2>
            <Badge tone={stageTone(deal.stage)} size="md">{deal.stage}</Badge>
            {deal.draft && <Badge tone="warning" size="sm">Draft</Badge>}
            {deal.cancel_requested && !deal.cancel_approved && (
              <Badge tone="warning" size="sm">Cancel requested</Badge>
            )}
            {deal.manager_validated && (
              <Badge tone="success" size="sm">Validated</Badge>
            )}
            {deal.referral_status && (
              <Badge
                tone={deal.referral_status === 'accepted' ? 'success'
                  : deal.referral_status === 'declined' ? 'warning' : 'info'}
                size="sm"
              >
                Referral: {deal.referral_status}
              </Badge>
            )}
            {/* δ1 (2026-06-12): LMS cross-link when backend has created
                a loan application from this deal (typically after advancing
                to Compliance). Mirrors the Credit Admin → LMS cross-link
                pattern from β6 so users can trace a deal's downstream lifecycle. */}
            {deal.lms_application_id && (
              <button
                onClick={() => navigate(`/lms/${encodeURIComponent(deal.lms_application_id!)}`)}
                className="text-xs text-brand-primary hover:underline font-medium"
              >
                View Loan Application →
              </button>
            )}
          </div>
          <span className="font-mono text-xs text-gray-500">{deal.id}</span>
        </Card.Header>
        <Card.Body>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <DetailField label="Product type" value={deal.product_type ?? deal.product} />
            <DetailField label="Pipeline category" value={deal.pipeline_category ?? deal.deal_category} />
            <DetailField label="Source" value={deal.source} />
            <DetailField label="Client type" value={deal.client_type} />
            <DetailField label="Deal value" value={formatValue(deal.amount_kes ?? deal.deal_value, currency)} />
            <DetailField label="Probability" value={
              typeof deal.probability === 'number'
                ? `${Math.round(deal.probability * 100)}%`
                : '—'
            } />
            <DetailField label="Currency" value={deal.currency ?? currency} />
            <DetailField label="Expected close" value={formatDate(deal.expected_close)} />
            <DetailField label="Next action" value={deal.next_action} />
            <DetailField label="Next action date" value={formatDate(deal.next_action_date)} />
            <DetailField label="Owner" value={deal.staff_name} sub={deal.staff_code} />
            {deal.backup_staff_codes && deal.backup_staff_codes.length > 0 && (
              <DetailField label="Backup staff" value={deal.backup_staff_codes.join(', ')} />
            )}
          </div>
        </Card.Body>
      </Card>

      {/* SLA status panel (Phase 4 #81) — the deal's own clock, due-soon, breach */}
      {sla && sla.state && (
        <Card className="mt-6" stripe={sla.state === 'breached' ? 'accent' : 'primary'}>
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
      )}

      {/* Permissions panel — shows what server says you can do */}
      <Card className="mt-6">
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">
            Your permissions on this deal
          </h3>
          <span className="text-xs text-gray-400">α7 server-resolved</span>
        </Card.Header>
        <Card.Body>
          <PermissionBadges permissions={permissions ?? undefined} showAll />
          <p className="text-xs text-gray-500 mt-3">
            Each permission reflects your relationship to this deal
            (owner / backup / manager-in-scope) combined with its state
            (terminal stages, pending cancellation, validation status).
            The buttons below appear only when the corresponding permission is true.
          </p>
        </Card.Body>
      </Card>

      {/* Cancellation-pending notice */}
      {deal.cancel_requested && !deal.cancel_approved && (
        <Card className="mt-6" stripe="accent">
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

      {/* Action: advance — gated by α7 can_advance_stage */}
      {permissions?.can_advance_stage && (
        <AdvancePanel
          deal={deal}
          mutations={mutations}
          stageFlow={stageFlow}
          onSuccess={() => {
            // Credit submission is now an explicit, document-gated action
            // (the Submit to Credit Analysis panel), not a side-effect of
            // advancing a stage — so advancing just reports the advance.
            toast({ tone: 'success', message: 'Deal advanced.' });
            void reloadDeal();
          }}
        />
      )}

      {/* Action: submit to credit — gated by the document checklist (B10).
          The panel fetches its own checklist and renders only when the
          caller may submit, or when the deal is already submitted. */}
      <CreditSubmissionPanel deal={deal} onChanged={() => void reloadDeal()} />

      {/* Action: refer this deal to another person (A1). Hidden for drafts and
          while a referral is already pending acceptance. */}
      {!deal.draft && deal.referral_status !== 'pending' && (
        <ReferPanel deal={deal} onSuccess={() => void reloadDeal()} />
      )}

      {/* Action: request cancellation — gated by α7 can_request_cancel */}
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
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title={title}
        breadcrumbs={[{ label: 'A2Z Sales Pro', to: '/pipeline' }, { label: title }]}
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
            ← Back to pipeline
          </Button>
        }
      />
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
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

function CreditSubmissionPanel({ deal, onChanged }: CreditPanelProps) {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [checklist,  setChecklist]  = useState<CreditChecklistResponse | null>(null);
  const [checked,    setChecked]    = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchCreditChecklist(deal.id)
      .then((c) => {
        if (!alive) return;
        setChecklist(c);
        setChecked(new Set(c.provided));
      })
      .catch(() => { /* checklist unavailable — panel stays hidden */ });
    return () => { alive = false; };
  }, [deal.id]);

  if (!checklist) return null;

  // Already submitted — show the cross-link, no form.
  if (checklist.already_submitted) {
    return (
      <Card className="mt-6" stripe="accent">
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">Credit analysis</h3>
          <Badge tone="success" size="sm">Submitted</Badge>
        </Card.Header>
        <Card.Body>
          <p className="text-sm text-gray-700">
            This deal has been submitted to credit analysis.
            {checklist.lms_application_id && (
              <>
                {' '}
                <button
                  onClick={() =>
                    navigate(`/lms/${encodeURIComponent(checklist.lms_application_id!)}`)}
                  className="text-brand-primary hover:underline font-medium"
                >
                  View Loan Application →
                </button>
              </>
            )}
          </p>
        </Card.Body>
      </Card>
    );
  }

  // Only the owner / admin sees the submission form.
  if (!checklist.can_submit) return null;

  const toggle = (doc: string) => {
    setError(null);
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(doc)) next.delete(doc);
      else next.add(doc);
      return next;
    });
  };

  const missing = checklist.required.filter((d) => !checked.has(d));

  const onSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitDealToCredit(deal.id, Array.from(checked));
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
        <h3 className="text-sm font-semibold text-gray-900">Submit to Credit Analysis</h3>
        <Badge tone="info" size="sm">document gate</Badge>
      </Card.Header>
      <Card.Body>
        <p className="text-xs text-gray-500 mb-3">
          Confirm each required document is on file. All required documents
          must be checked before the deal can be submitted to credit analysis.
        </p>
        <div className="space-y-2">
          {checklist.required.map((doc) => (
            <label key={doc} className="flex items-center gap-2 text-sm text-gray-800">
              <input
                type="checkbox"
                checked={checked.has(doc)}
                onChange={() => toggle(doc)}
                disabled={submitting}
                className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary/30"
              />
              <span>{doc}</span>
            </label>
          ))}
        </div>
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {!error && missing.length > 0 && (
          <div className="mt-3 text-xs text-amber-600">
            {missing.length} document{missing.length === 1 ? '' : 's'} still required.
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <Button
            onClick={() => void onSubmit()}
            loading={submitting}
            disabled={missing.length > 0}
          >
            Submit to Credit Analysis
          </Button>
        </div>
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
      toast({ tone: 'success', message: `Referred to ${picked.name}. They'll need to accept it.` });
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
