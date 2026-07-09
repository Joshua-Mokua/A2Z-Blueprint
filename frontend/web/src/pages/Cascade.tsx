// v10.533 Phase 5 Batch γ3b — Cascade landing page.
//
// Three sections:
//   1. Bank Targets — 21 KPIs at MD level (read-only view)
//   2. Given to me — incoming allocations from upline leaders
//   3. My allocations — outgoing cascade entries with coverage chips
//
// Coverage chip surfaces over-allocation drift (e.g. 22B target with
// 224B allocated). This is the read-only γ3 surface — γ5 will add
// edit affordances for MD bank-target setting and leader allocation.

import { useState } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useMyCascade } from '@/hooks/useMyCascade';
import { setBankTarget, setCascadeAllocations, ApiValidationError } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { AdminTabs } from '@/components/AdminTabs';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  formatTargetValue,
  coverageStatus,
  coverageTone,
  coverageLabel,
  type BankTarget,
  type CascadeEntry,
  type IncomingAllocation,
} from '@/types/cascade';


// ── Helpers ──────────────────────────────────────────────────────────────

function unitForKpiName(kpi: string): 'percent' | 'count' | 'currency' {
  const k = (kpi || '').toLowerCase();
  if (k.includes('ratio') || k.includes('score') || k === 'par' || k.includes('%')) return 'percent';
  if (k.includes('number of') || k.includes('borrowers') || k.includes('accounts') || k.includes('productivity')) return 'count';
  return 'currency';
}


// ── Page component ──────────────────────────────────────────────────────

