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
import { useRole } from '@/hooks/useRole';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useToast } from '@/components/Toast';
import { fetchPipelineDealDetail, AuthExpiredError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import { PermissionBadges } from '@/components/PermissionBadges';
import {
  stageTone,
  ADVANCE_TARGET_STAGES,
  type PipelineDeal,
  type DealPermissions,
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
  const { user } = useRole();
  const { toast } = useToast();
  const mutations = usePipelineDealMutations();

  const [deal, setDeal] = useState<PipelineDeal | null>(null);
  const [permissions, setPermissions] = useState<DealPermissions | null>(null);
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
      <DetailFrame title="Pipeline Deal" branding={branding} user={user}>
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
      <DetailFrame title={`Deal ${dealId}`} branding={branding} user={user}>
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
      <DetailFrame title={`Deal ${dealId}`} branding={branding} user={user}>
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
    <DetailFrame title={`Deal ${deal.id}`} branding={branding} user={user}>
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
            <DetailField label="Deal value" value={formatValue(deal.deal_value, currency)} />
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
          onSuccess={(meta) => {
            // δ1 (2026-06-12): Advancing to Compliance silently triggers
            // LMS application creation server-side (α4 doctrine). Surface
            // that to the user via the toast so they know what happened.
            if (meta?.targetStage === 'Compliance') {
              toast({
                tone:    'success',
                message: '✓ Stage advanced. Loan application created.',
              });
            } else {
              toast({ tone: 'success', message: 'Deal advanced.' });
            }
            void reloadDeal();
          }}
        />
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
  branding: ReturnType<typeof useBranding>['branding'];
  user:     ReturnType<typeof useRole>['user'];
  children: React.ReactNode;
}

function DetailFrame({ title, branding, user, children }: DetailFrameProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: 'var(--brand-secondary)' }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[2.5px] font-bold opacity-70">
              {branding?.bank_name ?? 'A2Z MIS 360'}
            </div>
            <h1 className="text-xl font-bold mt-1">
              {branding?.app_name ?? 'A2Z'} MIS 360 — {title}
            </h1>
          </div>
          <div className="text-right text-xs opacity-70 leading-relaxed">
            {user?.full_name && (
              <div className="font-medium opacity-90">{user.full_name}</div>
            )}
            {user?.role && <div>{user.role}</div>}
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-8">
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
}

function AdvancePanel({ deal, mutations, onSuccess }: ActionPanelProps) {
  // Default to the next plausible stage if current is in the known list.
  const currentIndex = ADVANCE_TARGET_STAGES.indexOf(deal.stage);
  const defaultTarget = currentIndex >= 0 && currentIndex < ADVANCE_TARGET_STAGES.length - 1
    ? ADVANCE_TARGET_STAGES[currentIndex + 1]
    : ADVANCE_TARGET_STAGES[0];

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
              {ADVANCE_TARGET_STAGES.map((s) => (
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
