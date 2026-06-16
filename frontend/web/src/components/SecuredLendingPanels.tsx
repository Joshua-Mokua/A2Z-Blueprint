// React-A2 (P4 UI) — secured-lending entry panels for the Credit Admin case
// detail. Each panel is self-contained: reads the current case, calls the P4
// fetchers, and invokes onChange (parent refetch) on success. Renders only the
// pieces relevant to a secured facility where useful.

import { useState } from 'react';
import {
  classifyFacility, linkCollateral, unlinkCollateral, classifyCondition,
  legalAssign, legalComment, legalOutcome, addPerfection, updatePerfection,
  addInsurance, ApiValidationError, AuthExpiredError,
} from '@/lib/api';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import type {
  CreditAdminCase, SecurityClassification, CreditAdminCondition,
} from '@/types/creditAdmin';

// Collateral types — mirror the admin Credit Policy Matrix keys.
const COLLATERAL_TYPES = [
  'Cash / Fixed Deposit', 'Residential Property', 'Commercial Property',
  'Motor Vehicle', 'Debenture', 'Stock / Inventory',
];

const CLASS_TONE: Record<SecurityClassification, 'neutral' | 'warning' | 'success' | 'brand'> = {
  unsecured: 'neutral', partially_secured: 'warning',
  fully_secured: 'success', over_secured: 'brand',
};

function useAction(onChange?: () => void) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<unknown>, okMsg: string): Promise<boolean> {
    setBusy(true);
    try {
      await fn();
      toast.toast({ tone: 'success', message: okMsg });
      onChange?.();
      return true;
    } catch (e) {
      const msg = e instanceof ApiValidationError ? e.detail
        : e instanceof AuthExpiredError ? 'Session expired. Please sign in again.'
        : e instanceof Error ? e.message : 'Action failed.';
      toast.toast({ tone: 'danger', message: msg });
      return false;
    } finally { setBusy(false); }
  }
  return { busy, run };
}

const sel = 'w-full border rounded px-2 py-2 text-sm';
const lbl = 'text-sm block';
const cap = 'block mb-1 text-gray-600';

interface PanelProps { caseRecord: CreditAdminCase; onChange?: () => void }

