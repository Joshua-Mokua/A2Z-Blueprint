import { escapeHtml, printDocument } from './print';

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Obj : {};
const label = (key: string): string => key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const value = (v: unknown): string => v == null || v === '' ? 'Not recorded' : typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
const cell = (v: unknown): string => escapeHtml(value(v));
const rows = (data: Obj): string => Object.entries(data).map(([k,v]) => '<tr><th>' + escapeHtml(label(k)) + '</th><td>' + cell(v) + '</td></tr>').join('');
const section = (title: string, data: Obj): string => '<h2>' + escapeHtml(title) + '</h2><table>' + rows(data) + '</table>';

export function printApprovedAvailmentMemo(result: {case_id: string; version: number; released_by: string; released_at: string; snapshot: Obj}): void {
  const snap = obj(result.snapshot);
  const memo = obj(snap.memo);
  const data = obj(memo.data);
  const source = obj(snap.source);
  const approval = obj(snap.approval);
  const fields = obj(data.fields);
  const instructions = Array.isArray(data.instructions) ? data.instructions : [];
  const validation = obj(data.dual_validation);
  const heading = 'Universal Credit Availment Memo';
  const header = '<div class="head"><h1>ECOBANK KENYA</h1><strong>APPROVED / RELEASED TO TROPS</strong></div>';
  const identity = section('Document Control', {credit_admin_case_id: result.case_id, memo_id: memo.id, approved_version: result.version, released_by: result.released_by, released_at: result.released_at});
  const facility = section('Customer and Approved Facility', source);
  const terms = section('Disbursement and Facility Instructions', fields);
  const instructionRows = instructions.map((item, index) => '<tr><td>' + (index+1) + '</td><td><pre style="white-space:pre-wrap">' + cell(item) + '</pre></td></tr>').join('');
  const operational = '<h2>Operational Instructions</h2><table><tr><th>No.</th><th>Approved Instruction</th></tr>' + (instructionRows || '<tr><td colspan="2">No instructions recorded</td></tr>') + '</table>';
  const approvals = section('Approval and Authorization Record', approval);
  const validations = section('Dual Validation Evidence', validation);
  const footer = '<p class="muted">This document reproduces the approved memo snapshot released to TROPS. It is not evidence that funds have been disbursed. Flexcube booking remains a separate controlled operation.</p>';
  printDocument(heading, header + identity + facility + terms + operational + validations + approvals + footer);
}
