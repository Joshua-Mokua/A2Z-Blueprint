// The prospect record — ONE card.
//
// RULING (2026-08-11): "collapse these into one detail card that will be
// applicable even when one is creating an entry ... the one they work on and
// save becomes the detail page, that becomes our one table that is saved and
// when validated submitted to the validated side."
//
// Three cards asked a reader to hold the same business in their head three
// times. What the other two carried that mattered — status, provenance, the
// actions, and what anybody has found out — lives here: a header strip, four
// sections, and sources at the foot.
//
// EVERY ENTRY PASSES THE VALIDATION GATE. Nothing is born validated, however
// complete it arrives, because validation is somebody looking — not a score
// crossing a line.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchProspect, addProspectFact, claimProspect, validateProspect,
  updateProspect, fetchCompletenessMatrix,
  type ProspectDetail as Detail, type ProspectFact,
} from '@/lib/api';

type Row = {
  key: string; field: string; label: string;
  kind?: 'text' | 'select' | 'number' | 'area';
  options?: 'segments' | 'sectors' | 'counties';
  placeholder?: string;
};

// Sections pool related questions, so a block can be finished in one sitting
// rather than facing fifteen rows that each demand a different kind of digging.
const SECTIONS: { title: string; hint: string; rows: Row[] }[] = [
  {
    title: 'Identity',
    hint: 'Who this is, in the terms the bank organises itself around.',
    rows: [
      { key: 'name', field: 'name', label: 'Legal name' },
      { key: 'segment', field: 'segment', label: 'Segment', kind: 'select', options: 'segments' },
      { key: 'sector', field: 'sector', label: 'Sector', kind: 'select', options: 'sectors' },
      { key: 'business_activity', field: 'business_activity', label: 'What they actually do',
        kind: 'area', placeholder: 'Grain milling and animal feeds; supplies three counties' },
    ],
  },
  {
    title: 'Where to find them',
    hint: 'Enough for somebody to turn up, or to call.',
    rows: [
      { key: 'county', field: 'town', label: 'County', kind: 'select', options: 'counties' },
      { key: 'physical_address', field: 'physical_address', label: 'Physical address',
        placeholder: 'Ngano House, Industrial Area' },
      { key: 'branches', field: 'branches', label: 'Branches or footprint',
        placeholder: '12 branches across 6 counties' },
      { key: 'phone', field: 'contact_phone', label: 'Phone', placeholder: '0722 000 000' },
      { key: 'email', field: 'contact_email', label: 'Email', placeholder: 'info@example.co.ke' },
      { key: 'online_presence', field: 'website', label: 'Website', placeholder: 'example.co.ke' },
    ],
  },
  {
    title: 'Ownership and people',
    hint: 'Who decides, and who they answer to.',
    rows: [
      { key: 'decision_maker', field: 'contact_name', label: 'Decision maker and role',
        placeholder: 'Jane Wanjiku — CEO' },
      { key: '', field: 'ownership', label: 'Ownership or affiliation',
        placeholder: 'Member-owned; affiliated to KUSCCO' },
      { key: 'established', field: 'established', label: 'Year established',
        kind: 'number', placeholder: '1974' },
    ],
  },
  {
    title: 'The business',
    hint: 'What decides whether this is worth anyone\u2019s time.',
    rows: [
      { key: 'size_indicator', field: 'estimated_value',
        label: 'Size (turnover, assets or members)', kind: 'number' },
      { key: 'existing_banker', field: 'existing_banker', label: 'Banks with now',
        placeholder: 'KCB, Co-operative Bank' },
      { key: 'value_chain', field: 'value_chain', label: 'Value chain and potential needs',
        kind: 'area',
        placeholder: 'Buys maize from farmer groups; sells to schools and retailers. '
          + 'Likely needs: working capital, collection accounts.' },
    ],
  },
];

const KINDS = [
  { key: 'contact', label: 'Contact' },
  { key: 'relationship', label: 'Director / officer' },
  { key: 'financial', label: 'Financial' },
  { key: 'association', label: 'Membership' },
  { key: 'filing', label: 'Filing' },
  { key: 'news', label: 'News' },
  { key: 'note', label: 'Note' },
];