// ── 1. Facility classification ──────────────────────────────────────────
export function FacilityClassificationPanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const [type, setType] = useState(caseRecord.facility_security_type || 'unsecured');
  const [subtype, setSubtype] = useState(caseRecord.security_subtype || '');
  const cls = caseRecord.security_classification;
  return (
    <Card className="mt-6"><Card.Header>Facility classification</Card.Header><Card.Body>
      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-gray-500">Current:</span>
        <Badge tone={caseRecord.facility_security_type === 'secured' ? 'brand' : 'neutral'}>
          {caseRecord.facility_security_type || 'unsecured'}
        </Badge>
        {cls && <Badge tone={CLASS_TONE[cls]}>{cls.replace('_', '-')}</Badge>}
        {caseRecord.coverage_ratio != null && (
          <span className="text-gray-500">coverage {caseRecord.coverage_ratio}× / required {caseRecord.required_ratio ?? '—'}×</span>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
        <label className={lbl}><span className={cap}>Security type</span>
          <select className={sel} value={type} onChange={(e) => setType(e.target.value as 'unsecured' | 'secured')}>
            <option value="unsecured">unsecured</option>
            <option value="secured">secured</option>
          </select></label>
        <label className={lbl}><span className={cap}>Subtype</span>
          <Input value={subtype} onChange={(e) => setSubtype(e.target.value)} placeholder="debenture / mortgage / …" /></label>
        <Button disabled={busy} onClick={() => run(
          () => classifyFacility(caseRecord.id, { facility_security_type: type, security_subtype: subtype || undefined }),
          'Facility classification saved.')}>Save classification</Button>
      </div>
    </Card.Body></Card>
  );
}

// ── 2. Collateral linkage ───────────────────────────────────────────────
export function CollateralPanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const [cid, setCid] = useState('');
  const [ctype, setCtype] = useState(COLLATERAL_TYPES[0]);
  const [fsv, setFsv] = useState('');
  const [vdate, setVdate] = useState('');
  const links = caseRecord.linked_collateral || [];
  return (
    <Card className="mt-6"><Card.Header>Collateral &amp; coverage</Card.Header><Card.Body>
      {links.length > 0 ? (
        <table className="w-full text-sm mb-4">
          <thead><tr className="text-left text-gray-500 border-b">
            <th className="py-1 pr-3">ID</th><th className="py-1 pr-3">Type</th>
            <th className="py-1 pr-3">FSV</th><th className="py-1 pr-3">Valued</th><th></th></tr></thead>
          <tbody>{links.map((l) => (
            <tr key={l.collateral_id} className="border-b last:border-0">
              <td className="py-1 pr-3">{l.collateral_id}</td>
              <td className="py-1 pr-3">{l.collateral_type}</td>
              <td className="py-1 pr-3 tabular-nums">{Number(l.forced_sale_value || 0).toLocaleString()} {l.currency}</td>
              <td className="py-1 pr-3">{l.valuation_date || '—'}</td>
              <td className="py-1"><button className="text-red-600 text-xs underline" disabled={busy}
                onClick={() => run(() => unlinkCollateral(caseRecord.id, l.collateral_id), 'Collateral unlinked.')}>unlink</button></td>
            </tr>))}</tbody>
        </table>
      ) : <p className="text-sm text-gray-500 mb-4">No collateral linked.</p>}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
        <label className={lbl}><span className={cap}>Collateral ID</span>
          <Input value={cid} onChange={(e) => setCid(e.target.value)} placeholder="COL123" /></label>
        <label className={lbl}><span className={cap}>Type</span>
          <select className={sel} value={ctype} onChange={(e) => setCtype(e.target.value)}>
            {COLLATERAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
        <label className={lbl}><span className={cap}>Forced sale value (KES)</span>
          <Input value={fsv} onChange={(e) => setFsv(e.target.value)} inputMode="decimal" placeholder="120000000" /></label>
        <label className={lbl}><span className={cap}>Valuation date</span>
          <Input type="date" value={vdate} onChange={(e) => setVdate(e.target.value)} /></label>
        <Button disabled={busy} onClick={() => {
          const v = Number(fsv);
          if (!cid.trim() || !Number.isFinite(v) || v <= 0) return;
          run(() => linkCollateral(caseRecord.id, {
            collateral_id: cid.trim(), collateral_type: ctype, forced_sale_value: v,
            currency: 'KES', valuation_date: vdate || undefined,
          }), 'Collateral linked; coverage recomputed.').then((ok) => { if (ok) { setCid(''); setFsv(''); } });
        }}>Link collateral</Button>
      </div>
    </Card.Body></Card>
  );
}

// ── 3. Conditions Precedent / Subsequent ────────────────────────────────
export function ConditionsCpCsPanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const conds = caseRecord.conditions || [];
  if (conds.length === 0) return null;
  const row = (c: CreditAdminCondition) => (
    <tr key={c.type} className="border-b last:border-0 text-sm">
      <td className="py-1 pr-3">{c.type}</td>
      <td className="py-1 pr-3">
        <Badge tone={(c.classification || 'precedent') === 'precedent' ? 'warning' : 'info'}>
          {c.classification || 'precedent'}</Badge>
      </td>
      <td className="py-1 pr-3">{c.mandatory === false ? 'optional' : 'mandatory'}</td>
      <td className="py-1 pr-3">{c.fulfilled ? <Badge tone="success">met</Badge> : <Badge tone="neutral">open</Badge>}</td>
      <td className="py-1 flex gap-2">
        <button className="text-xs underline" disabled={busy}
          onClick={() => run(() => classifyCondition(caseRecord.id, { condition_type: c.type, classification: 'precedent' }), 'Marked precedent.')}>→ precedent</button>
        <button className="text-xs underline" disabled={busy}
          onClick={() => run(() => classifyCondition(caseRecord.id, { condition_type: c.type, classification: 'subsequent' }), 'Marked subsequent.')}>→ subsequent</button>
      </td>
    </tr>
  );
  return (
    <Card className="mt-6"><Card.Header>Conditions (Precedent / Subsequent)</Card.Header><Card.Body>
      <table className="w-full"><thead><tr className="text-left text-gray-500 border-b text-sm">
        <th className="py-1 pr-3">Condition</th><th className="py-1 pr-3">Class</th>
        <th className="py-1 pr-3">Mandatory</th><th className="py-1 pr-3">Status</th><th></th></tr></thead>
        <tbody>{conds.map(row)}</tbody></table>
      <p className="text-xs text-gray-400 mt-2">Mandatory Conditions Precedent block disbursement; Subsequent are tracked post-disbursement.</p>
    </Card.Body></Card>
  );
}

