import { useCallback, useEffect, useState } from 'react';
import { useRole } from '@/hooks/useRole';
import { AvailmentValidationPanel } from './AvailmentValidationPanel'; // A2Z STAGE 13 VALIDATION UI
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import {
  fetchAvailmentMemo, createAvailmentMemo, saveAvailmentDraft,
  requestAvailmentApproval, approveAvailmentMemo, returnAvailmentForCorrection,
  fetchCreditAdminAuthorizers, AuthExpiredError,
} from '@/lib/api';
import type { AvailmentResponse, AvailmentInstruction, AvailmentInstructionType } from '@/types/availment';

const FIELDS = [
  ['industry_code', 'Industry code'], ['product_program_code', 'Product/program code'],
  ['restricted_salaried_facility_details', 'Restricted salaried facility details'],
  ['amount_already_disbursed', 'Amount already disbursed'], ['current_disbursement', 'Current disbursement'],
  ['value_date', 'Value date'], ['review_date', 'Review date'], ['orr', 'ORR'], ['frr', 'FRR'],
  ['default_interest_rate', 'Default interest rate'], ['repayment_amount', 'Repayment amount'],
  ['repayment_frequency', 'Repayment frequency'], ['repayment_effective_date', 'Repayment effective date'],
  ['maturity_date', 'Maturity date'], ['drawdown_account', 'Drawdown account'],
  ['repayment_account', 'Repayment account'], ['facility_fee', 'Facility fee'],
  ['fee_debit_account', 'Fee debit account'], ['deferral', 'Deferral'],
  ['fees_charges', 'Fees and charges'], ['insurance_premium', 'Insurance premium'], ['notes', 'Notes'],
] as const;
const TYPES: AvailmentInstructionType[] = [
  'insurance_collection', 'prior_loan_liquidation', 'external_bank_payoff', 'residual_lien_hold', 'other',
];
const titleCase = (s: string) => s.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const stringify = (value: unknown): string => value === null || value === undefined ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
const errorText = (e: unknown) => e instanceof Error ? e.message : 'The request failed.';

type Checker = { staff_code: string; full_name: string; role: string };

