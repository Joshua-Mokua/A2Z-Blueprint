import { useCallback, useEffect, useState } from 'react';

/** Stage 13: opt-in UI for the Stage 11/12 case-scoped validation routes.
 * No disbursement controls; the backend remains the sole authority.
 */
type InboxItem = { case_id: string; roles: string[]; status: string };
type Readiness = { missing_roles?: string[]; blocked?: boolean; [key: string]: unknown };
const BASE = '/api/credit-admin';
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init, credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json() as { detail?: unknown }; if (typeof body.detail === 'string') message = body.detail; } catch { /* no detail */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export function AvailmentValidationPanel({ caseId }: { caseId: string }) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [role, setRole] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [mode, setMode] = useState<'physical' | 'electronic'>('electronic');
  const [rolesText, setRolesText] = useState('');
  const [isCadMaker, setIsCadMaker] = useState(false);
  const refresh = useCallback(async () => {
    setError('');
    const inbox = await request<{ items: InboxItem[] }>('/availment-validation/inbox');
    const all = Array.isArray(inbox.items) ? inbox.items : [];
    setItems(all);
    const matching = all.find(x => String(x.case_id) === String(caseId));
    if (matching?.roles.length) setRole(current => matching.roles.includes(current) ? current : matching.roles[0]);
    try { setReadiness(await request<Readiness>(`/cases/${encodeURIComponent(caseId)}/availment-validation/readiness`)); }
    catch { setReadiness(null); /* may be unassigned to case */ }
  }, [caseId]);
  useEffect(() => { void refresh().catch(e => setError(e instanceof Error ? e.message : 'Validation inbox unavailable')); }, [refresh]);
  const mine = items.find(x => String(x.case_id) === String(caseId));
  async function decide(action: 'validate' | 'return' | 'reject') {
    if (!role || (action !== 'validate' && !note.trim())) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await request(`/cases/${encodeURIComponent(caseId)}/availment-validation/decision`, {
        method: 'POST', body: JSON.stringify({ role, action, note: note.trim() }),
      });
      setNotice(`${action} recorded by the server. This does not release funds.`);
      setNote(''); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Decision failed'); }
    finally { setBusy(false); }
  }
  async function configure() {
    const required_roles = rolesText.split(',').map(x => x.trim()).filter(Boolean);
    if (!required_roles.length) { setError('Enter the bank-approved validation role names.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      await request(`/cases/${encodeURIComponent(caseId)}/availment-validation/configure`, {
        method: 'POST', body: JSON.stringify({ mode, required_roles }),
      });
      setNotice('Validation mode configured by the server. Physical evidence verification is not available yet.');
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Configuration failed'); }
    finally { setBusy(false); }
  }
  return <section aria-label="Availment validation circulation" className="rounded-lg border border-gray-200 p-4 space-y-3">
    <h3 className="font-semibold text-sm">Availment Memo — validation circulation</h3>
    <p className="text-xs text-gray-600">Case-scoped electronic inbox. The bank's required validators and assignments must be configured by an administrator. No TROPS release is performed here.</p>
    <button type="button" className="text-sm underline" onClick={() => void refresh().catch(e => setError(String(e)))} disabled={busy}>Refresh inbox and readiness</button>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="text-sm text-green-700">{notice}</p>}
    <div className="text-sm">My assigned cases: {items.length}. {mine ? `This case awaits: ${mine.roles.join(', ')}` : 'No pending validation assigned to you for this case.'}</div>
    {readiness && <div className="text-xs text-gray-700">Outstanding roles: {(readiness.missing_roles ?? []).join(', ') || 'None reported'} · Blocked: {String(Boolean(readiness.blocked))}</div>}
    {mine && <div className="space-y-2 border-t pt-3">
      <label className="block text-xs">My assigned validation role
        <select aria-label="Validation role" className="mt-1 block w-full rounded border p-2" value={role} onChange={e => setRole(e.target.value)}>{mine.roles.map(r => <option key={r} value={r}>{r}</option>)}</select>
      </label>
      <label className="block text-xs">Decision remarks
        <textarea className="mt-1 block w-full rounded border p-2" rows={2} value={note} onChange={e => setNote(e.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">{(['validate', 'return', 'reject'] as const).map(action => <button key={action} type="button" disabled={busy || !role || (action !== 'validate' && !note.trim())} className="rounded border px-3 py-2 text-sm disabled:opacity-50" onClick={() => void decide(action)}>{action === 'validate' ? 'Validate' : action === 'return' ? 'Return for correction' : 'Reject'}</button>)}</div>
    </div>}
    <div className="border-t pt-3 space-y-2">
      <label className="flex gap-2 text-xs items-center"><input type="checkbox" checked={isCadMaker} onChange={e => setIsCadMaker(e.target.checked)} /> Show CAD maker configuration (server enforces permissions)</label>
      {isCadMaker && <><label className="block text-xs">Validation mode
        <select className="mt-1 block w-full rounded border p-2" value={mode} onChange={e => setMode(e.target.value as 'physical' | 'electronic')}><option value="electronic">Electronic</option><option value="physical">Physical</option></select>
      </label><label className="block text-xs">Required validation roles (comma-separated, exact approved role names)
        <input className="mt-1 block w-full rounded border p-2" value={rolesText} onChange={e => setRolesText(e.target.value)} />
      </label><button type="button" className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={() => void configure()}>Configure validation</button></>}
    </div>
  </section>;
}