export function Cascade() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const [period, setPeriod] = useState<string>('2026');

  // γ5a: only the MD can edit bank-level targets (server enforces 403
  // for non-MD callers; we hide the affordance client-side to avoid
  // showing a button that would 403).
  // γ5a-hotfix1: lenient match — real-world user records have
  // 'Chief Executive & Managing Director' (William's title) and bare
  // 'Managing Director'. Match either. Director-prefix roles like
  // 'Director Retail Banking' don't contain 'managing director' so
  // they don't false-positive.
  const isMd = (user?.role ?? '').toLowerCase().includes('managing director');

  const {
    bankTargets,    bankTargetsLoading,    bankTargetsError,
    incoming,       incomingLoading,       incomingError,
    outgoing,       outgoingLoading,       outgoingError,
    refetch,
  } = useMyCascade(period);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      <AdminTabs
        subtitle={`Bank-level targets · incoming allocations · my cascade · period ${period}`}
        actions={
          <input
            type="text"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            aria-label="Cascade period"
            className="h-9 px-2 rounded-md border border-gray-200 bg-white text-sm font-mono w-20 text-center focus:outline-none focus:border-brand-primary"
          />
        }
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6 space-y-5">

        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-500">
            {user?.full_name && (
              <>Viewing as <span className="font-medium text-gray-700">{user.full_name}</span> (staff {user.staff_code})</>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={() => refetch()}>
            Refresh all
          </Button>
        </div>


        {/* ─────────── SECTION 1: Bank Targets ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Bank Targets ({bankTargets.length})
            </h2>
            <span className="text-xs text-gray-500">From bank_targets.json</span>
          </Card.Header>
          <Card.Body className="p-0">
            {bankTargetsLoading && (
              <div className="px-6 py-4 space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            )}

            {bankTargetsError && !bankTargetsLoading && (
              <div className="px-6 py-4 text-sm text-red-700">{bankTargetsError}</div>
            )}

            {!bankTargetsLoading && !bankTargetsError && bankTargets.length === 0 && (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                No bank targets set for {period}.
              </div>
            )}

            {!bankTargetsLoading && !bankTargetsError && bankTargets.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">KPI</th>
                      <th className="px-4 py-3 text-right">Target</th>
                      <th className="px-4 py-3 text-right">Buffer</th>
                      <th className="px-4 py-3">Unit</th>
                      {isMd && <th className="px-4 py-3 text-right">Actions</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {bankTargets.map((t) => (
                      <BankTargetRow
                        key={t.kpi}
                        target={t}
                        period={period}
                        currencySymbol={currencySymbol}
                        canEdit={isMd}
                        onSaved={() => {
                          toast({ tone: 'success', message: `✓ Updated ${t.kpi}` });
                          void refetch();
                        }}
                        onError={(msg) => toast({ tone: 'danger', message: msg })}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>


        {/* ─────────── SECTION 2: Given to me ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Given to me ({incoming.length})
            </h2>
            <span className="text-xs text-gray-500">Incoming allocations from upline</span>
          </Card.Header>
          <Card.Body className="p-0">
            {incomingLoading && (
              <div className="px-6 py-4 space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-2/3" />
              </div>
            )}

            {incomingError && !incomingLoading && (
              <div className="px-6 py-4 text-sm text-red-700">{incomingError}</div>
            )}

            {!incomingLoading && !incomingError && incoming.length === 0 && (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                No incoming allocations for {period}. Either no upline cascade has reached you yet,
                or you sit at the top of the cascade (MD or unallocated KPI owner).
              </div>
            )}

            {!incomingLoading && !incomingError && incoming.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">KPI</th>
                      <th className="px-4 py-3">From</th>
                      <th className="px-4 py-3 text-right">Amount given</th>
                      <th className="px-4 py-3 text-right">Source total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {incoming.map((a, i) => (
                      <IncomingRow key={`${a.kpi || 'unknown'}-${i}`} allocation={a} symbol={currencySymbol} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>


        {/* ─────────── SECTION 3: My allocations (outgoing) ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              My allocations ({outgoing.length})
            </h2>
            <span className="text-xs text-gray-500">Outgoing cascade to downstream</span>
          </Card.Header>
          <Card.Body className="p-0">
            {outgoingLoading && (
              <div className="px-6 py-4 space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            )}

            {outgoingError && !outgoingLoading && (
              <div className="px-6 py-4 text-sm text-red-700">{outgoingError}</div>
            )}

            {!outgoingLoading && !outgoingError && outgoing.length === 0 && (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                No outgoing allocations for {period}. Either you haven't cascaded any KPIs,
                or you don't have a downline (leaf-role cascade target).
              </div>
            )}

            {!outgoingLoading && !outgoingError && outgoing.length > 0 && (
              <div className="divide-y divide-gray-100">
                {outgoing.map((entry, i) => (
                  <OutgoingRow
                    key={`${entry.kpi}-${i}`}
                    entry={entry}
                    symbol={currencySymbol}
                    canEdit={
                      // γ5b: only the entry's from_code can edit (server enforces;
                      // client mirrors). Compare trimmed strings to avoid whitespace
                      // mismatches between users.json staff codes and cascade JSON.
                      (entry.from_code ?? '').trim() === (user?.staff_code ?? '').trim()
                    }
                    onSaved={() => {
                      toast({ tone: 'success', message: `✓ Allocations saved for ${entry.kpi}` });
                      void refetch();
                    }}
                    onError={(msg) => toast({ tone: 'danger', message: msg })}
                  />
                ))}
              </div>
            )}
          </Card.Body>
        </Card>




      </main>
    </div>
  );
}


// ── Incoming row ─────────────────────────────────────────────────────────

function IncomingRow({ allocation: a, symbol }: { allocation: IncomingAllocation; symbol: string }) {
  const unit = unitForKpiName(a.kpi || '');
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-medium text-gray-900">{a.kpi || '—'}</td>
      <td className="px-4 py-2 text-xs text-gray-700">
        {a.from_name || '—'}
        {a.from_code && <span className="text-gray-400 ml-1">({a.from_code})</span>}
      </td>
      <td className="px-4 py-2 text-right font-mono">
        {formatTargetValue(a.amount, unit, symbol)}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs text-gray-500">
        {a.total_target !== undefined ? formatTargetValue(a.total_target, unit, symbol) : '—'}
      </td>
    </tr>
  );
}


// ── Outgoing row (expandable + editable allocations list) ───────────────
// γ5b (2026-06-12): Each leader can edit their outgoing cascade
// allocations. Server-side gate (γ5a backend) enforces that the
// caller's staff_code == entry.from_code; the client-side flag here
// just hides the affordance when it would 403.

interface OutgoingRowProps {
  entry:       CascadeEntry;
  symbol:      string;
  canEdit:     boolean;
  onSaved:     () => void;
  onError:     (msg: string) => void;
}

function OutgoingRow({ entry, symbol, canEdit, onSaved, onError }: OutgoingRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing,  setEditing]  = useState(false);
  const [saving,   setSaving]   = useState(false);

  // Local draft state — array of { to_code, to_name, amountText }.
  // amountText is a string so user can type freely (cleared input,
  // partial number, etc.) without React fighting them.
  type DraftRow = { to_code: string; to_name: string; amountText: string };
  const initialDraft: DraftRow[] = (entry.allocations ?? []).map((a) => ({
    to_code:    a.to_code ?? '',
    to_name:    a.to_name ?? '',
    amountText: String(a.amount ?? 0),
  }));
  const [draft, setDraft] = useState<DraftRow[]>(initialDraft);

  const unit = unitForKpiName(entry.kpi);
  const status = coverageStatus(entry.total_target, entry.allocated_sum);
  const tone = coverageTone(status);
  const label = coverageLabel(status, entry.total_target, entry.allocated_sum);

  // Live sum of draft amounts (only in edit mode)
  const draftSum = draft.reduce((acc, r) => {
    const n = Number(r.amountText);
    return acc + (Number.isFinite(n) ? n : 0);
  }, 0);
  const draftStatus = coverageStatus(entry.total_target, draftSum);
  const draftTone = coverageTone(draftStatus);
  const draftLabel = coverageLabel(draftStatus, entry.total_target, draftSum);

  const onClickEdit = () => {
    // Reset draft from current entry state
    setDraft(
      (entry.allocations ?? []).map((a) => ({
        to_code:    a.to_code ?? '',
        to_name:    a.to_name ?? '',
        amountText: String(a.amount ?? 0),
      })),
    );
    setEditing(true);
  };

  const onClickCancel = () => {
    setEditing(false);
  };

  const onAddRow = () => {
    setDraft((d) => [...d, { to_code: '', to_name: '', amountText: '0' }]);
  };

  const onRemoveRow = (idx: number) => {
    setDraft((d) => d.filter((_, i) => i !== idx));
  };

  const onChangeField = (idx: number, field: keyof DraftRow, value: string) => {
    setDraft((d) => d.map((row, i) => (i === idx ? { ...row, [field]: value } : row)));
  };

  const onClickSave = async () => {
    // Validate
    for (let i = 0; i < draft.length; i++) {
      const r = draft[i];
      if (!r.to_code.trim()) {
        onError(`Row ${i + 1}: recipient code is required.`);
        return;
      }
      const n = Number(r.amountText);
      if (!Number.isFinite(n) || n < 0) {
        onError(`Row ${i + 1} (${r.to_code}): amount must be a non-negative number.`);
        return;
      }
    }
    setSaving(true);
    try {
      await setCascadeAllocations({
        from_code:    entry.from_code,
        kpi:          entry.kpi,
        period:       entry.period,
        total_target: entry.total_target,
        allocations:  draft.map((r) => ({
          to_code: r.to_code.trim(),
          to_name: r.to_name.trim(),
          amount:  Number(r.amountText),
        })),
      });
      setEditing(false);
      onSaved();
    } catch (e) {
      if (e instanceof ApiValidationError) {
        onError(e.detail || 'Save failed.');
      } else {
        onError(e instanceof Error ? e.message : 'Save failed.');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-6 py-3">
      {/* Collapsed/expanded header */}
      <div
        onClick={() => !editing && setExpanded((x) => !x)}
        className={`flex items-center justify-between gap-3 ${editing ? '' : 'cursor-pointer'}`}
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900">{entry.kpi}</span>
            <Badge tone={tone} size="sm">{label}</Badge>
            {editing && draftStatus !== status && (
              <Badge tone={draftTone} size="sm">draft: {draftLabel}</Badge>
            )}
          </div>
          <div className="text-xs text-gray-600 mt-1">
            Target: <span className="font-mono">{formatTargetValue(entry.total_target, unit, symbol)}</span>
            <span className="text-gray-400 mx-2">→</span>
            Allocated: <span className="font-mono">{formatTargetValue(editing ? draftSum : entry.allocated_sum, unit, symbol)}</span>
            <span className="text-gray-400 ml-2">across {(editing ? draft.length : entry.allocations?.length) || 0} recipients</span>
          </div>
        </div>
        {!editing && (
          <span className="text-gray-400 text-sm">{expanded ? '▾' : '▸'}</span>
        )}
      </div>

      {/* Read-only allocations list (collapsed expanded view) */}
      {expanded && !editing && entry.allocations && entry.allocations.length > 0 && (
        <div className="mt-3 pl-4 border-l-2 border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs text-gray-500 uppercase tracking-wide">Recipients</div>
            {canEdit && (
              <Button variant="ghost" size="sm" onClick={onClickEdit}>
                Edit allocations
              </Button>
            )}
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              <tr>
                <th className="text-left pb-1">Recipient</th>
                <th className="text-right pb-1">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entry.allocations.map((a, i) => (
                <tr key={`${a.to_code || 'unknown'}-${i}`}>
                  <td className="py-1 text-xs text-gray-700">
                    {a.to_name || '—'}
                    {a.to_code && <span className="text-gray-400 ml-1">({a.to_code})</span>}
                  </td>
                  <td className="py-1 text-right font-mono text-xs">
                    {formatTargetValue(a.amount, unit, symbol)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Editable allocations list */}
      {editing && (
        <div className="mt-3 pl-4 border-l-2 border-brand-primary bg-blue-50/30 rounded-r-md py-2 pr-2">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs text-gray-700 font-medium">Editing allocations for {entry.kpi}</div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={onClickCancel} disabled={saving}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={() => void onClickSave()} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              <tr>
                <th className="text-left pb-1 w-1/4">Code</th>
                <th className="text-left pb-1">Name</th>
                <th className="text-right pb-1 w-1/4">Amount</th>
                <th className="pb-1 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {draft.map((row, i) => (
                <tr key={i}>
                  <td className="py-1">
                    <input
                      type="text"
                      value={row.to_code}
                      onChange={(e) => onChangeField(i, 'to_code', e.target.value)}
                      disabled={saving}
                      placeholder="staff_code"
                      className="w-full h-7 px-2 rounded border border-gray-300 bg-white text-xs font-mono focus:outline-none focus:border-brand-primary"
                      autoComplete="off"
                    />
                  </td>
                  <td className="py-1 pl-2">
                    <input
                      type="text"
                      value={row.to_name}
                      onChange={(e) => onChangeField(i, 'to_name', e.target.value)}
                      disabled={saving}
                      placeholder="recipient name (optional)"
                      className="w-full h-7 px-2 rounded border border-gray-300 bg-white text-xs focus:outline-none focus:border-brand-primary"
                      autoComplete="off"
                    />
                  </td>
                  <td className="py-1 pl-2">
                    <input
                      type="number"
                      inputMode="decimal"
                      value={row.amountText}
                      onChange={(e) => onChangeField(i, 'amountText', e.target.value)}
                      disabled={saving}
                      className="w-full h-7 px-2 text-right rounded border border-gray-300 bg-white text-xs font-mono focus:outline-none focus:border-brand-primary"
                      autoComplete="off"
                    />
                  </td>
                  <td className="py-1 pl-2 text-right">
                    <button
                      onClick={() => onRemoveRow(i)}
                      disabled={saving}
                      className="text-xs text-red-600 hover:underline disabled:opacity-50"
                      title="Remove recipient"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={onAddRow} disabled={saving}>
              + Add recipient
            </Button>
            <div className="text-xs text-gray-600">
              Sum: <span className="font-mono">{formatTargetValue(draftSum, unit, symbol)}</span>
              <span className="text-gray-400 mx-1">/</span>
              Target: <span className="font-mono">{formatTargetValue(entry.total_target, unit, symbol)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── BankTargetRow (γ5a) — editable when canEdit ─────────────────────────

interface BankTargetRowProps {
  target:         BankTarget;
  period:         string;
  currencySymbol: string;
  canEdit:        boolean;
  onSaved:        () => void;
  onError:        (msg: string) => void;
}

function BankTargetRow({
  target: t,
  period,
  currencySymbol,
  canEdit,
  onSaved,
  onError,
}: BankTargetRowProps) {
  const [editing,    setEditing]    = useState<boolean>(false);
  const [targetText, setTargetText] = useState<string>(String(t.target));
  const [bufferText, setBufferText] = useState<string>(String(t.buffer_pct));
  const [saving,     setSaving]     = useState<boolean>(false);

  // Reset edit-state if the underlying target prop changes (e.g. after refetch)
  // — handled by re-rendering with fresh defaults when not editing.

  const onClickEdit = () => {
    setTargetText(String(t.target));
    setBufferText(String(t.buffer_pct));
    setEditing(true);
  };

  const onClickCancel = () => {
    setEditing(false);
  };

  const onClickSave = async () => {
    const targetNum = Number(targetText);
    const bufferNum = Number(bufferText);
    if (!Number.isFinite(targetNum) || targetNum < 0) {
      onError('Target must be a non-negative number.');
      return;
    }
    if (!Number.isFinite(bufferNum) || bufferNum < 0 || bufferNum > 100) {
      onError('Buffer must be a number between 0 and 100.');
      return;
    }
    setSaving(true);
    try {
      await setBankTarget({
        kpi:        t.kpi,
        period:     period,
        target:     targetNum,
        buffer_pct: bufferNum,
      });
      setEditing(false);
      onSaved();
    } catch (e) {
      if (e instanceof ApiValidationError) {
        onError(e.detail || 'Save failed.');
      } else {
        onError(e instanceof Error ? e.message : 'Save failed.');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <tr>
        <td className="px-4 py-2 font-medium text-gray-900">{t.kpi}</td>
        <td className="px-4 py-2 text-right font-mono">
          {formatTargetValue(t.target, t.unit, currencySymbol)}
        </td>
        <td className="px-4 py-2 text-right font-mono text-xs text-gray-600">
          {t.buffer_pct ? `${t.buffer_pct}%` : '—'}
        </td>
        <td className="px-4 py-2 text-xs text-gray-500">{t.unit}</td>
        {canEdit && (
          <td className="px-4 py-2 text-right">
            <Button variant="ghost" size="sm" onClick={onClickEdit}>
              Edit
            </Button>
          </td>
        )}
      </tr>
    );
  }

  // Editing row
  return (
    <tr className="bg-blue-50/30">
      <td className="px-4 py-2 font-medium text-gray-900">{t.kpi}</td>
      <td className="px-4 py-2 text-right">
        <input
          type="number"
          inputMode="decimal"
          value={targetText}
          onChange={(e) => setTargetText(e.target.value)}
          disabled={saving}
          className="w-full h-8 px-2 text-right rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          autoComplete="off"
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          type="number"
          inputMode="decimal"
          value={bufferText}
          onChange={(e) => setBufferText(e.target.value)}
          disabled={saving}
          className="w-full h-8 px-2 text-right rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          autoComplete="off"
        />
      </td>
      <td className="px-4 py-2 text-xs text-gray-500">{t.unit}</td>
      <td className="px-4 py-2 text-right">
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={onClickCancel} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={() => void onClickSave()} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </td>
    </tr>
  );
}