export function AvailmentMemoPanel({ caseId }: { caseId: string }) {
  const { user } = useRole();
  const [record, setRecord] = useState<AvailmentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [fields, setFields] = useState<Record<string, unknown>>({});
  const [instructions, setInstructions] = useState<AvailmentInstruction[]>([]);
  const [dirty, setDirty] = useState(false);
  const [checkers, setCheckers] = useState<Checker[]>([]);
  const [checkerCode, setCheckerCode] = useState('');
  const [approvalNote, setApprovalNote] = useState('');
  const [returnReason, setReturnReason] = useState('');

  const apply = useCallback((next: AvailmentResponse) => {
    setRecord(next);
    setFields({ ...(next.memo?.data?.fields ?? {}) });
    setInstructions((next.memo?.data?.instructions ?? []).map(i => ({ ...i })));
    setDirty(false);
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try { apply(await fetchAvailmentMemo(caseId)); }
    catch (e) { if (e instanceof AuthExpiredError) throw e; setError(errorText(e)); }
    finally { setLoading(false); }
  }, [caseId, apply]);

  useEffect(() => { void reload().catch(() => { /* Auth expiry handled by API */ }); }, [reload]);
  useEffect(() => {
    if (record?.status !== 'draft') return;
    let live = true;
    fetchCreditAdminAuthorizers().then(r => {
      if (live) setCheckers(Array.isArray(r.authorizers) ? r.authorizers : []);
    }).catch(e => { if (live) setError(`Checker directory: ${errorText(e)}`); });
    return () => { live = false; };
  }, [record?.status]);

  const act = async (fn: () => Promise<AvailmentResponse>, message: string) => {
    setBusy(true); setError(''); setNotice('');
    try { apply(await fn()); setNotice(message); }
    catch (e) { if (e instanceof AuthExpiredError) throw e; setError(errorText(e)); }
    finally { setBusy(false); }
  };

  if (loading) return <Card><Card.Body><p className="text-sm text-gray-600">Loading Availment Memo…</p></Card.Body></Card>;
  const memo = record?.memo;
  const status = record?.status ?? 'not_started';
  const editable = status === 'draft';
  const mine = String(user?.staff_code || user?.username || '').trim().toLowerCase();
  const assigned = String(memo?.approval_assignee_code || '').trim().toLowerCase();
  const isAssignedChecker = status === 'ready_for_approval' && !!mine && mine === assigned;
  const source = record?.source;
  const requiredMissing = [
    !source?.application_id && 'Application ID', !source?.client_name && 'Client name',
    (source?.amount === undefined || source?.amount === null || source?.amount === '') && 'Approved amount',
    !source?.currency && 'Currency', !stringify(fields.current_disbursement).trim() && 'Current disbursement',
    !stringify(fields.value_date).trim() && 'Value date',
  ].filter(Boolean) as string[];

  // BANK FORM ALIGNMENT STAGE 8: display-only; no new backend fields or approval claims.
  const bankFormRows: Array<[string, string, string]> = [
    ['Customer Name', stringify(source?.client_name), 'LMS / source (read-only)'],
    ['Customer Number: CIF', 'Not supplied by current memo source', 'Requires verified CBS mapping'],
    ['Date of Instruction', 'Not recorded in current memo source', 'CAD-controlled / system timestamp mapping pending'],
    ['TM Date', 'Not recorded in current memo source', 'Requires bank rule'],
    ['Branch', 'Not recorded in current memo source', 'Requires staff / branch mapping'],
    ['Collateral Code', 'Not recorded in current memo source', 'Requires collateral registry'],
    ['SIC Code', 'Not recorded in current memo source', 'Requires customer master'],
    ['Segment Code', 'Not recorded in current memo source', 'Requires segment mapping'],
    ['Industry Code', stringify(fields.industry_code), 'CAD draft input'],
    ['Product Program Code', stringify(fields.product_program_code), 'CAD draft input'],
    ['Exchange Rate', 'Not recorded in current memo source', 'Requires approved FX source'],
    ['Approved Loan Limit', stringify(source?.amount), 'LMS approved amount (read-only)'],
    ['Amount already disbursed', stringify(fields.amount_already_disbursed), 'CAD draft input; CBS verification required'],
    ['Amount of current disbursement', stringify(fields.current_disbursement), 'CAD draft input'],
    ['Total outstanding after this disbursement', 'Not calculated', 'CBS calculation and validation pending'],
    ['Value Date of Disbursement / Effective Date', stringify(fields.value_date), 'CAD draft input'],
    ['Review Date', stringify(fields.review_date), 'CAD draft input'],
    ['Obligor Risk Rating (ORR)', stringify(fields.orr), 'CAD draft input; risk source verification required'],
    ['Facility Risk Rating (FRR)', stringify(fields.frr), 'CAD draft input; risk source verification required'],
    ['Tenure of Loan (months)', 'Not mapped', 'Approved facility terms mapping pending'],
    ['Debit Interest Rate', 'Not mapped', 'Approved pricing mapping pending'],
    ['Default interest rate', stringify(fields.default_interest_rate), 'CAD draft input'],
    ['Repayment amount', stringify(fields.repayment_amount), 'CAD draft input'],
    ['Frequency of repayment', stringify(fields.repayment_frequency), 'CAD draft input'],
    ['Effective date of repayment of principal', stringify(fields.repayment_effective_date), 'CAD draft input'],
    ['Effective date of repayment of interest', 'Not separately mapped', 'Bank rule / separate field pending'],
    ['Maturity Date', stringify(fields.maturity_date), 'CAD draft input'],
    ['Drawdown Account', stringify(fields.drawdown_account), 'CAD draft input; CBS validation required'],
    ['Repayment / Liquidation Account', stringify(fields.repayment_account), 'CAD draft input; CBS validation required'],
    ['Facility Fee', stringify(fields.facility_fee), 'CAD draft input'],
    ['Account to debit facility fee', stringify(fields.fee_debit_account), 'CAD draft input'],
    ['Security Details', 'Not mapped', 'Collateral and approved security terms pending'],
    ['Transaction within approved facility', 'Not verified', 'Credit limit check pending'],
    ['Total outstanding within total facilities', 'Not verified', 'CBS exposure check pending'],
    ['Level of Approval Required', 'Not mapped', 'Approval matrix mapping pending'],
    ['Documentation in Order', 'Not verified', 'CAD checklist pending'],
    ['Deferral Approval Required', stringify(fields.deferral), 'CAD draft input; approval verification pending'],
    ['Insurance in place (if applicable)', 'Not verified', 'Insurance evidence check pending'],
    ['Deferral Approved in Place', 'Not verified', 'Deferral authority check pending'],
    ['Fees and charges collected', stringify(fields.fees_charges), 'CAD draft input; collection evidence pending'],
    ['Notes / payment instructions', stringify(fields.notes), 'CAD draft input'],
  ];
  // UNIVERSAL MEMO STAGE 9 — presentation only. No invented votes or electronic signatures.
  // The memo API currently does not guarantee these workflow fields. Display gaps transparently.
  const journeySource = (source ?? {}) as Record<string, unknown>;
  const journeyRows: Array<[string, unknown, string]> = [
    ['Deal owner / branch originator', journeySource.deal_owner ?? journeySource.originator, 'Pipeline / originating branch'],
    ['Originating branch', journeySource.branch_name ?? journeySource.branch, 'Branch directory'],
    ['Branch Credit Committee votes', journeySource.branch_committee_votes, 'Recorded individual BCC votes and decision'],
    ['Department Analyst', journeySource.department_analyst, 'Original reviewer identity'],
    ['Department Analyst comments', journeySource.department_analyst_comments, 'Immutable original review'],
    ['Department Credit Committee votes', journeySource.department_committee_votes, 'Recorded individual DCC votes and decision'],
    ['Credit Risk Analyst', journeySource.credit_risk_analyst, 'Assigned risk reviewer'],
    ['Credit Risk Analyst comments', journeySource.credit_risk_comments, 'Recorded credit risk recommendation'],
    ['Final credit decision / authority', journeySource.final_credit_decision, 'Approved decision and authority'],
    ['Post-approval Department Analyst verification', journeySource.post_approval_verification, 'Original analyst fulfilment confirmation'],
  ];
  const bankSignoffs = ['CAD MAKER', 'HEAD OF CAD / DESIGNATED CAD CHECKER', 'CREDIT RISK VALIDATOR', 'CREDIT COMMITTEE VALIDATION (WHERE REQUIRED)', 'OPERATIONS INPUTTER', 'OPERATIONS AUTHORISER'];
  return <div className="space-y-4">
    <Card stripe="primary"><Card.Header><div className="flex flex-wrap items-center justify-between gap-3"><div>
      <h2 className="text-base font-semibold text-gray-900">CAD Availment Memo</h2>
      <p className="text-xs text-gray-500">Independent maker/checker approval; does not release funds or submit to TROPS.</p>
    </div><span className="rounded-md bg-gray-100 px-3 py-1 text-sm font-medium">{titleCase(status)}{memo ? ` · Version ${memo.current_version}` : ''}</span></div></Card.Header>
    <Card.Body><div className="grid gap-3 text-sm md:grid-cols-3">
      {([['Application', source?.application_id], ['Client', source?.client_name], ['Product', source?.product],
        ['Approved amount', source?.amount], ['Currency', source?.currency], ['Approval date', source?.approval_date],
        ['Security classification', source?.facility_security_type], ['Security subtype', source?.security_subtype]] as [string, unknown][]).map(([label, value]) =>
        <div key={label}><div className="text-xs uppercase text-gray-500">{label}</div><div className="break-words font-medium">{stringify(value) || '—'}</div></div>)}
    </div>{memo && <div className="mt-4 border-t pt-3 text-xs text-gray-600 space-y-1">
      <p>Requested by: {memo.approval_requested_by || '—'} · Assigned checker: {memo.approval_assignee_name || '—'} ({memo.approval_assignee_code || '—'})</p>
      <p>Approved by: {memo.approved_by || '—'} · Approved at: {memo.approved_at || '—'}</p>
      {memo.approval_note && <p>Approval request note: {memo.approval_note}</p>}
    </div>}</Card.Body></Card>

    <Card><Card.Header><div><h3 className="text-sm font-semibold">Ecobank Universal Credit Availment & Disbursement Instruction</h3><p className="text-xs text-amber-800">Universal facility preview based on the supplied salaried-loan form. Product-specific annexes and final bank approval are pending. This is not a release authorization. Missing mappings and verifications are explicitly shown; blank fields must not be treated as approved.</p></div></Card.Header><Card.Body>
      <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-xs"><thead><tr><th className="border p-2">Bank form field</th><th className="border p-2">Current value / gap</th><th className="border p-2">Provenance / responsibility</th></tr></thead><tbody>{bankFormRows.map(([label, value, origin]) => <tr key={label}><th className="border p-2 font-medium">{label}</th><td className="border p-2">{value || '—'}</td><td className="border p-2 text-gray-600">{origin}</td></tr>)}</tbody></table></div>
      <section aria-label="Credit journey and decision record" className="mt-5 border-t pt-4">
        <h4 className="text-sm font-semibold">Credit Journey &amp; Decision Record</h4>
        <p className="mt-1 text-xs text-gray-600">Read-only workflow evidence. Votes and reviewer comments must originate from authenticated LMS records, not CAD transcription. Not recorded means the source has not been integrated or evidence is absent.</p>
        <div className="mt-2 overflow-x-auto"><table className="w-full border-collapse text-left text-xs"><thead><tr><th className="border p-2">Journey stage</th><th className="border p-2">Recorded value</th><th className="border p-2">Authoritative source</th></tr></thead><tbody>
          {journeyRows.map(([label, value, origin]) => <tr key={label}><th className="border p-2 font-medium">{label}</th><td className="border p-2 whitespace-pre-wrap break-words">{stringify(value) || 'Not recorded / integration pending'}</td><td className="border p-2 text-gray-600">{origin}</td></tr>)}
        </tbody></table></div>
      </section>
      <h4 className="mt-4 text-xs font-semibold">Electronic validation roles — workflow integration pending</h4><div className="mt-2 grid gap-2 sm:grid-cols-2">{bankSignoffs.map(role => <div key={role} className="rounded border p-2 text-xs"><span className="font-semibold">{role}</span><span className="ml-2 text-amber-800">Electronic validation not yet recorded</span></div>)}</div>
      <p className="mt-3 text-xs text-gray-600">Existing authenticated CAD maker/checker approval remains active and separate. The other electronic validation roles above are placeholders until backed by authenticated server-side attestations, timestamps, version locks and role checks. No Operations authorization or disbursement is triggered.</p>
    </Card.Body></Card>

    {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    {notice && <div role="status" className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">{notice}</div>}
    {!record && <Button variant="ghost" onClick={() => void reload()} disabled={busy}>Retry loading</Button>}
    {record && status === 'not_started' && <Card><Card.Body><p className="mb-3 text-sm text-gray-600">No Availment Memo has been started for this case.</p>
      <Button variant="primary" disabled={busy} onClick={() => void act(() => createAvailmentMemo(caseId), 'Memo created.')}>Create Availment Memo</Button>
    </Card.Body></Card>}

    {memo && <Card><Card.Header><h3 className="text-sm font-semibold">CAD operational fields</h3></Card.Header><Card.Body>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">{FIELDS.map(([key, label]) => <label key={key} className="block text-xs font-medium text-gray-600">{label}
        <input type="text" value={stringify(fields[key])} disabled={!editable || busy}
          onChange={e => { setFields(v => ({ ...v, [key]: e.target.value })); setDirty(true); }}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 disabled:bg-gray-50" />
      </label>)}</div>
      <p className="mt-3 text-xs text-gray-500">Enter amounts and dates in the format required by your bank. Source-approved fields above are read-only.</p>
    </Card.Body></Card>}

    {memo && <Card><Card.Header><h3 className="text-sm font-semibold">Disbursement instructions</h3></Card.Header><Card.Body><div className="space-y-3">
      {instructions.map((instruction, index) => <div key={index} className="grid gap-2 rounded-md border border-gray-200 p-3 md:grid-cols-[1fr_2fr_auto]">
        <select aria-label={`Instruction ${index + 1} type`} disabled={!editable || busy} value={instruction.type}
          onChange={e => { setInstructions(a => a.map((v, i) => i === index ? { ...v, type: e.target.value as AvailmentInstructionType } : v)); setDirty(true); }}
          className="rounded-md border border-gray-300 p-2 text-sm">{TYPES.map(t => <option key={t} value={t}>{titleCase(t)}</option>)}</select>
        <input aria-label={`Instruction ${index + 1} details`} disabled={!editable || busy} type="text" placeholder="Instruction details"
          value={stringify(instruction.details)} onChange={e => { setInstructions(a => a.map((v, i) => i === index ? { ...v, details: e.target.value } : v)); setDirty(true); }}
          className="rounded-md border border-gray-300 p-2 text-sm" />
        {editable && <Button variant="ghost" size="sm" disabled={busy} onClick={() => { setInstructions(a => a.filter((_, i) => i !== index)); setDirty(true); }}>Remove</Button>}
      </div>)}
      {editable && <Button variant="ghost" size="sm" disabled={busy} onClick={() => { setInstructions(a => [...a, { type: 'other', details: '' }]); setDirty(true); }}>Add instruction</Button>}
      {instructions.length === 0 && <p className="text-xs text-gray-500">No additional disbursement instructions recorded.</p>}
    </div></Card.Body></Card>}

    {memo && editable && <Card stripe="accent"><Card.Header><h3 className="text-sm font-semibold">Draft and approval submission</h3></Card.Header><Card.Body>
      <div className="flex flex-wrap items-center gap-3"><Button variant="primary" disabled={busy || !dirty}
        onClick={() => void act(() => saveAvailmentDraft(caseId, { fields, instructions }), 'Draft saved.')}>Save draft</Button>
        {dirty && <span className="text-xs text-amber-700">Unsaved changes — save before requesting approval.</span>}
      </div>
      <div className="mt-4 border-t pt-4"><p className="text-xs font-semibold uppercase text-gray-500">Readiness check</p>
        {requiredMissing.length ? <p className="mt-1 text-sm text-amber-800">Missing: {requiredMissing.join(', ')}</p> : <p className="mt-1 text-sm text-green-700">Required values present; server performs final validation.</p>}
        <label className="mt-3 block text-xs font-medium text-gray-600">Select eligible Credit Admin checker
          <select className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm" value={checkerCode} disabled={busy} onChange={e => setCheckerCode(e.target.value)}>
            <option value="">Select checker…</option>{checkers.map(c => <option key={c.staff_code} value={c.staff_code}>{c.full_name} · {c.role} ({c.staff_code})</option>)}
          </select></label>
        <label className="mt-3 block text-xs font-medium text-gray-600">Submission note (optional)
          <textarea className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm" rows={2} value={approvalNote} disabled={busy} onChange={e => setApprovalNote(e.target.value)} />
        </label><div className="mt-3"><Button variant="primary" disabled={busy || dirty || !checkerCode || requiredMissing.length > 0}
          onClick={() => void act(() => requestAvailmentApproval(caseId, { approver_code: checkerCode, note: approvalNote }), 'Submitted to selected checker.')}>Request approval</Button></div>
      </div>
    </Card.Body></Card>}

    {memo && status === 'ready_for_approval' && <Card stripe="accent"><Card.Header><h3 className="text-sm font-semibold">Checker decision</h3></Card.Header><Card.Body>
      {!isAssignedChecker ? <p className="text-sm text-gray-600">Awaiting the assigned Credit Admin checker. This memo is read-only.</p> : <div className="space-y-3">
        <Button variant="primary" disabled={busy} onClick={() => void act(() => approveAvailmentMemo(caseId), 'Availment Memo approved and versioned.')}>Approve memo</Button>
        <label className="block text-xs font-medium text-gray-600">Reason for return (required)
          <textarea className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm" rows={3} value={returnReason} disabled={busy} onChange={e => setReturnReason(e.target.value)} />
        </label><Button variant="ghost" disabled={busy || !returnReason.trim()} onClick={() => void act(() => returnAvailmentForCorrection(caseId, { reason: returnReason.trim() }), 'Returned to maker for correction.')}>Return for correction</Button>
      </div>}
    </Card.Body></Card>}
    {memo && (memo.data?.approval_returns?.length ?? 0) > 0 && <Card><Card.Header><h3 className="text-sm font-semibold">Return history</h3></Card.Header><Card.Body>
      <div className="space-y-2">{memo.data?.approval_returns?.map((entry, index) => <pre key={index} className="whitespace-pre-wrap break-words rounded bg-gray-50 p-2 text-xs">{JSON.stringify(entry, null, 2)}</pre>)}</div>
    </Card.Body></Card>}
    {memo && status === 'approved' && <p className="text-sm text-green-800">Approved Availment Memo is immutable. No disbursement instruction has been sent to TROPS by this action.</p>}
    {import.meta.env.VITE_A2Z_AVAILMENT_VALIDATION_UI === 'enabled' && memo && <AvailmentValidationPanel caseId={caseId} />}
  </div>;
}
