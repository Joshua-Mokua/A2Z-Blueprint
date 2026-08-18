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

import { displayName } from "../lib/names";
import { FacilitiesTable, facilitiesToPrintHtml } from '@/components/FacilitiesTable';
import { useState, useEffect } from 'react';
import type { ElementType } from 'react';
import { AffordabilityAppraisal } from '@/components/AffordabilityAppraisal';
import { getApplicationWorkbench, refreshWorkbench, addWorkbenchNote, pickLmsApplication, submitLmsToDcc, listLmsDocuments, downloadLmsDocument, uploadLmsDocument, requestLmsDocument, getDccRoster, recordDccVote, resolveDcc, handToCreditAnalyst, uploadCallbackMemo, escalateToChief, type WorkbenchView, type LmsDocumentsResponse, type DccRosterResponse } from '@/lib/api';
import { DocumentViewerModal } from '@/components/DocumentViewerModal';
import { useNavigate, useParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useLmsApplication } from '@/hooks/useLmsApplication';
import { useLmsMutations } from '@/hooks/useLmsMutations';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import { WorkbenchShell } from '@/components/WorkbenchShell';
import {
  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, setCommitteeReadiness, fetchReworkReasons, appealDecline, decideAppeal, recordCommitteePreRead, fetchCommitteePreReads, type CommitteePreReadsResponse, type LmsCommitteeRecordsResponse, type AssignableAnalyst,
  type CrView, type CrField, type CommitteeMember, type CommitteeTier,
} from '@/lib/api';  // attachment imports trimmed with AttachmentsBccCard
import { Card, EmbeddedShell, EmbeddedHeader, EmbeddedBody } from '@/components/Card';
import { printDocument, escapeHtml } from '@/lib/print';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import { Timeline, eventLabel } from '@/components/Timeline';
import {
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


  // IA Phase 3: the VIEW gate (which panel layout to show) keys purely on
  // "is the viewer the assigned analyst" — independent of assignment_purpose,
  // so legacy assignments (no purpose recorded) still get the analyst layout.
  // Editing on the credit page is credit-only (permissions.can_update), which
  // excludes the RM/originator by design.
  const _viewerIsAnalyst = Boolean(application.analyst?.code) && String(application.analyst?.code ?? '') === String(user?.staff_code ?? '');

  // IA Phase 3: the Assessment card is rendered in one of two positions —
  // directly under the customer strip for the assigned analyst, or in its
  // regular place in the origination flow for everyone else. Defined once
  // here and placed conditionally in the JSX below to avoid duplication.
  const printJourney = () => {
    const evs = [...(application.journey ?? application.history ?? [])];
    const rows = evs.map((e) => {
      const when = e.at ? new Date(e.at).toLocaleString() : '';
      const who = e.by_name || e.by || '';
      const role = e.by_role ? ` <span class="muted">(${escapeHtml(e.by_role)})</span>` : '';
      return `<tr><td>${escapeHtml(when)}</td><td>${escapeHtml(eventLabel(e.event))}</td><td>${escapeHtml(who)}${role}</td><td>${escapeHtml(e.note || '')}</td></tr>`;
    }).join('');
    const head = `<div class="head"><h1>Case Journey — ${escapeHtml(application.id)}</h1><span class="muted">${escapeHtml(application.client_name || '')} · printed ${escapeHtml(new Date().toLocaleString())}</span></div>`;
    const table = `<table><thead><tr><th style="width:20%">When</th><th style="width:22%">Event</th><th style="width:22%">By</th><th>Note</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="muted">No events recorded.</td></tr>'}</tbody></table>`;
    printDocument(`Case Journey ${application.id}`, head + table);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <WorkbenchShell
          title={application.client_name}
          stage={application.status}
          badges={[
            ...(application.sla?.state === 'breached' ? [{ label: 'SLA breached' }] : []),
            ...(application.sla?.state === 'due_soon' ? [{ label: 'SLA due soon' }] : []),
          ]}
          idLabel={application.id}
          onBack={() => navigate('/lms')}
          onRefresh={() => void refetch()}
          details={(
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
                  <span className="text-gray-900">{displayName(application.analyst.name)}</span>
                </div>
              )}
            </div>
          )}
        defaultTabId="journey"
        tabs={[
          { id: 'journey', label: 'Case Journey', color: '#0082BB', content: (
            <>
        {/* ─────────── Case Journey (prominent, always shown) ─────────── */}
        {(
          <Card stripe="primary">
            <Card.Header>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">Case Journey</h3>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-400">{(application.journey ?? application.history)?.length ?? 0} events · who did what, when</span>
                  <button onClick={printJourney} className="text-xs font-medium text-brand-primary hover:underline">Print</button>
                </div>
              </div>
            </Card.Header>
            <Card.Body>
              {/* Executive summary — compact reference facts folded in from the
                  former standalone Reference card, to reduce box count. Key
                  facts (client/CIF/product/amount/RM/analyst) live in the strip. */}
              <div className="mb-4 flex flex-wrap gap-x-6 gap-y-1.5 border-b border-gray-100 pb-3 text-xs">
                {([
                  ['Currency', application.currency || 'KES', false],
                  ['Applied', formatDate(application.application_date), false],
                  ['Updated', formatDate(application.last_updated), false],
                  ['Pipeline deal', application.pipeline_deal_id || '—', true],
                  ['RM code', application.rm_code || '—', true],
                  ['RM unit', application.rm_unit || '—', false],
                ] as const).map(([label, value, mono]) => (
                  <span key={label} className="flex items-center gap-1.5">
                    <span className="uppercase tracking-wide text-gray-400">{label}</span>
                    <span className={mono ? 'font-mono text-gray-800' : 'text-gray-800'}>{value}</span>
                  </span>
                ))}
              </div>
              <Timeline events={[...(application.journey ?? application.history ?? [])]} emptyHint="No activity recorded on this application yet. Actions taken here (assignment, decisions) will appear in this journey." />
            </Card.Body>
          </Card>
        )}


            </>
          ) },
          { id: 'documents', label: 'Department Review', color: '#0097A7', content: (
            <>
              {/* PICKING BELONGS WHERE THE WORK IS (ruling 2026-08-14):
                  "this should not have come on the Actions but on the
                  analysis." An analyst opening a case to work it should not
                  have to find another tab to claim it first - and Actions said
                  only "no actions available for your role", which reads as a
                  dead end rather than a case waiting to be picked up. */}
        {/* ─────────── ACTION: Self-pick (if can_self_pick) ─────────── */}
        {permissions.can_self_pick && (
          <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-blue-900">
                This case is unallocated and in your segment. Pick it to start working it.
              </div>
              <Button onClick={async () => {
                try {
                  await pickLmsApplication(application.id);
                  await refetch();
                  toast({ tone: 'success', message: 'Case picked — assigned to you.' });
                } catch (e) {
                  toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Pick failed.' });
                }
              }}>Pick this case</Button>
            </div>
          </div>
        )}

        {/* THE DOCUMENTATION HEADER CARD IS GONE (ruling 2026-08-14): "we can
                  remove entirely the top part written Documentation and the
                  contents."

                  A completeness percentage that reads 0%, "Nothing
                  outstanding", and three underwriting flags all reading "no"
                  told the analyst nothing they could act on - and pushed the
                  papers and the decision below the fold. What is left is the
                  documents themselves and the verdict. */}

        {/* ─────────── The analyst's verdict ───────────
            RULING (2026-08-14): "it is here that we need to see the
            recommendation from the consumer analyst ... if it returns for
            reworks with specifics, or recommend for department credit review
            which we defined as should be able to auto advance including
            stage."

            CorrectnessPanel already carries both - a reason list for a rework
            and a "ready for committee" verdict. It was on another tab, so the
            analyst read the papers on one screen and recorded the verdict on
            another. It belongs with the evidence it is a verdict about. */}
        {/* THE ASSIGNED ANALYST RECORDS IT, not anybody who can edit the
            case. This is the gate the panel already had on the Actions tab and
            it is the right one - a verdict carries a name, so the person
            giving it must be the person the case is with. */}
        {String(application.analyst?.code ?? '') === String(user?.staff_code ?? '')
          && !!application.analyst?.code && (
          <CorrectnessPanel appId={application.id} onDone={refetch} toast={toast} />
        )}

        <LmsTravelledDocuments appId={application.id} canDownload={!!permissions.can_update}
          // Whoever is WORKING the case may attach: the analyst who can send it
          // to the DCC, anyone who can update it, and the credit analyst it was
          // handed to. Not a committee member merely reading it.
          // WIDER THAN THE FIRST ATTEMPT. can_submit_to_dcc is only true while
          // a case sits at 'assigned' - so the moment it moved to credit_admin,
          // Catherine lost the ability to attach to a case she is still working.
          // can_view is the honest test here: the credit surface is already
          // scoped, and somebody who can open the case can add a paper to it.
          canAttach={!!(permissions.can_view ?? true)}
          onAttached={refetch} />


        {/* ─────────── Credit Report moved into the Assessment tabs below ─────────── */}
        <BranchCommitteeDecisionsCard appId={application.id} />
        {application.status === 'referred_to_committee' && (
          <CommitteePreReadPanel appId={application.id} toast={toast} />
        )}


            </>
          ) },
          // ── DEPARTMENT CREDIT COMMITTEE ──────────────────────────────
          // RULING (2026-08-14): "we embed a Department Credit Committee where
          // we will have a similar page like that of the branch credit
          // committee ... the same flow as the branch manager clicking on
          // review and getting to that page to vote should be the same for the
          // department committee."
          //
          // THE PANELS ALREADY EXISTED - DccVotePanel and SubmitToDccPanel -
          // buried inside the journey and actions tabs, several screens apart.
          // A member arriving to vote had to know where to look. They are the
          // same two panels; what was missing was somewhere obvious to put
          // them.
          //
          // Sits directly after Department Analysis, because that is the order
          // the work happens: read the case, analyse it, take it to committee.
          { id: 'dcc', label: 'Department Credit Committee', color: '#005B82', content: (
            <div className="space-y-4">
              <DccVotePanel appId={application.id} toast={toast} onDone={refetch} />
              {permissions.can_submit_to_dcc && (
                <SubmitToDccPanel appId={application.id} onDone={refetch} toast={toast} />
              )}
              {/* The branch committee's decision stays on the journey tab,
                  where it is context for the whole case rather than only for
                  voting - so it is not repeated here. */}
            </div>
          ) },
          // ── CREDIT RISK REVIEW ────────────────────────────────────────
          // RULING (2026-08-18): the bank credit analyst "needs an extra
          // button on top indicating Credit Risk Review, after the Department
          // Committee ... he needs to review and recommend based on the
          // pre-approval and pre-disbursement conditions, including escalating
          // to the Director Credit Risk. If he approves, it is from here that
          // it should travel to credit administration."
          //
          // THE PANEL ALREADY EXISTS. ActionPanelDecision carries the verdict,
          // both kinds of condition and the push to the Chief, and the server
          // already routes an approval to credit admin. It was buried on the
          // Actions tab among a dozen other things, so the one step this role
          // exists to perform was the hardest thing on the page to find.
          //
          // This gives it a tab of its own, named for the job, sitting where
          // the work happens: after the committee that recommended the case.
          //
          // Shown only to somebody who may actually decide - can_record_decision
          // is the same gate the panel already had. A tab that is visible and
          // does nothing is worse than no tab.
          ...(permissions.can_record_decision ? [{
            id: 'crr', label: 'Credit Risk Review', color: '#C62828', content: (
              <div className="space-y-4">
                <Card>
                  <Card.Body>
                    <p className="text-sm text-gray-700">
                      The department committee has recommended this case. Record
                      the credit decision here: approve with any pre-approval and
                      pre-disbursement conditions, return it for more information,
                      or push it to the Chief Credit Risk.
                    </p>
                    <p className="mt-1 text-xs text-gray-500">
                      An approval sends the case to Credit Administration with its
                      conditions attached. A decline goes back to the owner, who
                      may appeal or accept it.
                    </p>
                  </Card.Body>
                </Card>
                <ActionPanelDecision
                  appId={application.id}
                  open={decisionOpen}
                  setOpen={setDecisionOpen}
                  mutations={mutations}
                  onSuccess={async (verdict) => {
                    await refetch();
                    setDecisionOpen(false);
                    toast({
                      tone: verdict === 'approved' ? 'success'
                        : verdict === 'declined' ? 'danger' : 'warning',
                      message: verdict === 'approved'
                        ? 'Approved — the case is now with Credit Administration.'
                        : verdict === 'declined'
                        ? 'Declined — it goes back to the owner to appeal or accept.'
                        : `Decision recorded: ${verdict}`,
                    });
                  }}
                  toast={toast}
                />
              </div>
            ),
          }] : []),
          { id: 'cr', label: 'Transaction Memo', color: '#7E57C2', content: (
            <CreditReportCard appId={application.id} canEdit={!!permissions.can_update && !_viewerIsAnalyst} toast={toast} embedded />
          ) },
          { id: 'affordability', label: 'Affordability', color: '#00A65A', content: (
            <AffordabilityAppraisal defaultCif={application.client_cif} appId={application.id} embedded canEdit={!!permissions.can_update} />
          ) },
          ...(permissions.can_update ? [{ id: 'engines', label: 'Engines & Conflicts', color: '#C62828', content: (
            <CreditWorkbenchPanel appId={application.id} toast={toast} embedded canEdit={!!permissions.can_update} />
          ) }] : []),
          { id: 'actions', label: 'Actions', color: '#EF6C00', content: (
            <div className="space-y-4">
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


        {/* ─────────── ACTION: Hand to Credit Analyst (if can_hand_to_credit_analyst) ─────────── */}
        {permissions.can_hand_to_credit_analyst && (
          <HandToCreditAnalystPanel appId={application.id} onDone={refetch} toast={toast} />
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
              ? 'Read the papers, then either recommend the case to the department committee or return it to the branch with what needs fixing.'
              : 'Assigned for decisioning — analyse the case and record the credit decision.'}
          </div>
        )}
        {application.committee_readiness && (
          <div className={`mt-2 rounded-md px-4 py-2 text-xs ${
            application.committee_readiness.state === 'ready_for_committee'
              ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {application.committee_readiness.state === 'ready_for_committee'
              ? `Recommended to committee by ${application.committee_readiness.by_name}`
              : `Returned for rework — by ${application.committee_readiness.by_name}`}
            {application.committee_readiness.opinion
              && <div className="mt-1 italic">Opinion: {application.committee_readiness.opinion}</div>}
          </div>
        )}
        {/* CorrectnessPanel moved to Department Review, where the papers
            it judges are. Removed here so it does not render twice. */}

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

        <AppealPanel app={application} canReview={!!permissions.can_record_decision} onDone={refetch} toast={toast} />


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

            </div>
          ) },
        ]}
      />
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
  // ── TWO KINDS, BECAUSE DIFFERENT PEOPLE TICK THEM ───────────────────────
  // RULING (2026-08-15): approve "with pre-approval conditions, pre-
  // disbursement conditions". Credit admin clears the first; Trops clears the
  // second before money moves. One box cannot say which is which, and the
  // person ticking would have to guess.
  //
  // `conditions` above stays as the pre-approval box - every decision recorded
  // before today used it that way, and renaming it would strand them.
  const [preDisb, setPreDisb] = useState<string>('');
  const [escalateOpen, setEscalateOpen] = useState(false);
  const [escalateReason, setEscalateReason] = useState('');
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
      pre_approval_conditions: conditionsList.length > 0 ? conditionsList : undefined,
      pre_disbursement_conditions: preDisb
        .split('\n').map((c) => c.trim()).filter((c) => c.length > 0),
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
            <label className="text-sm font-medium text-gray-700">Pre-approval conditions (one per line)</label>
            <textarea
              value={conditions}
              onChange={(e) => setConditions(e.target.value)}
              disabled={mutations.loading}
              rows={3}
              placeholder="Board resolution&#10;Debenture&#10;Insurance certificate"
              className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
            />
            <p className="text-xs text-gray-500 mt-1">
              Cleared by credit admin before the case moves on. The last one
              ticked releases it to Trops.
            </p>
          </div>
        )}
        {verdict === 'approved' && (
          <div className="mt-3">
            <label className="text-sm font-medium text-gray-700">Pre-disbursement conditions (one per line)</label>
            <textarea
              value={preDisb}
              onChange={(e) => setPreDisb(e.target.value)}
              disabled={mutations.loading}
              rows={3}
              placeholder="Charge registered&#10;Insurance assigned&#10;Valuation within 90 days"
              className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
            />
            <p className="text-xs text-gray-500 mt-1">
              Cleared by Trops before money moves. Leave blank if there are none.
            </p>
          </div>
        )}

        {/* ─────────── Push it to the Chief ───────────
            RULING (2026-08-15): the analyst may "push to the Chief Credit Risk
            for their approval as well."

            The Chief is resolved SERVER-SIDE from config - this does not name a
            person, because a bank changes its people more often than its
            software.

            The case does not change hands: escalation asks a question of
            somebody senior, and the analyst still owns it. */}
        <div className="mt-4 border-t border-gray-100 pt-3">
          {!escalateOpen ? (
            <button
              type="button"
              onClick={() => setEscalateOpen(true)}
              disabled={mutations.loading}
              className="text-xs font-medium text-[#005B82] hover:underline disabled:opacity-50"
            >
              Above my authority — push to the Chief Credit Risk
            </button>
          ) : (
            <div className="rounded-md border border-[#005B82]/30 bg-[#005B82]/5 p-3">
              <label className="text-sm font-medium text-gray-800">
                Why does this need the Chief?
              </label>
              <textarea
                value={escalateReason}
                onChange={(e) => setEscalateReason(e.target.value)}
                rows={2}
                placeholder="Exposure above my limit; concentration in one sector…"
                className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary resize-y"
              />
              <p className="mt-1 text-xs text-gray-600">
                A case arriving with no question attached wastes the trip.
              </p>
              <div className="mt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setEscalateOpen(false); setEscalateReason(''); }}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={mutations.loading || !escalateReason.trim()}
                  onClick={() => {
                    void (async () => {
                      try {
                        const r = await escalateToChief(appId, { reason: escalateReason.trim() });
                        const to = (r as unknown as { escalated_to?: string }).escalated_to;
                        setError(null);
                        setEscalateOpen(false);
                        setEscalateReason('');
                        toast({ tone: 'success',
                          message: `Sent to ${to || 'the Chief Credit Risk'}. The case stays with you.` });
                      } catch (e) {
                        setError(e instanceof Error ? e.message : 'Could not escalate');
                      }
                    })();
                  }}
                  className="rounded-md bg-[#005B82] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
                >
                  Push to the Chief
                </button>
              </div>
            </div>
          )}
        </div>
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



// (Attachments & BCC card removed from the credit surface — the RM's documents
// live on the pipeline workbench; committee outcomes on the deal's committee card.)

// ─── Credit Report (CR) — hybrid auto-populated appraisal memo ─────────
// Template-driven: renders sections/fields from the server. auto/cbs fields
// show prefilled (editable but tinted to signal provenance); rm fields are
// blank for the relationship owner. Save draft or mark complete (required
// fields enforced server-side).
function DccVotePanel({ appId, toast, onDone }: {
  appId: string;
  toast: ReturnType<typeof useToast>['toast'];
  onDone: () => Promise<void> | void;
}) {
  const [roster, setRoster] = useState<DccRosterResponse | null>(null);
  const [memberId, setMemberId] = useState('');
  const [vote, setVote] = useState('YES');
  const [rationale, setRationale] = useState('');
  const [busy, setBusy] = useState(false);
  const load = () => { getDccRoster(appId).then(setRoster).catch(() => { /* none */ }); };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [appId]);
  // ── SAY WHY, RATHER THAN NOTHING ─────────────────────────────────────────
  // This returned null whenever the case was not yet before the committee, so
  // the Department Credit Committee tab rendered BLANK - which reads as broken
  // rather than as "not yet". A member opening it to vote had no way to tell
  // the difference.
  //
  // Returning null is right where the panel is one card among many on another
  // tab. It is wrong when the panel IS the tab.
  if (!roster) {
    return (
      <Card>
        <Card.Body>
          <p className="py-6 text-center text-sm text-gray-400">Loading the committee…</p>
        </Card.Body>
      </Card>
    );
  }
  if (!roster.enabled) {
    return (
      <Card>
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">Department Credit Committee</h3>
        </Card.Header>
        <Card.Body>
          <p className="text-sm text-gray-600">
            The department committee is not switched on for this bank. An
            administrator enables it under Administration → Credit Committees.
          </p>
        </Card.Body>
      </Card>
    );
  }
  if (!roster.is_dcc_case && !roster.outcome) {
    return (
      <Card>
        <Card.Header>
          <h3 className="text-sm font-semibold text-gray-900">Department Credit Committee</h3>
        </Card.Header>
        <Card.Body>
          <p className="text-sm text-gray-600">
            This case has not been submitted to the department committee yet.
          </p>
          <p className="mt-1 text-xs text-gray-500">
            It arrives here once the analyst marks it ready on the Department
            Review tab — then the committee's members vote, and the case moves
            on by itself when they have.
          </p>
        </Card.Body>
      </Card>
    );
  }
  const votesByMember = new Map(roster.votes.map((v) => [v.member_id, v]));
  const resolve = async () => {
    setBusy(true);
    try {
      await resolveDcc(appId, {});
      toast({ tone: 'success', message: 'DCC closed — case returned to the Department Analyst.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not close the DCC.' });
    } finally { setBusy(false); }
  };
  const cast = async () => {
    if (!memberId) return;
    setBusy(true);
    try {
      await recordDccVote(appId, { member_id: memberId, vote, rationale: rationale.trim() });
      toast({ tone: 'success', message: 'DCC vote recorded.' });
      setRationale(''); load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Vote failed.' });
    } finally { setBusy(false); }
  };
  return (
    <Card className="mt-4" stripe="primary">
      <Card.Header>
        <h3 className="text-sm font-semibold text-gray-900">{roster.name}</h3>
        <span className="text-xs text-gray-500">{roster.votes.length}/{roster.members.length} voted</span>
      </Card.Header>
      <Card.Body>
        {roster.outcome ? (
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm">
            <div>DCC recommendation:{' '}
              <span className={roster.outcome.recommendation === 'support' ? 'font-semibold text-green-700'
                : roster.outcome.recommendation === 'oppose' ? 'font-semibold text-red-600'
                : 'font-semibold text-gray-600'}>
                {roster.outcome.recommendation}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Tally: {roster.outcome.tally.yes} yes · {roster.outcome.tally.no} no · {roster.outcome.tally.abstain} abstain
              {roster.outcome.by_name ? ` · closed by ${roster.outcome.by_name}` : ''}
            </div>
            <p className="mt-2 text-xs text-gray-500">Advisory only — the Credit Analyst makes the final decision.</p>
          </div>
        ) : roster.members.length === 0 ? (
          <p className="text-xs text-gray-400">No DCC members configured yet (set them in the credit-workflow config).</p>
        ) : (
          <>
            <div className="mb-3 space-y-1">
              {roster.members.map((m) => {
                const id = m.id || m.member_id || '';
                const v = votesByMember.get(id);
                return (
                  <div key={id} className="flex items-center justify-between text-sm">
                    <span className="text-gray-800">
                      {m.name || id}{m.role ? <span className="text-xs text-gray-500"> — {m.role}</span> : null}
                    </span>
                    <span className={v ? (v.vote === 'YES' ? 'text-green-700' : v.vote === 'NO' ? 'text-red-600' : 'text-gray-500') : 'text-gray-300'}>
                      {v ? v.vote : 'not voted'}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="grid grid-cols-1 items-end gap-2 border-t pt-3 md:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-gray-700">Member</label>
                <select value={memberId} onChange={(e) => setMemberId(e.target.value)} disabled={busy}
                  className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm">
                  <option value="">Select…</option>
                  {roster.members.map((m) => {
                    const id = m.id || m.member_id || '';
                    return <option key={id} value={id}>{m.name || id}</option>;
                  })}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700">Vote</label>
                <select value={vote} onChange={(e) => setVote(e.target.value)} disabled={busy}
                  className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm">
                  <option>YES</option><option>NO</option><option>ABSTAIN</option>
                </select>
              </div>
              <Button onClick={cast} disabled={busy || !memberId}>Record vote</Button>
            </div>
            <input value={rationale} onChange={(e) => setRationale(e.target.value)} disabled={busy}
              placeholder="Rationale (optional)"
              className="mt-2 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm" />
            {roster.votes.length > 0 && (
              <div className="mt-3 flex items-center justify-end gap-2 border-t pt-3">
                <span className="text-xs text-gray-500">Advisory — closing returns the case to the Department Analyst.</span>
                <Button variant="ghost" onClick={resolve} disabled={busy}>Close &amp; return to analyst</Button>
              </div>
            )}
          </>
        )}
      </Card.Body>
    </Card>
  );
}


// WHAT THE ANALYST ATTACHES (ruling 2026-08-12: "in the pilot she is
// particularly supposed to attach the CRB and the Call Back Memo").
//
// Offered as named buttons rather than a free-text box: a document called
// "CRB" on one case and "CRB Report" on another cannot be checked off a
// required list, and the analyst should not have to know the exact string.
// "Other" stays for the paper nobody anticipated.
const ANALYST_DOCS = ['CRB Report', 'Call Back Memo', 'Other'];

function LmsTravelledDocuments({ appId, canDownload, canAttach, onAttached }: {
  appId: string; canDownload: boolean; canAttach?: boolean; onAttached?: () => void;
}) {
  const [files, setFiles] = useState<LmsDocumentsResponse['files']>({});
  const [viewing, setViewing] = useState<{ docName: string; filename: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const [requested, setRequested] = useState<{ name: string; note?: string }[]>([]);

  const reload = () => {
    listLmsDocuments(appId).then((d) => {
      setFiles(d.files || {});
      setRequested(d.requested || []);
    }).catch(() => { /* none on file */ });
  };

  async function requestDoc() {
    const name = (window.prompt('What document do you need?') || '').trim();
    if (!name) return;
    const note = (window.prompt('Why, or any detail for whoever supplies it? (optional)') || '').trim();
    setBusy(true);
    setErr('');
    try {
      await requestLmsDocument(appId, name, note);
      reload();
      onAttached?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not record that request.');
    } finally {
      setBusy(false);
    }
  }
  useEffect(reload, [appId]);

  async function attach(docName: string, file: File) {
    setBusy(true);
    setErr('');
    try {
      const b64 = await new Promise<string>((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(',')[1] ?? '');
        r.onerror = () => rej(new Error('Could not read that file.'));
        r.readAsDataURL(file);
      });
      await uploadLmsDocument(appId, docName, file.name, b64);
      reload();
      onAttached?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not attach that file.');
    } finally {
      setBusy(false);
    }
  }

  const entries = Object.entries(files);
  // The panel must render even with nothing on file - otherwise the analyst
  // has nowhere to attach the first document.
  if (entries.length === 0 && !canAttach) return null;
  return (
    <Card className="mt-4">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Documents on file</h2>
        <span className="text-xs text-gray-500">
          {entries.length} document{entries.length === 1 ? '' : 's'} travelled with the case
        </span>
      </Card.Header>
      <Card.Body>
        <div className="space-y-2">
          {entries.map(([doc, meta]) => (
            <div key={doc} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
              <span className="text-gray-800">
                <span className="text-gray-400">📄</span> {doc}
                {meta?.filename && <span className="ml-2 text-xs text-gray-500">{meta.filename}</span>}
              </span>
              <button type="button" className="text-brand-primary hover:underline text-xs"
                onClick={() => setViewing({ docName: doc, filename: meta?.filename || doc })}>View</button>
            </div>
          ))}
        </div>
        {entries.length === 0 && (
          <p className="py-3 text-center text-xs text-gray-400">
            Nothing on file yet.
          </p>
        )}

        {canAttach && (
          <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
            <p className="mb-2 text-xs font-medium text-gray-700">Attach a document</p>
            <div className="flex flex-wrap items-center gap-2">
              {[...ANALYST_DOCS, ...requested.map((r) => r.name)
                .filter((n) => !ANALYST_DOCS.includes(n))].map((d) => (
                <label key={d}
                       className={'cursor-pointer rounded-md border px-3 py-1.5 text-xs '
                         + (files[d]
                           ? 'border-[#BED600] bg-[#F4F8E6] text-[#3B6D11]'
                           : 'border-gray-300 bg-white text-gray-700 hover:border-brand-primary')}>
                  {files[d] ? `✓ ${d}` : d}
                  <input type="file" className="hidden" disabled={busy}
                         onChange={(e) => {
                           const f = e.target.files?.[0];
                           if (!f) return;
                           const name = d === 'Other'
                             ? (window.prompt('What is this document called?') || '').trim()
                             : d;
                           if (!name) return;
                           void attach(name, f);
                           e.target.value = '';
                         }} />
                </label>
              ))}
              {busy && <span className="text-xs text-gray-500">Attaching…</span>}
            </div>
            {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}

            {/* ASK FOR SOMETHING NOT ON THE LIST. The required list is per
                PRODUCT and set by an admin - it says what every case of this
                kind needs. What one analyst wants on ONE case is a different
                thing, and writing it into the product config would quietly
                change the rules for every future deal. So it is recorded on
                the case, with who asked. */}
            <div className="mt-2 flex items-center gap-2">
              <button type="button" disabled={busy}
                      onClick={() => void requestDoc()}
                      className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:border-brand-primary">
                Request a document
              </button>
              {requested.length > 0 && (
                <span className="text-[11px] text-gray-500">
                  {requested.length} requested:{' '}
                  {requested.map((r) => r.name).join(', ')}
                </span>
              )}
            </div>
            <p className="mt-2 text-[11px] text-gray-500">
              Attached against this case and recorded under your name and role,
              so it is clear later which papers came from credit rather than
              from the branch.
            </p>
          </div>
        )}

        {!canDownload && (
          <p className="mt-2 text-xs text-gray-400">Read-only — download is not permitted for your role.</p>
        )}
      </Card.Body>
      {viewing && (
        <DocumentViewerModal
          dealId="" docName={viewing.docName} filename={viewing.filename}
          canDownload={canDownload}
          fetchBlob={() => downloadLmsDocument(appId, viewing.docName)}
          onClose={() => setViewing(null)}
        />
      )}
    </Card>
  );
}


function HandToCreditAnalystPanel({ appId, onDone, toast }: {
  appId: string;
  onDone: () => Promise<void> | void;
  toast: ReturnType<typeof useToast>['toast'];
}) {
  const [busy, setBusy] = useState(false);
  const hand = async () => {
    setBusy(true);
    try {
      await handToCreditAnalyst(appId);
      toast({ tone: 'success', message: 'Handed to the Credit Analyst pool for decisioning.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Handoff failed.' });
    } finally { setBusy(false); }
  };
  return (
    <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 px-4 py-3">
      <div className="text-sm font-semibold text-blue-900">Hand to Credit Analyst</div>
      <p className="mt-1 text-xs text-blue-800">
        The DCC has advised. Release this case to the Credit Analyst pool — a Credit Analyst
        picks it up and, seeing both the Branch Committee and DCC inputs, makes the final
        credit decision that issues the offer. You do not decide the case.
      </p>
      <div className="mt-3">
        <Button onClick={hand} disabled={busy}>{busy ? 'Handing over…' : 'Hand to Credit Analyst'}</Button>
      </div>
    </div>
  );
}


function SubmitToDccPanel({ appId, onDone, toast }: {
  appId: string;
  onDone: () => Promise<void> | void;
  toast: ReturnType<typeof useToast>['toast'];
}) {
  const [opinion, setOpinion] = useState('');
  const [pep, setPep] = useState(false);
  const [busy, setBusy] = useState(false);
  const [memoBusy, setMemoBusy] = useState(false);
  const attachMemo = () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setMemoBusy(true);
      try {
        const buf = await f.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        await uploadCallbackMemo(appId, { filename: f.name, content_b64: btoa(bin) });
        toast({ tone: 'success', message: 'Call-Back Memo attached.' });
        await onDone();
      } catch (e) {
        toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Upload failed.' });
      } finally { setMemoBusy(false); }
    };
    inp.click();
  };
  const submit = async () => {
    setBusy(true);
    try {
      await submitLmsToDcc(appId, { opinion: opinion.trim(), pep_confirmed: pep });
      toast({ tone: 'success', message: 'Submitted to the Department Credit Committee.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Submit failed.' });
    } finally { setBusy(false); }
  };
  return (
    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="text-sm font-semibold text-amber-900">Submit to Department Credit Committee</div>
      <p className="mt-1 text-xs text-amber-800">
        Check completeness and voice your support. You do not make the credit decision —
        this refers the case to the DCC. As the checker, complete the call-back and
        <strong> attach the Call-Back Memo</strong> below, and confirm PEP compliance.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={attachMemo} disabled={memoBusy || busy}>
          {memoBusy ? 'Attaching…' : 'Attach Call-Back Memo'}
        </Button>
        <span className="text-xs text-amber-700">Stored with the case + readable by the committee.</span>
      </div>
      <label className="mt-3 block text-xs font-medium text-amber-900">Support opinion</label>
      <textarea
        value={opinion} disabled={busy} rows={3}
        onChange={(e) => setOpinion(e.target.value)}
        placeholder="Why you support this facility (completeness, key strengths)…"
        className="mt-1 w-full rounded-md border border-amber-300 px-2 py-1.5 text-sm"
      />
      <label className="mt-3 flex items-center gap-2 text-sm text-amber-900">
        <input type="checkbox" checked={pep} disabled={busy} onChange={(e) => setPep(e.target.checked)} />
        I confirm the client is not a PEP and has no compliance issues.
      </label>
      <div className="mt-3">
        <Button onClick={submit} disabled={busy || !pep}>
          {busy ? 'Submitting…' : 'Submit to DCC'}
        </Button>
      </div>
    </div>
  );
}


function CreditReportCard({ appId, canEdit, toast, embedded = false }: {
  appId: string; canEdit: boolean; toast: ReturnType<typeof useToast>['toast'];
  embedded?: boolean;
}) {
  const [cr, setCr] = useState<CrView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

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

  const printCr = () => {
    const secs = (cr.template?.sections ?? []).map((sec) => {
      const tableField = (sec.fields ?? []).find((f) => f.type === 'table');
      if (tableField) {
        return `<h2>${escapeHtml(sec.title)}</h2>${facilitiesToPrintHtml(valueFor(tableField.key))}`;
      }
      const rows = (sec.fields ?? []).map((f) =>
        `<tr><th style="width:42%">${escapeHtml(f.label)}</th><td>${escapeHtml(valueFor(f.key)) || '—'}</td></tr>`).join('');
      return `<h2>${escapeHtml(sec.title)}</h2><table>${rows}</table>`;
    }).join('');
    const head = `<div class="head"><h1>Transaction Memo — ${escapeHtml(appId)}</h1><span class="muted">${cr.completed ? 'Complete' : 'Draft'} · printed ${escapeHtml(new Date().toLocaleString())}</span></div>`;
    printDocument(`Transaction Memo ${appId}`, head + secs);
  };

  const Shell:   ElementType = embedded ? EmbeddedShell  : Card;
  const SHeader: ElementType = embedded ? EmbeddedHeader : Card.Header;
  const SBody:   ElementType = embedded ? EmbeddedBody   : Card.Body;

  return (
    <Shell className="mt-6">
      <SHeader>
        <h2 className="text-base font-semibold text-gray-900">Transaction Memo (TM)</h2>
        <div className="flex items-center gap-2">
          {cr.completed && <Badge tone="success">Complete</Badge>}
          {!cr.cbs_available && <span className="text-xs text-gray-400">CBS data unavailable — fill manually</span>}
          <button className="text-sm text-brand-primary" onClick={printCr}>Print</button>
        </div>
      </SHeader>
      <SBody>
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
            <div className="mt-4 flex gap-2">
              <Button onClick={() => save(false)} disabled={busy}>{busy ? 'Working…' : 'Save draft'}</Button>
              <Button variant="secondary" onClick={() => save(true)} disabled={busy}>Mark complete</Button>
            </div>
          )}
          {cr.updated_by && (
            <div className="mt-2 text-xs text-gray-400">Last saved by {cr.updated_by}</div>
          )}
        </SBody>
    </Shell>
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

function CreditWorkbenchPanel({ appId, toast, embedded = false, canEdit = false }: {
  appId: string; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
  embedded?: boolean; canEdit?: boolean;
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

  const Shell:   ElementType = embedded ? EmbeddedShell  : Card;
  const SHeader: ElementType = embedded ? EmbeddedHeader : Card.Header;
  const SBody:   ElementType = embedded ? EmbeddedBody   : Card.Body;

  return (
    <Shell className="mt-4" stripe="accent">
      <SHeader>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Credit Analyst Workbench</h3>
          <span className="text-xs text-gray-500">Session {s.state ?? '—'}</span>
        </div>
      </SHeader>
      <SBody>
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

        {canEdit ? (
        <div className="mb-4">
          <Button variant="primary" onClick={() => void refresh()} disabled={busy}>
            {busy ? 'Refreshing…' : 'Refresh engines'}
          </Button>
        </div>
        ) : (
          <p className="mb-4 text-xs text-gray-400">Read-only — you can view the credit analysis but not change it.</p>
        )}

        {/* Analyst notes */}
        <div className="border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">
            Analyst notes {s.notes_count ? `(${s.notes_count})` : ''}
          </p>
          {canEdit && (
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
          )}
          {s.notes_by_category && Object.keys(s.notes_by_category).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
              {Object.entries(s.notes_by_category).map(([cat, n]) => (
                <span key={cat} className="rounded bg-gray-100 px-2 py-0.5">{cat.replace(/_/g, ' ')}: {n}</span>
              ))}
            </div>
          )}
        </div>
      </SBody>
    </Shell>
  );
}

function AppealPanel({ app, canReview, onDone, toast }: {
  app: LoanApplication; canReview: boolean;
  onDone: () => Promise<unknown> | unknown; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = !!app.appeal_pending;
  const isDeclined = String(app.status).toLowerCase() === 'declined';
  const appeals = app.appeals ?? [];
  if (!isDeclined && !pending && appeals.length === 0) return null;

  const file = async () => {
    if (!reason.trim()) { toast({ tone: 'danger', message: 'An appeal reason is required.' }); return; }
    setBusy(true);
    try {
      await appealDecline(app.id, reason.trim());
      toast({ tone: 'success', message: 'Appeal filed — pending manager review.' });
      await onDone();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' }); }
    finally { setBusy(false); }
  };
  const review = async (outcome: 'grant' | 'uphold') => {
    setBusy(true);
    try {
      const r = await decideAppeal(app.id, outcome, note.trim() || undefined);
      toast({ tone: 'success', message: r.reopened ? 'Appeal granted — case reopened for a fresh decision.' : 'Appeal upheld — the decline stands.' });
      await onDone();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' }); }
    finally { setBusy(false); }
  };

  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Decline appeal</h3></Card.Header>
      <Card.Body>
        {appeals.length > 0 && (
          <div className="mb-3 space-y-2">
            {appeals.map((a, i) => (
              <div key={i} className="rounded border border-gray-200 bg-gray-50 p-2 text-xs">
                <div><span className="font-medium">Reason:</span> {a.reason}</div>
                <div className="text-gray-500">
                  Filed{a.by_name ? ` by ${a.by_name}` : ''}{a.at ? ` · ${a.at}` : ''} — <span className="font-medium">{a.outcome}</span>{a.reviewed_by_name ? ` by ${a.reviewed_by_name}` : ''}
                </div>
                {a.review_note && <div className="italic text-gray-500">Note: {a.review_note}</div>}
              </div>
            ))}
          </div>
        )}
        {isDeclined && !pending && (
          <div>
            <p className="mb-2 text-xs text-gray-500">This application was declined. File an appeal for reconsideration — a manager will review it.</p>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Grounds for appeal…" rows={3} className="mb-2 w-full rounded border border-gray-300 px-3 py-2 text-sm" />
            <Button variant="primary" onClick={() => void file()} disabled={busy}>File appeal</Button>
          </div>
        )}
        {pending && canReview && (
          <div>
            <p className="mb-2 text-xs text-gray-500">An appeal is pending. Grant it (reopens the case for a fresh decision) or uphold the decline.</p>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Review note (optional)…" rows={2} className="mb-2 w-full rounded border border-gray-300 px-3 py-2 text-sm" />
            <div className="flex gap-2">
              <Button variant="primary" onClick={() => void review('grant')} disabled={busy}>Grant (reopen)</Button>
              <Button variant="ghost" onClick={() => void review('uphold')} disabled={busy}>Uphold decline</Button>
            </div>
          </div>
        )}
        {pending && !canReview && (
          <p className="text-xs text-gray-500">Appeal filed — pending manager review.</p>
        )}
      </Card.Body>
    </Card>
  );
}

function CorrectnessPanel({ appId, onDone, toast }: {
  appId: string; onDone: () => Promise<unknown> | unknown; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [opinion, setOpinion] = useState('');
  const [reasons, setReasons] = useState<string[]>([]);
  const [reasonOptions, setReasonOptions] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    fetchReworkReasons().then(setReasonOptions).catch(() => setReasonOptions([]));
  }, []);
  const toggleReason = (r: string) =>
    setReasons((p) => (p.includes(r) ? p.filter((x) => x !== r) : [...p, r]));
  const act = async (decision: 'ready' | 'rework') => {
    if (decision === 'rework' && reasons.length === 0) {
      toast({ tone: 'danger', message: 'Select at least one rework reason before returning the case.' });
      return;
    }
    setBusy(true);
    try {
      await setCommitteeReadiness(appId, decision, opinion.trim() || undefined,
        decision === 'rework' ? reasons : undefined);
      toast({ tone: 'success', message: decision === 'ready'
        ? 'Recommended — the case is now with the department committee.'
        : 'Returned to the branch for rework.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' });
    } finally { setBusy(false); }
  };
  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Correctness check</h3></Card.Header>
      <Card.Body>
        <p className="mb-2 text-xs text-gray-500">Confirm the case is well-packaged for committee, or return it for rework. When returning for rework, select the specific reason(s) so the branch knows exactly what to fix; you may also add an opinion for the Chief.</p>
        {reasonOptions.length > 0 && (
          <div className="mb-3 rounded-md border border-gray-200 bg-gray-50 p-3">
            <div className="mb-1.5 text-xs font-medium text-gray-600">Rework reasons <span className="text-gray-400">(required if returning for rework)</span></div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {reasonOptions.map((r) => (
                <label key={r} className="flex items-center gap-2 text-xs text-gray-700">
                  <input type="checkbox" checked={reasons.includes(r)} onChange={() => toggleReason(r)} disabled={busy} />
                  {r}
                </label>
              ))}
            </div>
          </div>
        )}
        <textarea
          value={opinion}
          onChange={(e) => setOpinion(e.target.value)}
          placeholder="Optional opinion / notes for the Chief…"
          className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          rows={3}
        />
        <div className="flex gap-2">
          {/* "MAYBE READY RECOMMENDED" (ruling 2026-08-14). "Mark ready" reads
              like a housekeeping flag; what the analyst is doing is
              RECOMMENDING the case, and that recommendation now sends it to
              the committee in the same act. The label should say so, because
              somebody who thinks they are ticking a box will press it more
              casually than somebody who knows they are submitting. */}
          <Button variant="primary" onClick={() => void act('ready')} disabled={busy}>Recommend to committee</Button>
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
