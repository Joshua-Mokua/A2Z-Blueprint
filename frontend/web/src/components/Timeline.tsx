// Timeline — shared credit-workflow history (v10.587).
//
// Renders the per-application `history` events (who did what, when) as a
// vertical timeline so the analyst, deal owner, and credit admin share one
// view of where a case is and how long each step took.

import type { LoanAppHistoryEvent } from '@/types/lms';

const EVENT_LABELS: Record<string, string> = {
  application_created: 'Application created',
  deal_created: 'Deal created',
  deal_stage_change: 'Pipeline stage changed',
  assigned_to_analyst: 'Assigned to analyst',
  affordability_completed: 'Affordability appraisal completed',
  affordability_concurred: 'Affordability concurred',
  reopened_after_decline: 'Reopened after decline',
  placed_on_hold: 'Placed on hold',
  hold_lifted: 'Hold lifted',
  ready_for_committee: 'Marked ready for committee',
  returned_for_rework: 'Returned for rework',
  decision_approved: 'Decision — approved',
  decision_declined: 'Decision — declined',
  decision_returned: 'Decision — returned for rework',
  committee_appeal: 'Committee decision appealed',
  info_requested: 'Information requested',
  info_provided: 'Information provided',
  offer_issued: 'Letter of offer issued',
  offer_signed: 'Offer signed by customer',
  offer_validated: 'Offer validated by line manager',
  offer_validation_rejected: 'Offer validation rejected',
  analyst_confirmed: 'Confirmed to Credit Admin',
  handoff_to_credit_admin: 'Handed off to Credit Admin',
  referred_to_committee: 'Referred to credit committee',
  committee_vote: 'Committee vote recorded',
  sla_breached: 'SLA breached',
  sla_commitment: 'SLA commitment recorded',
};

export function eventLabel(ev: string): string {
  if (EVENT_LABELS[ev]) return EVENT_LABELS[ev];
  if (ev.startsWith('committee_')) return `Committee: ${ev.replace('committee_', '')}`;
  return ev.replace(/_/g, ' ');
}

function label(ev: string): string {
  return eventLabel(ev);
}

// Per-event colour: SLA breaches / declines are red, at-risk / holds / returns
// amber, approvals green, everything else the brand blue.
function eventTone(ev: string): { dot: string; text: string } {
  if (ev === 'sla_breached' || ev === 'decision_declined' || ev === 'offer_validation_rejected'
      || ev.includes('breach') || ev.includes('reject'))
    return { dot: '#DC2626', text: 'text-red-700' };
  if (ev === 'sla_commitment' || ev === 'placed_on_hold' || ev === 'returned_for_rework'
      || ev === 'decision_returned' || ev === 'committee_appeal')
    return { dot: '#D97706', text: 'text-amber-700' };
  if (ev === 'decision_approved') return { dot: '#059669', text: 'text-emerald-700' };
  return { dot: 'var(--brand-primary)', text: 'text-gray-900' };
}

function fmtWhen(at?: string): string {
  if (!at) return '';
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at;
  return d.toLocaleString();
}

export interface TimelineProps {
  events?: LoanAppHistoryEvent[];
  emptyHint?: string;
}

export function Timeline({ events, emptyHint }: TimelineProps) {
  if (!events || events.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-gray-500">
        {emptyHint ?? 'No workflow activity yet.'}
      </div>
    );
  }
  return (
    <ol className="relative border-l border-gray-200 ml-3 space-y-4 py-1">
      {events.map((e, i) => {
        const tone = eventTone(e.event);
        return (
        <li key={`${e.event}-${i}`} className="ml-4">
          <span
            className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full border-2 border-white"
            style={{ background: tone.dot }}
          />
          <div className="flex items-baseline justify-between gap-2 flex-wrap">
            <span className={`text-sm font-medium ${tone.text}`}>{label(e.event)}</span>
            <span className="text-xs text-gray-400">{fmtWhen(e.at)}</span>
          </div>
          {(e.by_name || e.by || e.note) && (
            <div className="text-xs text-gray-500 mt-0.5">
              {e.by_name ? (
                <span className="font-medium text-gray-700">
                  {e.by_name}{e.by_role ? ` (${e.by_role})` : ''}
                </span>
              ) : (
                e.by && <span className="font-mono">{e.by}</span>
              )}
              {(e.by_name || e.by) && e.note ? ' — ' : ''}
              {e.note}
            </div>
          )}
        </li>
        );
      })}
    </ol>
  );
}
