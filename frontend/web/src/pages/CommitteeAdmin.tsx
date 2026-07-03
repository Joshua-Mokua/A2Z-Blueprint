import { useEffect, useMemo, useState } from 'react';
import { StaffPicker } from '@/components/StaffPicker';
import type { StaffMember } from '@/lib/api';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchCommitteePalette,
  upsertCommittee,
  deleteCommittee,
  seedCommitteePalette,
  setRequireMcc,
  type CommitteeDef,
} from '@/lib/api';

const EMPTY: CommitteeDef = {
  code: '', name: '', chaired_by: '', recording_mode: 'voting',
  voting_rule: 'SIMPLE_MAJORITY', amount_threshold_kes: 0, members: [],
};

export default function CommitteeAdmin() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const canAdmin = useMemo(() => {
    if (isAdmin) return true;
    const r = (user?.role ?? '').toLowerCase();
    return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
  }, [user, isAdmin]);

  const [committees, setCommittees] = useState<CommitteeDef[]>([]);
  const [modes, setModes] = useState<string[]>(['single', 'voting']);
  const [rules, setRules] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<CommitteeDef | null>(null);
  const [requireMcc, setRequireMccState] = useState(true);
  const [savingMcc, setSavingMcc] = useState(false);

  async function load() {
    setLoading(true); setError(null);
    try {
      const d = await fetchCommitteePalette();
      setCommittees(d.committees);
      setModes(d.recording_modes);
      setRules(d.voting_rules);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load committees');
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const columns: Column<CommitteeDef>[] = [
    { key: 'code', header: 'Code' },
    { key: 'name', header: 'Name' },
    { key: 'chaired_by', header: 'Chair', render: (c) => c.chaired_by || '—' },
    { key: 'recording_mode', header: 'Recording' },
    { key: 'voting_rule', header: 'Voting rule' },
    { key: 'amount_threshold_kes', header: 'Auto-trigger >= (KES)',
      render: (c) => c.amount_threshold_kes ? c.amount_threshold_kes.toLocaleString() : '—' },
    { key: 'members', header: 'Members', render: (c) => String((c.members ?? []).length) },
    { key: 'code', header: '', render: (c) => (
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => setDraft({ ...c })}>Edit</Button>
        <Button variant="ghost" size="sm" onClick={() => void remove(c.code)}>Delete</Button>
      </div>
    ) },
  ];

  async function seed() {
    setSaving(true);
    try {
      await seedCommitteePalette();
      toast({ tone: 'success', message: 'Seeded default committees.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Seed failed' });
    } finally { setSaving(false); }
  }

  async function remove(code: string) {
    setSaving(true);
    try {
      await deleteCommittee(code);
      toast({ tone: 'success', message: `Removed ${code}.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Delete failed' });
    } finally { setSaving(false); }
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      await upsertCommittee(draft);
      toast({ tone: 'success', message: `Saved ${draft.code}.` });
      setDraft(null);
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' });
    } finally { setSaving(false); }
  }

  function setMemberFromStaff(i: number, sm: StaffMember | null) {
    if (!draft) return;
    const members = [...(draft.members ?? [])];
    members[i] = {
      ...members[i],
      name: sm?.name ?? '',
      role: sm?.role ?? '',
      staff_code: sm?.staff_code ?? '',
    };
    setDraft({ ...draft, members });
  }
  function toggleFunnel(i: number, value: boolean) {
    if (!draft) return;
    const members = [...(draft.members ?? [])];
    members[i] = { ...members[i], full_funnel: value };
    setDraft({ ...draft, members });
  }

  if (!canAdmin) {
    return <Card><Card.Body><div className="text-sm text-gray-600">No access to committee configuration.</div></Card.Body></Card>;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Credit Committees"
        subtitle="The palette of credit committees. Each product's journey opens the gates it needs. Renamable and fully editable."
      />

      {error && (
        <Card><Card.Body>
          <div className="text-sm text-red-600">{error}</div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>Retry</Button>
        </Card.Body></Card>
      )}

      {/* C1b: ladder policy toggle */}
      <Card stripe="accent"><Card.Body>
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" checked={requireMcc} className="mt-1"
            onChange={async (e) => {
              const v = e.target.checked; setRequireMccState(v); setSavingMcc(true);
              try { await setRequireMcc(v); toast({ tone: 'success', message: 'Ladder policy saved.' }); }
              catch { toast({ tone: 'danger', message: 'Could not save.' }); setRequireMccState(!v); }
              finally { setSavingMcc(false); }
            }} disabled={savingMcc} />
          <div>
            <div className="text-sm font-medium text-gray-900">Require MCC before Board / Group</div>
            <div className="text-xs text-gray-500">When on (recommended), any case whose limit needs the Board or Group committee must first pass through the Management Credit Committee, whose verdict is captured before it climbs. When off, cases route directly to the committee their limit requires.</div>
          </div>
        </label>
      </Card.Body></Card>

      <Card><Card.Body>
        <div className="mb-3 flex justify-between">
          <p className="text-sm text-gray-600">{committees.length} committee(s)</p>
          <div className="flex gap-2">
            {committees.length === 0 && (
              <Button variant="ghost" onClick={() => void seed()} disabled={saving}>Seed defaults</Button>
            )}
            <Button onClick={() => setDraft({ ...EMPTY })} disabled={saving}>+ Add committee</Button>
          </div>
        </div>
        <Table columns={columns} rows={committees} rowKey="code" loading={loading} empty="No committees yet — seed the defaults or add one." />
      </Card.Body></Card>

      {draft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => !saving && setDraft(null)}>
          <div className="max-h-[85vh] w-full max-w-lg overflow-auto rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-3 text-lg font-semibold">{draft.code ? `Edit ${draft.code}` : 'New committee'}</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <label className="col-span-1">Code
                <input className="mt-1 w-full rounded border px-2 py-1.5" value={draft.code}
                  onChange={(e) => setDraft({ ...draft, code: e.target.value })} />
              </label>
              <label className="col-span-1">Chair (optional)
                <input className="mt-1 w-full rounded border px-2 py-1.5" value={draft.chaired_by ?? ''}
                  onChange={(e) => setDraft({ ...draft, chaired_by: e.target.value })} />
              </label>
              <label className="col-span-2">Name
                <input className="mt-1 w-full rounded border px-2 py-1.5" value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </label>
              <label className="col-span-1">Recording mode
                <select className="mt-1 w-full rounded border px-2 py-1.5" value={draft.recording_mode}
                  onChange={(e) => setDraft({ ...draft, recording_mode: e.target.value })}>
                  {modes.map((m) => <option key={m} value={m}>{m === 'voting' ? 'Each member votes' : 'Single record'}</option>)}
                </select>
              </label>
              <label className="col-span-1">Voting rule
                <select className="mt-1 w-full rounded border px-2 py-1.5" value={draft.voting_rule}
                  onChange={(e) => setDraft({ ...draft, voting_rule: e.target.value })}>
                  {rules.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              <label className="col-span-2">Auto-trigger at amount &gt;= (KES, 0 = none)
                <input type="number" className="mt-1 w-full rounded border px-2 py-1.5" value={draft.amount_threshold_kes}
                  onChange={(e) => setDraft({ ...draft, amount_threshold_kes: Number(e.target.value) })} />
              </label>
            </div>

            <div className="mt-4">
              <div className="mb-1 flex items-center justify-between">
                <p className="text-sm font-medium">Members (name + role + staff code — staff code lets them be notified & record a pre-read)</p>
                <Button variant="ghost" size="sm"
                  onClick={() => setDraft({ ...draft, members: [...(draft.members ?? []), { name: '', role: '', staff_code: '' }] })}>
                  + Member
                </Button>
              </div>
              <div className="space-y-2">
                {(draft.members ?? []).map((m, i) => (
                  <div key={i} className="flex gap-2">
                    <div className="flex-1 min-w-0">
                      {m.name ? (
                        <div className="flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-sm">
                          <span className="truncate">
                            <span className="font-medium">{m.name}</span>
                            <span className="text-gray-500">{m.staff_code ? ` · ${m.staff_code}` : ''}{m.role ? ` · ${m.role}` : ''}</span>
                          </span>
                          <button type="button" className="text-xs text-brand-primary hover:underline shrink-0"
                            onClick={() => setMemberFromStaff(i, null)}>Change</button>
                        </div>
                      ) : (
                        <StaffPicker value={null} onChange={(sm) => setMemberFromStaff(i, sm)} />
                      )}
                    </div>
                    <label className="flex items-center gap-1 text-xs text-gray-600 whitespace-nowrap" title="EXCO full-funnel visibility (planning view like the MD)">
                      <input type="checkbox" checked={!!m.full_funnel}
                        onChange={(e) => toggleFunnel(i, e.target.checked)} />
                      EXCO view
                    </label>
                    <Button variant="ghost" size="sm"
                      onClick={() => setDraft({ ...draft, members: (draft.members ?? []).filter((_, j) => j !== i) })}>
                      x
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDraft(null)} disabled={saving}>Cancel</Button>
              <Button onClick={() => void save()} disabled={saving || !draft.code.trim() || !draft.name.trim()}>
                {saving ? 'Saving…' : 'Save committee'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