// ── 4. Legal review ─────────────────────────────────────────────────────
export function LegalReviewPanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const [officer, setOfficer] = useState('');
  const [comment, setComment] = useState('');
  const lr = caseRecord.legal_review;
  if (caseRecord.facility_security_type !== 'secured') return null;
  return (
    <Card className="mt-6"><Card.Header>Legal review</Card.Header><Card.Body>
      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-gray-500">Status:</span>
        <Badge tone={lr?.outcome === 'rejected' ? 'danger' : lr?.outcome ? 'success' : 'neutral'}>
          {lr?.status || 'not_started'}</Badge>
        {lr?.outcome && <span className="text-gray-500">outcome: {lr.outcome}</span>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
        <label className={lbl}><span className={cap}>Assign officer (code)</span>
          <Input value={officer} onChange={(e) => setOfficer(e.target.value)} placeholder="LO001" /></label>
        <Button disabled={busy || !officer.trim()} onClick={() => run(
          () => legalAssign(caseRecord.id, { officer_code: officer.trim() }), 'Legal officer assigned.')}>Assign</Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
        <label className={`${lbl} md:col-span-2`}><span className={cap}>Comment</span>
          <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="legal note / query" /></label>
        <Button disabled={busy || !comment.trim()} onClick={() => run(
          () => legalComment(caseRecord.id, { text: comment.trim() }), 'Comment added.').then((ok) => { if (ok) setComment(''); })}>Add comment</Button>
      </div>
      <div className="flex gap-2">
        <Button disabled={busy} onClick={() => run(() => legalOutcome(caseRecord.id, { outcome: 'approved' }), 'Legal review cleared.')}>Approve</Button>
        <Button disabled={busy} onClick={() => run(() => legalOutcome(caseRecord.id, { outcome: 'approved_with_conditions' }), 'Cleared with conditions.')}>Approve w/ conditions</Button>
        <Button disabled={busy} onClick={() => run(() => legalOutcome(caseRecord.id, { outcome: 'rejected' }), 'Legal review rejected.')}>Reject</Button>
      </div>
    </Card.Body></Card>
  );
}