export default function ProspectDetail() {
  const { prospectId = '' } = useParams();
  const nav = useNavigate();
  const { toast } = useToast();

  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [lists, setLists] = useState<{ segments: string[]; sectors: string[]; counties: string[] }>(
    { segments: [], sectors: [], counties: [] });
  const [fact, setFact] = useState({
    kind: 'contact', title: '', source: '', url: '', occurred_on: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchProspect(prospectId));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [prospectId, toast]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        const m = await fetchCompletenessMatrix();
        setLists({ segments: m.segments ?? [], sectors: m.sectors ?? [], counties: m.counties ?? [] });
      } catch { /* the form still works, just without the pickers */ }
    })();
  }, []);

  const p = data?.prospect;
  const c = data?.completeness;
  const facts: ProspectFact[] = data?.card?.items ?? [];

  // AUTOSAVE ON BLUR, but only while the record is under validation. That set
  // exists to be filled in, and making somebody hunt for a Save button after
  // every field is how half-typed records get abandoned.
  //
  // A VALIDATED record is never autosaved - it needs the password, and
  // prompting for it the moment somebody tabs out of a field would be
  // maddening. There, Save stays explicit.
  async function autosave(field: string) {
    if (c?.validated) return;
    if (!(field in edit)) return;
    const value = edit[field];
    try {
      await updateProspect(prospectId, { [field]: value });
      setEdit((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
      await load();
    } catch (e) {
      // Left in `edit` so the typing is not lost and Save can retry it.
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save.' });
    }
  }

  async function save() {
    // The password is asked for ONLY on a validated record. The working set
    // exists to be filled in, and friction there stops the backfilling.
    let pw = '';
    if (c?.validated) {
      pw = window.prompt('This is a validated record. Enter the warehouse password to change it.') || '';
      if (!pw) return;
    }
    setBusy(true);
    try {
      await updateProspect(prospectId, edit, pw);
      toast({ tone: 'success', message: 'Saved.' });
      setEdit({});
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save.' });
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    try {
      await validateProspect(prospectId);
      toast({ tone: 'success', message: 'Validated — this is now a usable record.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not validate.' });
    } finally {
      setBusy(false);
    }
  }

  async function pursue() {
    setBusy(true);
    try {
      const r = await claimProspect(prospectId);
      toast({
        tone: 'success',
        message: `Yours. ${r.referrer_name || 'Whoever listed it'} is credited as the referrer.`,
      });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not claim it.' });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function addFact() {
    if (!fact.title.trim() || !fact.source.trim()) {
      toast({ tone: 'danger', message: 'A source needs what it says and where it came from.' });
      return;
    }
    setBusy(true);
    try {
      await addProspectFact(prospectId, fact);
      setFact({ ...fact, title: '', url: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not add.' });
    } finally {
      setBusy(false);
    }
  }

  const box = 'mt-1 w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#0082BB] ';
  const small = 'h-8 w-full rounded-lg border border-gray-200 px-2 text-xs focus:outline-none focus:ring-1 focus:ring-[#0082BB]';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' },
                      { label: 'Deals Warehouse' }, { label: p?.name ?? 'Prospect' }]}
        title={p?.name ?? 'Prospect'}
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading…</p>}
        {!loading && !p && (
          <p className="py-10 text-center text-sm text-gray-400">No such prospect.</p>
        )}

        {p && (
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold text-gray-900">{p.name}</h2>
                  <span className={'rounded-full px-2.5 py-0.5 text-[11px] ' + (
                    c?.validated ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-[#FEF6E7] text-[#854F0B]')}>
                    {c?.validated ? `validated by ${c.validated_by}` : 'under validation'}
                  </span>
                  <span className={'rounded-full px-2.5 py-0.5 text-[11px] ' + (
                    p.status === 'available' ? 'bg-[#E6F1FB] text-[#0C447C]' : 'bg-gray-100 text-gray-600')}>
                    {p.status === 'available' ? 'unclaimed'
                      : p.claimed_by_name ? `with ${p.claimed_by_name}` : p.status}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-gray-500">
                  {p.source_event || 'Entered by hand'}
                  {p.created_at ? ` · ${String(p.created_at).slice(0, 10)}` : ''}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className={'text-lg font-semibold tabular-nums ' + (
                    c?.validated ? 'text-[#3B6D11]' : 'text-gray-800')}>{c?.score ?? 0}%</div>
                  <div className="text-[10px] text-gray-400">
                    {c?.answered ?? 0}/{c?.of ?? 15} answered
                  </div>
                </div>
                {/* PURSUE ONLY ON A VALIDATED RECORD (ruling 2026-08-11).
                    Sending somebody to call a business whose details nobody has
                    checked is how the warehouse loses trust on the first bad
                    call - and one bad call costs more than the prospect was
                    worth. */}
                {p.status === 'available' && c?.validated && (
                  <Button size="sm" variant="secondary" disabled={busy}
                          onClick={() => void pursue()}>Pursue</Button>
                )}
                {p.status === 'available' && !c?.validated && (
                  <span className="text-[10px] text-gray-400">
                    validate before pursuing
                  </span>
                )}
                {!c?.validated && (
                  <Button size="sm" disabled={busy || !c?.complete}
                          title={c?.complete ? '' : `${c?.threshold ?? 80}% needed first`}
                          onClick={() => void validate()}>Validate</Button>
                )}
              </div>
            </div>

            <div className="h-1.5 bg-gray-100">
              <div className={'h-full ' + (
                c?.validated ? 'bg-[#3B6D11]'
                  : (c?.score ?? 0) >= 80 ? 'bg-[#BED600]'
                    : (c?.score ?? 0) >= 40 ? 'bg-[#E0A02B]' : 'bg-gray-300')}
                   style={{ width: `${Math.max(2, c?.score ?? 0)}%` }} />
            </div>

            <div className="space-y-4 p-4">
              {c?.stale_validation && (
                <p className="rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                  This record changed after it was validated, so it is no longer
                  the record that was checked. Worth validating again.
                </p>
              )}

              {SECTIONS.map((sec) => {
                const done = sec.rows.filter((r) => r.key && c?.have.includes(r.key)).length;
                const scored = sec.rows.filter((r) => r.key).length;
                return (
                  <div key={sec.title} className="overflow-hidden rounded-xl border border-gray-200">
                    <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/70 px-3 py-2">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-wide text-[#003D57]">
                          {sec.title}
                        </div>
                        <div className="text-[10px] text-gray-500">{sec.hint}</div>
                      </div>
                      {scored > 0 && (
                        <span className={'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ' + (
                          done === scored ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-[#FEF6E7] text-[#854F0B]')}>
                          {done}/{scored}
                        </span>
                      )}
                    </div>

                    <div className="grid gap-3 p-3 sm:grid-cols-2">
                      {sec.rows.map((row) => {
                        const answered = row.key ? Boolean(c?.have.includes(row.key)) : true;
                        const cur = edit[row.field]
                          ?? String((p as unknown as Record<string, unknown>)[row.field] ?? '');
                        const set = (v: string) => setEdit({ ...edit, [row.field]: v });
                        const cls = box + (answered ? 'border-gray-200' : 'border-[#F0D9A8] bg-[#FFFDF8]');
                        const opts = row.options === 'segments' ? lists.segments
                          : row.options === 'sectors' ? lists.sectors
                            : row.options === 'counties' ? lists.counties : [];
                        return (
                          <label key={row.field}
                                 className={'block text-[11px] text-gray-600 '
                                   + (row.kind === 'area' ? 'sm:col-span-2' : '')}>
                            <span className="flex items-center gap-1.5">
                              <span className={'h-1.5 w-1.5 rounded-full ' + (
                                answered ? 'bg-[#3B6D11]' : 'bg-[#E0A02B]')} />
                              {row.label}
                            </span>
                            {row.kind === 'select' ? (
                              // A picker saves on CHANGE - there is no
                              // half-typed state to protect.
                              <select className={cls} value={cur}
                                      onChange={(e) => {
                                        set(e.target.value);
                                        setTimeout(() => void autosave(row.field), 0);
                                      }}>
                                <option value="">Select…</option>
                                {opts.map((o) => <option key={o} value={o}>{o}</option>)}
                              </select>
                            ) : row.kind === 'area' ? (
                              <textarea rows={2} className={cls} value={cur}
                                        placeholder={row.placeholder}
                                        onBlur={() => void autosave(row.field)}
                                        onChange={(e) => set(e.target.value)} />
                            ) : (
                              <input className={cls} value={cur} placeholder={row.placeholder}
                                     inputMode={row.kind === 'number' ? 'numeric' : undefined}
                                     onBlur={() => void autosave(row.field)}
                                     onChange={(e) => set(e.target.value)} />
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}

              {/* Every warehouse eventually meets a business whose important
                  fact has no column, and a record with nowhere to put it loses
                  the fact. */}
              <label className="block text-[11px] text-gray-600">
                Anything else worth knowing
                <textarea rows={3}
                          className={box + 'border-gray-200'}
                          placeholder="Seasonality, known issues, group structure, anything the fields above do not cover…"
                          value={edit.additional_information
                            ?? String((p as unknown as Record<string, unknown>).additional_information ?? '')}
                          onBlur={() => void autosave('additional_information')}
                          onChange={(e) => setEdit({ ...edit, additional_information: e.target.value })} />
              </label>

              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-gray-400">
                  {c?.validated
                    ? 'Validated — saving needs the warehouse password.'
                    : `Saves as you go. ${c?.threshold ?? 80}% opens validation.`}
                </span>
                <Button size="sm" disabled={busy || Object.keys(edit).length === 0}
                        onClick={() => void save()}>
                  {busy ? 'Saving…' : 'Save'}
                </Button>
              </div>

              {/* SOURCES, folded in rather than sitting in a card of their own.
                  Each is a fact with a date and a place it came from - never a
                  copied article. */}
              <div className="overflow-hidden rounded-xl border border-gray-200">
                <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/70 px-3 py-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[#003D57]">
                    Sources and findings
                  </div>
                  <span className="text-[10px] text-gray-500">
                    {facts.length} {facts.length === 1 ? 'entry' : 'entries'}
                  </span>
                </div>

                <div className="space-y-2 p-3">
                  <div className="grid gap-2 sm:grid-cols-6">
                    <select className={small} value={fact.kind}
                            onChange={(e) => setFact({ ...fact, kind: e.target.value })}>
                      {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
                    </select>
                    <input className={`${small} sm:col-span-2`} value={fact.title}
                           placeholder="What it says"
                           onChange={(e) => setFact({ ...fact, title: e.target.value })} />
                    <input className={small} value={fact.source}
                           placeholder="Where from"
                           onChange={(e) => setFact({ ...fact, source: e.target.value })} />
                    <input type="date" className={small} value={fact.occurred_on}
                           onChange={(e) => setFact({ ...fact, occurred_on: e.target.value })} />
                    <Button size="sm" disabled={busy} onClick={() => void addFact()}>Add</Button>
                  </div>

                  {facts.length === 0 ? (
                    <p className="py-3 text-center text-[11px] text-gray-400">
                      Nothing recorded yet. Whoever finds something out records it here.
                    </p>
                  ) : (
                    <ul className="divide-y divide-gray-100">
                      {facts.map((f) => (
                        <li key={f.id} className="flex flex-wrap items-baseline gap-2 py-1.5 text-xs">
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-600">
                            {KINDS.find((k) => k.key === f.kind)?.label ?? f.kind}
                          </span>
                          <span className="font-medium text-gray-900">{f.title}</span>
                          <span className="text-[10px] text-gray-400">
                            {f.source}{f.occurred_on ? ` · ${f.occurred_on}` : ''}
                            {f.added_by ? ` · ${f.added_by}` : ''}
                          </span>
                          {f.url && (
                            <a href={f.url} target="_blank" rel="noreferrer"
                               className="text-[10px] text-brand-primary hover:underline">open</a>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <button type="button"
                      className="w-full text-center text-xs text-gray-500 hover:text-gray-700"
                      onClick={() => nav('/pipeline/warehouse')}>
                Back to the shelf
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