// ── 5. Security perfection ──────────────────────────────────────────────
export function PerfectionPanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const [stype, setStype] = useState('Debenture');
  const [ref, setRef] = useState('');
  const perfs = caseRecord.security_perfections || [];
  if (caseRecord.facility_security_type !== 'secured') return null;
  return (
    <Card className="mt-6"><Card.Header>Security perfection</Card.Header><Card.Body>
      {perfs.length > 0 ? (
        <table className="w-full text-sm mb-4"><thead><tr className="text-left text-gray-500 border-b">
          <th className="py-1 pr-3">Type</th><th className="py-1 pr-3">Registration</th>
          <th className="py-1 pr-3">Perfection</th><th></th></tr></thead>
          <tbody>{perfs.map((p) => (
            <tr key={p.id} className="border-b last:border-0">
              <td className="py-1 pr-3">{p.security_type}</td>
              <td className="py-1 pr-3">{p.registration_status}{p.registration_reference ? ` (${p.registration_reference})` : ''}</td>
              <td className="py-1 pr-3"><Badge tone={p.perfection_status === 'perfected' ? 'success' : 'neutral'}>{p.perfection_status}</Badge></td>
              <td className="py-1">{p.perfection_status !== 'perfected' && (
                <button className="text-xs underline" disabled={busy}
                  onClick={() => run(() => updatePerfection(caseRecord.id, p.id, { registration_status: 'registered', perfection_status: 'perfected' }), 'Marked perfected.')}>mark perfected</button>
              )}</td>
            </tr>))}</tbody></table>
      ) : <p className="text-sm text-gray-500 mb-4">No security instruments recorded.</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
        <label className={lbl}><span className={cap}>Security type</span>
          <Input value={stype} onChange={(e) => setStype(e.target.value)} placeholder="Debenture" /></label>
        <label className={lbl}><span className={cap}>Registration ref</span>
          <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="CR/12345" /></label>
        <Button disabled={busy || !stype.trim()} onClick={() => run(
          () => addPerfection(caseRecord.id, { security_type: stype.trim(), registration_reference: ref || undefined }),
          'Security instrument added.').then((ok) => { if (ok) setRef(''); })}>Add instrument</Button>
      </div>
    </Card.Body></Card>
  );
}

// ── 6. Insurance ────────────────────────────────────────────────────────
export function InsurancePanel({ caseRecord, onChange }: PanelProps) {
  const { busy, run } = useAction(onChange);
  const [insurer, setInsurer] = useState('');
  const [policy, setPolicy] = useState('');
  const [expiry, setExpiry] = useState('');
  const [noted, setNoted] = useState(true);
  const pols = caseRecord.insurance_policies || [];
  if (caseRecord.facility_security_type !== 'secured') return null;
  return (
    <Card className="mt-6"><Card.Header>Insurance</Card.Header><Card.Body>
      {pols.length > 0 ? (
        <table className="w-full text-sm mb-4"><thead><tr className="text-left text-gray-500 border-b">
          <th className="py-1 pr-3">Insurer</th><th className="py-1 pr-3">Policy</th>
          <th className="py-1 pr-3">Expiry</th><th className="py-1 pr-3">Bank noted</th><th className="py-1 pr-3">Status</th></tr></thead>
          <tbody>{pols.map((p) => (
            <tr key={p.id} className="border-b last:border-0">
              <td className="py-1 pr-3">{p.insurer}</td><td className="py-1 pr-3">{p.policy_number}</td>
              <td className="py-1 pr-3">{p.expiry_date || '—'}</td>
              <td className="py-1 pr-3">{p.bank_interest_noted ? '✓' : '—'}</td>
              <td className="py-1 pr-3"><Badge tone={p.status === 'active' ? 'success' : 'neutral'}>{p.status}</Badge></td>
            </tr>))}</tbody></table>
      ) : <p className="text-sm text-gray-500 mb-4">No insurance policies recorded.</p>}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
        <label className={lbl}><span className={cap}>Insurer</span>
          <Input value={insurer} onChange={(e) => setInsurer(e.target.value)} /></label>
        <label className={lbl}><span className={cap}>Policy no.</span>
          <Input value={policy} onChange={(e) => setPolicy(e.target.value)} /></label>
        <label className={lbl}><span className={cap}>Expiry</span>
          <Input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} /></label>
        <label className="text-sm flex items-center gap-2 pb-2">
          <input type="checkbox" checked={noted} onChange={(e) => setNoted(e.target.checked)} /> bank interest noted</label>
        <Button disabled={busy || !insurer.trim() || !policy.trim()} onClick={() => run(
          () => addInsurance(caseRecord.id, {
            insurer: insurer.trim(), policy_number: policy.trim(),
            expiry_date: expiry || undefined, bank_interest_noted: noted,
          }), 'Insurance policy added.').then((ok) => { if (ok) { setInsurer(''); setPolicy(''); } })}>Add policy</Button>
      </div>
    </Card.Body></Card>
  );
}
