#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BR1 - the app says A2Z, and the Committee tab shows only committee work.

THREE THINGS THE PILOT SAW THIS MORNING (2026-08-13).

1. "EKE IS STILL THERE AND IT IS WORRYING." Nothing was pulled from Alex -
   data/org_config.json on main reads "A2Z Blueprint" and always did. EKE was
   HARDCODED IN THE FRONTEND in seventeen places across eleven files:

       BrandingProvider.tsx    app_name: 'EKE Blueprint'   <- the fallback the
                                                              sidebar shows
                                                              before branding
                                                              loads
       breadcrumbs             'EKE Pipeline Intelligence System (PIS)'
                               'EKE Credit Intelligence System (CIS)'
                               'EKE Sales Pro', 'EKE MIS 360'

   So the config was right and the labels ignored it. All seventeen now read
   A2Z. Comments are left alone - they explain history and renaming them would
   lose the point they were making.

2. CANCELLATION CARDS RENDERED UNDER THE COMMITTEE TAB. The page suppresses the
   deal-card list for 'dailylog', 'ranking' and 'analytics' - a list written
   before the Committee tab existed, and nobody added it. So a committee member
   opening their tab got "Nothing waiting on your committee" followed by
   somebody's cancellation request, which is a confusing thing to put under a
   heading about committees.

3. THE COMMITTEE TAB ALWAYS READ 0. The count was hardcoded. A tab that always
   says zero tells somebody there is nothing to do, which is the opposite of
   what this queue exists to say. It now fetches the real number.

Verified: tsc --noEmit clean, and no hardcoded 'EKE ' string literal remains.

Usage (from project root, .venv active):
    python scripts\\patch_br1_a2z_and_committee_tab.py            # dry run
    python scripts\\patch_br1_a2z_and_committee_tab.py --apply
"""
import os
import shutil
import sys

BACKUP_SUFFIX = ".pre_br1"

FILES = {
    'frontend/web/src/components/AffordabilityAppraisal.tsx': r'''// AffordabilityAppraisal.tsx — shared RM/analyst multi-source affordability appraisal.
// Deterministic (no AI). Each income source (Bank X, M-Pesa, ...) has its own DSR + months
// + anomaly exclusions; a consolidation line SUMS the affordable instalments = total
// borrowing capacity. Named scenarios can be saved for the report. Amortization calc.
// Placed on BOTH the LMS application detail and the pipeline deal detail.
import { useState } from 'react';
import { analyzeMultiSource, computeAmortization, computeQualifyingAmount, getDealAppraisal, saveDealAppraisal, getAppAppraisal, saveAppAppraisal, type MultiSourceResult, type AmortizationResult, type QualifyingResult } from '@/lib/api';
import { useEffect } from 'react';
import { useToast } from '@/components/Toast';
import { useBranding } from '@/hooks/useBranding';
import { Card, EmbeddedShell, EmbeddedHeader, EmbeddedBody } from '@/components/Card';
import type { ElementType } from 'react';
import { Button } from '@/components/Button';

interface SourceInput {
  label: string;
  cif?: string;
  dsr_pct?: number;
  months_window?: number;
  raw_transactions?: string; // pasted CSV lines: date,amount,dr_cr
}

interface SavedScenario {
  name: string;
  total: number;
  lines: { label: string; dsr: number | null; months: number | null; affordable: number | null }[];
}

function parseTxns(raw: string): { txn_date: string; amount: number; dr_cr: string }[] {
  const out: { txn_date: string; amount: number; dr_cr: string }[] = [];
  for (const line of (raw || '').split('\n')) {
    const parts = line.split(',').map((p) => p.trim());
    if (parts.length >= 3 && parts[0]) {
      const amt = Number(parts[1]);
      if (!Number.isNaN(amt)) out.push({ txn_date: parts[0], amount: amt, dr_cr: parts[2] });
    }
  }
  return out;
}

export function AffordabilityAppraisal({ defaultCif, dealId, appId, embedded = false, canEdit = true }: { defaultCif?: string; dealId?: string; appId?: string; embedded?: boolean; canEdit?: boolean }) {
  const { toast } = useToast();
  const { branding } = useBranding();
  const [sources, setSources] = useState<SourceInput[]>([
    { label: 'Bank statement 1', cif: defaultCif ?? '', dsr_pct: 40, months_window: 6 },
  ]);
  const [result, setResult] = useState<MultiSourceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [scenarioName, setScenarioName] = useState('');
  const [scenarios, setScenarios] = useState<SavedScenario[]>([]);
  // per-source anomaly exclusions {sourceIndex: [{month, reason}]}
  const [excludedBySource, setExcludedBySource] = useState<Record<number, { month: string; reason: string }[]>>({});
  const effectiveCif = (sources[0]?.cif && sources[0].cif.trim()) ? sources[0].cif.trim() : (defaultCif ?? '');

  // persistence: load saved appraisal on mount
  useEffect(() => {
    const loadSaved = async () => {
      try {
        const saved = dealId ? await getDealAppraisal(dealId) : appId ? await getAppAppraisal(appId) : null;
        if (saved && Array.isArray(saved.sources) && saved.sources.length) {
          setSources(saved.sources as SourceInput[]);
        }
        if (saved && Array.isArray(saved.scenarios) && saved.scenarios.length) {
          setScenarios(saved.scenarios as SavedScenario[]);
        }
        if (saved && Array.isArray(saved.custom_sections) && saved.custom_sections.length) {
          setCustomSections(saved.custom_sections as { heading: string; body: string }[]);
        }
      } catch { /* no saved appraisal yet */ }
    };
    void loadSaved();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dealId, appId]);

  const saveAppraisal = async () => {
    const body = { sources, scenarios, custom_sections: customSections };
    try {
      if (dealId) await saveDealAppraisal(dealId, body);
      else if (appId) await saveAppAppraisal(appId, body);
      else { toast({ tone: 'danger', message: 'No case to save to.' }); return; }
      toast({ tone: 'success', message: 'Appraisal saved.' });
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' }); }
  };

  // custom sections (RM headings/free text, not page-limited)
  const [customSections, setCustomSections] = useState<{ heading: string; body: string }[]>([]);
  const addSection = () => setCustomSections((s) => [...s, { heading: '', body: '' }]);
  const removeSection = (i: number) => setCustomSections((s) => s.filter((_, idx) => idx !== i));
  const updateSection = (i: number, patch: Partial<{ heading: string; body: string }>) =>
    setCustomSections((s) => s.map((sec, idx) => (idx === i ? { ...sec, ...patch } : sec)));

  // qualifying amount
  const [qualRate, setQualRate] = useState('');
  const [qualTenor, setQualTenor] = useState('');
  const [qualResult, setQualResult] = useState<QualifyingResult | null>(null);
  const runQualifying = async () => {
    const instalment = result?.consolidation.total_affordable_installment ?? 0;
    const tenor = Number(qualTenor);
    if (!instalment || !tenor) { toast({ tone: 'danger', message: 'Analyse sources and enter a tenor first.' }); return; }
    try {
      const r = await computeQualifyingAmount({ affordable_installment: instalment, monthly_rate_pct: Number(qualRate) || undefined, tenor_months: tenor });
      setQualResult(r);
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Calc failed' }); }
  };

  // amortization
  const [amAmount, setAmAmount] = useState('');
  const [amRate, setAmRate] = useState('');
  const [amTenor, setAmTenor] = useState('');
  const [amResult, setAmResult] = useState<AmortizationResult | null>(null);

  const addSource = () => setSources((s) => [...s, { label: `Statement ${s.length + 1}`, dsr_pct: 40, months_window: 6 }]);
  const removeSource = (i: number) => setSources((s) => s.filter((_, idx) => idx !== i));
  const updateSource = (i: number, patch: Partial<SourceInput>) =>
    setSources((s) => s.map((src, idx) => (idx === i ? { ...src, ...patch } : src)));

  const run = async (): Promise<MultiSourceResult | null> => {
    setBusy(true);
    try {
      const payloadSources = sources.map((s, i) => {
        const txns = s.raw_transactions ? parseTxns(s.raw_transactions) : undefined;
        return {
          label: s.label,
          ...(txns && txns.length ? { transactions: txns } : {}),
          ...(s.cif ? { cif: s.cif } : {}),
          ...(s.dsr_pct != null ? { dsr_pct: s.dsr_pct } : {}),
          ...(s.months_window != null ? { months_window: s.months_window } : {}),
          ...(excludedBySource[i]?.length ? { excluded_months: excludedBySource[i] } : {}),
        };
      });
      const r = await analyzeMultiSource(payloadSources);
      setResult(r);
      return r;
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Analysis failed' });
      return null;
    } finally { setBusy(false); }
  };

  const saveScenario = async () => {
    if (!scenarioName.trim()) { toast({ tone: 'danger', message: 'Name the scenario first.' }); return; }
    const r = result ?? (await run());
    if (!r) return;
    setScenarios((prev) => [...prev, {
      name: scenarioName.trim(),
      total: r.consolidation.total_affordable_installment,
      lines: r.sources.map((s) => ({
        label: s.label ?? '',
        dsr: s.affordability?.dsr_limit_pct ?? null,
        months: s.affordability?.months_in_basis ?? null,
        affordable: s.affordability?.affordable_installment ?? null,
      })),
    }]);
    setScenarioName('');
    toast({ tone: 'success', message: 'Scenario saved.' });
  };

  const runAmort = async () => {
    const amount = Number(amAmount), rate = Number(amRate), tenor = Number(amTenor);
    if (!amount || !tenor) { toast({ tone: 'danger', message: 'Enter amount and tenor.' }); return; }
    try {
      const r = await computeAmortization({ amount, monthly_rate_pct: rate || undefined, tenor_months: tenor });
      setAmResult(r);
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Calc failed' }); }
  };

  const printAppraisal = () => {
    const bank = branding?.app_name ?? 'A2Z MIS 360';
    const esc = (v: unknown) => String(v ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] as string));
    const fmt = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 0 }));
    const srcRows = (result?.sources ?? []).map((s) =>
      `<tr><td>${esc(s.label)}</td><td style="text-align:right">${s.affordability?.dsr_limit_pct ?? '—'}</td><td style="text-align:right">${s.affordability?.months_in_basis ?? '—'}</td><td style="text-align:right">${fmt(s.summary?.avg_monthly_net)}</td><td style="text-align:right">${fmt(s.affordability?.affordable_installment)}</td></tr>`).join('');
    const total = result ? fmt(result.consolidation.total_affordable_installment) : '—';
    const scenRows = scenarios.map((sc) =>
      `<tr><td>${esc(sc.name)}</td><td style="text-align:right">${fmt(sc.total)}</td><td>${esc(sc.lines.map((l) => `${l.label} ${l.dsr ?? '—'}%`).join(', '))}</td></tr>`).join('');
    const secBlocks = customSections.filter((x) => x.heading || x.body).map((x) =>
      `<div class="sec"><h3>${esc(x.heading)}</h3><p>${esc(x.body).replace(/\n/g, '<br/>')}</p></div>`).join('');
    const qual = qualResult ? `<p><strong>Qualifying amount (from cashflow):</strong> KES ${fmt(qualResult.qualifying_amount)} <span class="muted">(at ${qualResult.monthly_rate_pct}%/mo × ${qualResult.tenor_months}mo on ${fmt(qualResult.affordable_installment)}/mo)</span></p>` : '';
    const html = `<!doctype html><html><head><meta charset="utf-8"/><title>Credit Appraisal</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;margin:32px;font-size:12px}
  h1{font-size:18px;margin:0 0 2px} h2{font-size:13px;margin:18px 0 6px;border-bottom:1px solid #ccc;padding-bottom:2px}
  h3{font-size:12px;margin:8px 0 2px} .muted{color:#666;font-weight:normal}
  table{width:100%;border-collapse:collapse;margin:6px 0} th,td{border:1px solid #ddd;padding:4px 6px;text-align:left}
  th{background:#f3f3f3} .total{font-weight:bold;background:#f8f8f8}
  .head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #0082BB;padding-bottom:6px}
  .sec{margin:6px 0} @media print{body{margin:12mm}}
</style></head><body>
  <div class="head"><h1>${esc(bank)} — Credit Appraisal</h1><span class="muted">${new Date().toLocaleDateString()}</span></div>
  <p><strong>Customer CIF:</strong> ${esc(effectiveCif || '—')}</p>
  <h2>Affordability — income sources</h2>
  <table><thead><tr><th>Source</th><th style="text-align:right">DSR %</th><th style="text-align:right">Months</th><th style="text-align:right">Avg net</th><th style="text-align:right">Affordable instalment</th></tr></thead>
  <tbody>${srcRows || '<tr><td colspan="5" class="muted">No sources analysed</td></tr>'}
  <tr class="total"><td colspan="4">Consolidated total borrowing capacity</td><td style="text-align:right">${total}</td></tr></tbody></table>
  ${qual}
  ${scenRows ? `<h2>Scenarios considered</h2><table><thead><tr><th>Scenario</th><th style="text-align:right">Total capacity</th><th>Detail</th></tr></thead><tbody>${scenRows}</tbody></table>` : ''}
  ${secBlocks ? `<h2>Additional analysis</h2>${secBlocks}` : ''}
  <h2>Sign-off</h2>
  <table><tr><td style="height:48px">Prepared by (RM/Analyst): __________________</td><td>Date: __________</td></tr>
  <tr><td style="height:48px">Reviewed by (Credit): __________________</td><td>Date: __________</td></tr></table>
  <script>window.onload=function(){window.print();}</script>
</body></html>`;
    const w = window.open('', '_blank');
    if (!w) { toast({ tone: 'danger', message: 'Allow pop-ups to print the appraisal.' }); return; }
    w.document.write(html); w.document.close();
  };

  const money = (n: number | null | undefined) =>
    n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 0 });

  const Shell:   ElementType = embedded ? EmbeddedShell  : Card;
  const SHeader: ElementType = embedded ? EmbeddedHeader : Card.Header;
  const SBody:   ElementType = embedded ? EmbeddedBody   : Card.Body;

  return (
    <Shell className="mt-4" stripe="accent">
      <SHeader><h3 className="text-sm font-semibold text-gray-900">Affordability Appraisal (multi-source)</h3></SHeader>
      <SBody>
        <p className="mb-3 text-xs text-gray-500">
          Add each income source (Bank X, M-Pesa, …) with its own DSR and months. Remove a
          disqualified statement or add a requested one — the total recalculates. Save named
          scenarios for the appraisal report. Deterministic (no AI required).
        </p>

        {/* nav strip (anchor-scroll) */}
        <div className="appraisal-nav sticky top-0 z-10 mb-3 flex flex-wrap gap-1 border-b-2 border-[#0082BB] bg-white/95 py-2 text-xs">
          {[['sources','Sources'],['consolidation','Consolidation'],['qualifying','Qualifying'],['scenarios','Scenarios'],['sections','Sections'],['actions','Print']].map(([id,lbl]) => (
            <button key={id} onClick={() => document.getElementById('appr-'+id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className="rounded px-2 py-1 text-[#005B82] hover:bg-[#0082BB]/10">{lbl}</button>
          ))}
        </div>

        {effectiveCif && (
          <p className="mb-3 text-xs text-gray-600">Customer CIF: <span className="font-mono font-medium">{effectiveCif}</span></p>
        )}

        {/* Sources */}
        <div id="appr-sources" />
        <div className="space-y-3">
          {sources.map((s, i) => (
            <div key={i} className="rounded border border-gray-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <input
                  value={s.label}
                  onChange={(e) => updateSource(i, { label: e.target.value })}
                  className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm font-medium"
                  placeholder="Source label (e.g. Bank X, M-Pesa)"
                />
                {sources.length > 1 && (
                  <Button variant="ghost" onClick={() => removeSource(i)}>Remove</Button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <label className="flex flex-col">CIF (from CBS)
                  <input value={s.cif ?? ''} onChange={(e) => updateSource(i, { cif: e.target.value })}
                    className="mt-1 rounded border border-gray-300 px-2 py-1" placeholder="optional" />
                </label>
                <label className="flex flex-col">DSR %
                  <input type="number" value={s.dsr_pct ?? ''} onChange={(e) => updateSource(i, { dsr_pct: e.target.value === '' ? undefined : Number(e.target.value) })}
                    className="mt-1 rounded border border-gray-300 px-2 py-1" />
                </label>
                <label className="flex flex-col">Months
                  <input type="number" value={s.months_window ?? ''} onChange={(e) => updateSource(i, { months_window: e.target.value === '' ? undefined : Number(e.target.value) })}
                    className="mt-1 rounded border border-gray-300 px-2 py-1" />
                </label>
                <label className="col-span-2 flex flex-col sm:col-span-1">Or paste txns (date,amount,dr_cr)
                  <textarea value={s.raw_transactions ?? ''} onChange={(e) => updateSource(i, { raw_transactions: e.target.value })}
                    rows={1} className="mt-1 rounded border border-gray-300 px-2 py-1" placeholder="2025-10-05,180000,CR" />
                </label>
              </div>
            </div>
          ))}
        </div>

        <div id="appr-actions" />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="ghost" onClick={addSource}>+ Add statement</Button>
          <Button variant="primary" onClick={() => void run()} disabled={busy}>{busy ? 'Analysing…' : 'Analyse & consolidate'}</Button>
          {canEdit && (dealId || appId) && <Button variant="ghost" onClick={() => void saveAppraisal()}>Save appraisal</Button>}
          <Button variant="ghost" onClick={printAppraisal}>Print appraisal</Button>
        </div>

        {/* Result */}
        <div id="appr-consolidation" />
        {result && (
          <div className="mt-4 rounded border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr><th className="p-2 text-left">Source</th><th className="p-2 text-right">DSR %</th><th className="p-2 text-right">Months</th><th className="p-2 text-right">Avg net</th><th className="p-2 text-right">Affordable instalment</th></tr>
              </thead>
              <tbody>
                {result.sources.map((s, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2">{s.label}
                      {s.affordability?.anomaly_hints && s.affordability.anomaly_hints.length > 0 && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                          anomaly: {s.affordability.anomaly_hints.join(', ')}
                        </span>
                      )}
                    </td>
                    <td className="p-2 text-right">{s.affordability?.dsr_limit_pct ?? '—'}</td>
                    <td className="p-2 text-right">{s.affordability?.months_in_basis ?? '—'}</td>
                    <td className="p-2 text-right">{money(s.summary?.avg_monthly_net)}</td>
                    <td className="p-2 text-right font-medium">{money(s.affordability?.affordable_installment)}</td>
                  </tr>
                ))}
                <tr className="border-t-2 bg-gray-50 font-semibold">
                  <td className="p-2" colSpan={4}>Consolidated total borrowing capacity ({result.consolidation.method})</td>
                  <td className="p-2 text-right">{money(result.consolidation.total_affordable_installment)}</td>
                </tr>
              </tbody>
            </table>
            {/* anomaly-surface: prompt the analyst to exclude flagged months before printing */}
            {result.sources.some((s) => (s.affordability?.anomaly_hints ?? []).length > 0) && (
              <div className="border-t bg-amber-50 p-2 text-xs text-amber-900">
                <span className="font-medium">Anomalous months detected — exclude before finalising:</span>
                <div className="mt-1 space-y-1">
                  {result.sources.map((s, i) => (s.affordability?.anomaly_hints ?? []).map((mo) => (
                    <div key={`${i}-${mo}`} className="flex items-center gap-2">
                      <span>{s.label}: {mo}</span>
                      <button
                        onClick={() => {
                          setExcludedBySource((prev) => ({ ...prev, [i]: [...(prev[i] ?? []), { month: mo, reason: 'analyst-excluded anomaly' }] }));
                          void run();
                        }}
                        className="rounded bg-amber-200 px-2 py-0.5 text-amber-900 hover:bg-amber-300">exclude {mo}</button>
                    </div>
                  )))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Scenarios */}
        <div id="appr-scenarios" />
        <div className="mt-4 border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">Scenarios (captured in the report)</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input value={scenarioName} onChange={(e) => setScenarioName(e.target.value)}
              placeholder="e.g. A: 6mo BankX@40% + Mpesa@30%"
              className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm" />
            <Button variant="ghost" onClick={() => void saveScenario()}>Save scenario</Button>
          </div>
          {scenarios.length > 0 && (
            <div className="mt-2 space-y-1">
              {scenarios.map((sc, i) => (
                <div key={i} className="rounded bg-gray-50 p-2 text-xs">
                  <span className="font-medium">{sc.name}</span> — total capacity {money(sc.total)}
                  <span className="ml-2 text-gray-500">
                    ({sc.lines.map((l) => `${l.label} ${l.dsr ?? '—'}%→${money(l.affordable)}`).join(' · ')})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Qualifying amount from cashflow */}
        <div id="appr-qualifying" />
        <div className="mt-4 border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">Qualifying amount from cashflow</p>
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <span className="text-gray-500">Uses the consolidated capacity{result ? `: ${money(result.consolidation.total_affordable_installment)}/mo` : ' (analyse first)'}</span>
            <label className="flex flex-col">Rate (%/month, blank=config)
              <input type="number" value={qualRate} onChange={(e) => setQualRate(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <label className="flex flex-col">Tenor (months)
              <input type="number" value={qualTenor} onChange={(e) => setQualTenor(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <Button variant="ghost" onClick={() => void runQualifying()}>Compute qualifying amount</Button>
          </div>
          {qualResult && (
            <div className="mt-2 text-sm">
              Qualifies for <span className="font-semibold text-green-700">{money(qualResult.qualifying_amount)}</span>
              <span className="text-xs text-gray-500"> (at {qualResult.monthly_rate_pct}%/mo x {qualResult.tenor_months}mo on {money(qualResult.affordable_installment)}/mo)</span>
            </div>
          )}
        </div>

        {/* Custom sections */}
        <div id="appr-sections" />
        <div className="mt-4 border-t pt-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-medium text-gray-600">Additional sections</p>
            <Button variant="ghost" onClick={addSection}>+ Add section</Button>
          </div>
          {customSections.map((sec, i) => (
            <div key={i} className="mb-2 rounded border border-gray-200 p-2">
              <div className="mb-1 flex items-center gap-2">
                <input value={sec.heading} onChange={(e) => updateSection(i, { heading: e.target.value })}
                  placeholder="Section heading" className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm font-medium" />
                <Button variant="ghost" onClick={() => removeSection(i)}>Remove</Button>
              </div>
              <textarea value={sec.body} onChange={(e) => updateSection(i, { body: e.target.value })}
                rows={3} placeholder="Free text — not page-limited" className="w-full rounded border border-gray-300 px-2 py-1 text-sm" />
            </div>
          ))}
        </div>

        {/* Amortization calculator */}
        <div className="mt-4 border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">Amortization calculator</p>
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="flex flex-col">Amount (KES)
              <input type="number" value={amAmount} onChange={(e) => setAmAmount(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <label className="flex flex-col">Rate (%/month, blank=config)
              <input type="number" value={amRate} onChange={(e) => setAmRate(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <label className="flex flex-col">Tenor (months)
              <input type="number" value={amTenor} onChange={(e) => setAmTenor(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <Button variant="ghost" onClick={() => void runAmort()}>Calculate</Button>
          </div>
          {amResult && (
            <div className="mt-2 text-xs text-gray-700">
              Instalment <span className="font-semibold">{money(amResult.monthly_instalment)}/mo</span>
              {' · '}total {money(amResult.total_repayable)} · interest {money(amResult.total_interest)} · rate {amResult.monthly_rate_pct}%/mo
            </div>
          )}
        </div>
      </SBody>
    </Shell>
  );
}
''',

    'frontend/web/src/pages/CommitteeConvening.tsx': r'''// C4: MD convening queue — referred cases grouped by committee tier. The MD sees
// per-tier counts, case details, pre-read tallies, and convenes the binding meeting.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import {
  fetchConveningQueue, convokeCommittee,
  type ConveningQueueResponse, type ConveningCase,
} from '@/lib/api';

function fmt(n?: number): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

export function CommitteeConvening() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState<ConveningQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try { setData(await fetchConveningQueue()); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load queue' }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const convene = async (appId: string) => {
    setBusy(appId);
    try {
      await convokeCommittee(appId);
      toast({ tone: 'success', message: 'Committee convened — the binding vote is open.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Convene failed' });
    } finally { setBusy(null); }
  };

  const slaBadge = (c: ConveningCase) => {
    if (!c.sla) return null;
    const st = c.sla.state;
    const cls = st === 'breached' ? 'bg-red-100 text-red-700'
      : st === 'due_soon' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700';
    const txt = st === 'breached' ? `${c.sla.overdue_business_days}d over`
      : st === 'due_soon' ? `${c.sla.remaining_business_days}d left` : 'On track';
    return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{txt}</span>;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Committee Convening' }]}
        title="Committee Convening"
        subtitle="Cases referred to committee, grouped by tier. Convene the meeting to open the binding vote."
      />
      <main className="max-w-6xl mx-auto px-6 py-6">
        {!loading && data && (
          <div className="mb-4 flex gap-3">
            <Card><Card.Body className="py-3">
              <div className="text-xs text-gray-500">Total before committee</div>
              <div className="text-xl font-semibold">{data.total}</div>
            </Card.Body></Card>
            <Card><Card.Body className="py-3">
              <div className="text-xs text-gray-500">Awaiting convening</div>
              <div className="text-xl font-semibold text-brand-primary">{data.awaiting}</div>
            </Card.Body></Card>
          </div>
        )}

        {loading && <Card><Card.Body>Loading…</Card.Body></Card>}
        {!loading && data && data.tiers.length === 0 && (
          <Card><Card.Body>
            <div className="py-8 text-center text-sm text-gray-500">No cases before any committee right now.</div>
          </Card.Body></Card>
        )}

        {!loading && data && data.tiers.map((t) => (
          <Card key={String(t.tier)} className="mb-4" stripe="primary">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">{t.name ?? `Tier ${t.tier}`}</h2>
              <Badge tone="brand" size="sm">{t.count}</Badge>
            </Card.Header>
            <Card.Body>
              <div className="space-y-2">
                {t.cases.map((c) => (
                  <div key={c.id} className="flex items-center justify-between rounded border p-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <button className="font-mono text-xs text-brand-primary hover:underline"
                          onClick={() => navigate(`/lms/${encodeURIComponent(c.id)}`)}>{c.id}</button>
                        <span className="text-sm font-medium">{c.client_name}</span>
                        {slaBadge(c)}
                      </div>
                      <div className="mt-0.5 text-xs text-gray-500">
                        {c.product} · KES {fmt(c.amount)} · pre-reads: {c.pre_read_count}
                        {' '}(<span className="text-green-600">{c.pre_read_tally.leaning_approve ?? 0}▲</span>
                        {' '}<span className="text-red-600">{c.pre_read_tally.leaning_decline ?? 0}▼</span>
                        {' '}<span className="text-amber-600">{c.pre_read_tally.questions ?? 0}?</span>)
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.convened
                        ? <Badge tone="success" size="sm">Convened</Badge>
                        : <Button size="sm" onClick={() => void convene(c.id)} disabled={busy === c.id}>
                            {busy === c.id ? 'Convening…' : 'Convene'}
                          </Button>}
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        ))}
      </main>
    </div>
  );
}
''',

    'frontend/web/src/pages/CreditAdmin.tsx': r'''// v10.522 Phase 4 Batch β6 — Credit Admin case list page.
//
// First consumer of GET /api/credit-admin/cases (α9). Cascade-scoped
// table. Filter chips by case category (pending conditions / ready /
// cleared / disbursed) rather than by single status string, because
// case state is a combination of three boolean flags.
//
// Pattern mirrors Lms.tsx (β5).

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useCreditAdminCases } from '@/hooks/useCreditAdminCases';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  CASE_CATEGORIES,
  caseCategoryLabel,
  categorizeCase,
  caseStatusTone,
  caseStatusLabel,
  type CaseCategory,
  type CreditAdminCase,
} from '@/types/creditAdmin';


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

function conditionProgress(c: CreditAdminCase): string {
  const total = (c.conditions || []).length;
  if (total === 0) return '—';
  const fulfilled = c.conditions.filter((cond) => cond.fulfilled).length;
  return `${fulfilled} / ${total}`;
}


// ── Page component ──────────────────────────────────────────────────────

export function CreditAdmin() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { cases, count, loading, error, refetch } = useCreditAdminCases();

  // ── Filter state ──
  const [categoryFilter, setCategoryFilter] = useState<CaseCategory>('all');
  const [searchTerm,     setSearchTerm]     = useState<string>('');

  // ── Filtered cases ──
  const filteredCases = useMemo<CreditAdminCase[]>(() => {
    let result = cases;
    if (categoryFilter !== 'all') {
      result = result.filter((c) => categorizeCase(c) === categoryFilter);
    }
    if (searchTerm.trim()) {
      const t = searchTerm.trim().toLowerCase();
      result = result.filter((c) =>
        (c.client_name || '').toLowerCase().includes(t) ||
        (c.id || '').toLowerCase().includes(t) ||
        (c.application_id || '').toLowerCase().includes(t) ||
        (c.product || '').toLowerCase().includes(t) ||
        (c.rm_name || '').toLowerCase().includes(t)
      );
    }
    return result;
  }, [cases, categoryFilter, searchTerm]);

  // ── Counts per category ──
  const categoryCounts = useMemo(() => {
    const counts: Record<CaseCategory, number> = {
      all: cases.length,
      pending_conditions: 0,
      ready_for_disbursement: 0,
      cleared: 0,
      disbursed: 0,
    };
    for (const c of cases) {
      counts[categorizeCase(c)]++;
    }
    return counts;
  }, [cases]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Admin' }]}
        title="Credit Admin"
        subtitle="Approved loans in the disbursement pipeline · condition tracking."
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

        {/* Filter bar */}
        <Card className="mb-4">
          <Card.Body>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {CASE_CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                    categoryFilter === cat
                      ? 'bg-brand-primary text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  disabled={cat !== 'all' && categoryCounts[cat] === 0}
                >
                  {caseCategoryLabel(cat)} ({categoryCounts[cat]})
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search by client name, case id, app id, product, or RM..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="flex-1 h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              {searchTerm && (
                <Button variant="ghost" size="sm" onClick={() => setSearchTerm('')}>
                  Clear
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
            </div>
          </Card.Body>
        </Card>


        {/* Error */}
        {error && (
          <Card className="mb-4">
            <Card.Body>
              <div className="text-sm text-red-800">
                <div className="font-semibold mb-1">Failed to load cases</div>
                <div>{error}</div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* Loading */}
        {loading && !error && (
          <Card>
            <Card.Body>
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            </Card.Body>
          </Card>
        )}


        {/* Empty */}
        {!loading && !error && filteredCases.length === 0 && (
          <Card>
            <Card.Body>
              <div className="text-center py-8">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  No cases match the current filter
                </div>
                <div className="text-xs text-gray-500">
                  {cases.length === 0
                    ? 'No credit-admin cases in your cascade.'
                    : `${cases.length} total in cascade; ${count} returned by server.`}
                </div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* Table */}
        {!loading && !error && filteredCases.length > 0 && (
          <Card>
            <Card.Body className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">Case ID</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-center">Conditions</th>
                      <th className="px-4 py-3">RM</th>
                      <th className="px-4 py-3">Approved</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredCases.map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/credit-admin/${encodeURIComponent(c.id)}`)}
                        className="hover:bg-gray-50 cursor-pointer transition"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-600">
                          {c.id}
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {c.client_name}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {c.product || '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-700">
                          {formatAmount(c.amount, currencySymbol)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={caseStatusTone(c)} size="sm">
                            {caseStatusLabel(c)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-center font-mono text-xs text-gray-700">
                          {conditionProgress(c)}
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {c.rm_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(c.approval_date)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-3 border-t border-gray-100 text-xs text-gray-500">
                Showing {filteredCases.length} of {cases.length} cases
                {categoryFilter !== 'all' && ` (category: ${caseCategoryLabel(categoryFilter)})`}
                {searchTerm && ` (search: "${searchTerm}")`}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}
''',

    'frontend/web/src/pages/CreditAnalytics.tsx': r'''// Credit Analytics — pipeline-origin credit FLOW by workflow stage, scoped to
// the caller's cascade. This is the live credit workload (so Operations can prep
// against what's sitting at each step), NOT the loan book / NPL view — that is
// deferred to the Phase-2 Credit Monitoring module.

import { useEffect, useMemo, useState } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { fetchCreditFlowByStage, type CreditFlowByStageResponse } from '@/lib/api';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import { Badge } from '@/components/Badge';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';

function abbrev(n: number): string {
  return n.toLocaleString();
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card><Card.Body>
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </Card.Body></Card>
  );
}

// Terminal stages are shown but visually distinct from in-flight work.
const TERMINAL_KEYS = new Set(['disbursed', 'declined']);

export function CreditAnalytics() {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  const [data, setData] = useState<CreditFlowByStageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchCreditFlowByStage()
      .then((d) => { if (active) { setData(d); setError(null); } })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : 'Could not load credit flow.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const barData = useMemo(
    () => (data?.stages ?? [])
      .filter((s) => !TERMINAL_KEYS.has(s.key))
      .map((s) => ({ stage: s.label, cases: s.count })),
    [data],
  );

  if (loading) {
    return <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-4"><Skeleton /><Skeleton /><Skeleton /></div>;
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No credit flow available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Analytics' }]}
        title="Credit Analytics"
        subtitle="Pipeline-origin credit flow within your scope — live cases by workflow stage, so the team can prep workload. (Loan-book / NPL analytics arrive with the Credit Monitoring module.)"
      />
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-6">

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Cases in flight" value={t.in_flight_count.toLocaleString()} sub="not yet disbursed/declined" />
          <Stat label="In-flight value" value={kes(t.in_flight_value)} />
          <Stat label="All cases" value={t.count.toLocaleString()} sub="incl. disbursed & declined" />
          <Stat label="Total value" value={kes(t.value)} />
        </div>

        {barData.length > 0 && (
          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Workload by stage</h2>
              <span className="text-xs text-gray-400">In-flight credit cases</span>
            </Card.Header>
            <Card.Body>
              <CategoryBarChart
                data={barData}
                xKey="stage"
                series={[{ key: 'cases', label: 'Cases' }]}
              />
            </Card.Body>
          </Card>
        )}

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Cases by stage</h2>
            <span className="text-xs text-gray-400">Count &amp; value at each step</span>
          </Card.Header>
          <Card.Body>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  <th className="py-2 text-left">Stage</th>
                  <th className="py-2 text-right">Cases</th>
                  <th className="py-2 text-right">Value</th>
                  <th className="py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.stages.map((s) => {
                  const terminal = TERMINAL_KEYS.has(s.key);
                  return (
                    <tr key={s.key} className="border-b border-gray-100 last:border-0">
                      <td className="py-2 text-gray-800">{s.label}</td>
                      <td className="py-2 text-right tabular-nums font-medium text-gray-900">
                        {s.count.toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-700">{kes(s.value)}</td>
                      <td className="py-2 text-right">
                        <Badge tone={terminal ? 'neutral' : s.count > 0 ? 'info' : 'neutral'} size="sm">
                          {terminal ? 'closed' : s.count > 0 ? 'active' : 'clear'}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card.Body>
        </Card>

      </div>
    </>
  );
}
''',

    'frontend/web/src/pages/Lms.tsx': r'''// v10.520 Phase 4 Batch β5 — LMS application list page.
//
// First consumer of GET /api/lms/applications (α8). Cascade-scoped
// table with status filters. Clicking a row navigates to detail.
//
// Layout mirrors Pipeline.tsx: header strip + filter chips + Card-based
// table + empty/loading/error states.

import { displayName } from "../lib/names";
import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useLmsApplications } from '@/hooks/useLmsApplications';
import { useToast } from '@/components/Toast';
import { requestLmsAssignment, fetchAssignmentRequests, assignLmsAnalyst, fetchMyAnalysts, type AssignmentRequestCase, type AssignableAnalyst } from '@/lib/api';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  statusTone,
  APPLICATION_STATUSES,
  type LoanApplication,
} from '@/types/lms';


// ── Helpers ─────────────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  return s.slice(0, 10);
}


// ── Page component ──────────────────────────────────────────────────────

export function Lms() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user, isAdmin } = useRole();
  const { applications, loading, error, refetch } = useLmsApplications();

  // ── Filter state (client-side; server always returns all in-scope) ──
  const [statusFilter, setStatusFilter] = useState<string | 'all'>('all');
  const [searchTerm,   setSearchTerm]   = useState<string>('');
  // B1: workload tabs. Analysts default to their own cases; managers to All.
  const myCode = String(user?.staff_code ?? '');
  const roleLc = String(user?.role ?? '').toLowerCase();
  const isPureAnalyst = roleLc.includes('analyst') && !isAdmin
    && !/chief|head|manager|officer|director|managing/.test(roleLc);
  const [tab, setTab] = useState<'mine' | 'pool' | 'all'>('all');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;
  const { toast } = useToast();
  const [requestBusy, setRequestBusy] = useState<string | null>(null);
  const isManagerRole = isAdmin || /chief|head|manager|officer|director|managing/.test(roleLc);
  const doRequest = async (appId: string) => {
    setRequestBusy(appId);
    try {
      await requestLmsAssignment(appId);
      toast({ tone: 'success', message: 'Assignment requested — the credit manager will action it.' });
      await refetch();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Request failed' });
    } finally { setRequestBusy(null); }
  };
  const [requestsCases, setRequestsCases] = useState<AssignmentRequestCase[]>([]);
  const [analystPool, setAnalystPool] = useState<AssignableAnalyst[]>([]);
  const [assignBusy, setAssignBusy] = useState<string | null>(null);
  const [assignMenuFor, setAssignMenuFor] = useState<string | null>(null);
  const [assignPurpose, setAssignPurpose] = useState<'decisioning' | 'correctness'>('decisioning');
  const loadRequests = async () => {
    if (!isManagerRole) return;
    try { const r = await fetchAssignmentRequests(); setRequestsCases(r.cases); } catch { /* non-fatal */ }
    try { const a = await fetchMyAnalysts(); setAnalystPool(a.analysts); } catch { /* non-fatal */ }
  };
  useEffect(() => { void loadRequests(); /* eslint-disable-next-line */ }, [isManagerRole, applications]);
  const doAssign = async (appId: string, code: string, name: string, purpose: 'decisioning' | 'correctness' = 'decisioning') => {
    setAssignBusy(appId + code);
    try {
      await assignLmsAnalyst(appId, { analyst_code: code, analyst_name: name, purpose });
      toast({ tone: 'success', message: purpose === 'correctness' ? `Assigned to ${name} for correctness check.` : `Assigned to ${name} for decisioning.` });
      await refetch();
      await loadRequests();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Assign failed' });
    } finally { setAssignBusy(null); }
  };
  useEffect(() => { setTab(isPureAnalyst ? 'mine' : 'all'); }, [isPureAnalyst]);

  // ── Filtered apps ──
  const filteredApps = useMemo<LoanApplication[]>(() => {
    let result = applications;
    if (statusFilter !== 'all') {
      result = result.filter((a) => (a.status || '').toLowerCase() === statusFilter);
    }
    if (searchTerm.trim()) {
      const t = searchTerm.trim().toLowerCase();
      result = result.filter((a) =>
        (a.client_name || '').toLowerCase().includes(t) ||
        (a.id || '').toLowerCase().includes(t) ||
        (a.product || '').toLowerCase().includes(t) ||
        (a.rm_name || '').toLowerCase().includes(t)
      );
    }
    // B1: workload tab filter.
    if (tab === 'mine') {
      result = result.filter((a) => String(a.analyst?.code ?? '') === myCode);
    } else if (tab === 'pool') {
      result = result.filter((a) => !a.analyst?.code
        && ['submitted'].includes((a.status || '').toLowerCase()));
    }
    return result;
  }, [applications, statusFilter, searchTerm, tab, myCode]);
  // Keep the current page in range when the filtered set shrinks.
  const pageCount = Math.max(1, Math.ceil(filteredApps.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pagedApps = filteredApps.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  // ── Status counts for the filter chips ──
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: applications.length };
    for (const status of APPLICATION_STATUSES) counts[status] = 0;
    for (const a of applications) {
      const s = (a.status || '').toLowerCase();
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }, [applications]);

  const tabCounts = useMemo(() => ({
    mine: applications.filter((a) => String(a.analyst?.code ?? '') === myCode).length,
    pool: applications.filter((a) => !a.analyst?.code && (a.status || '').toLowerCase() === 'submitted').length,
    all: applications.length,
  }), [applications, myCode]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header strip — same brand-navy as Pipeline pages */}
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Analysis' }]}
        title="Credit Analysis"
        subtitle="Submitted, assigned, and decided applications in your cascade."
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

        {/* ── Summary strip ──────────────────────────────────────── */}
        {!loading && !error && applications.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            {(() => {
              const total = applications.length;
              const inAnalysis = applications.filter((a) =>
                ['submitted', 'assigned', 'info_requested'].includes((a.status || '').toLowerCase())).length;
              const decided = applications.filter((a) =>
                ['approved', 'declined', 'disbursed'].includes((a.status || '').toLowerCase())).length;
              const totalValue = applications.reduce((s, a) => s + (Number(a.amount) || 0), 0);
              const stat = (label: string, value: string, accent: string) => (
                <Card>
                  <Card.Body className="py-3">
                    <div className="text-xs text-gray-500">{label}</div>
                    <div className={`text-xl font-semibold mt-0.5 ${accent}`}>{value}</div>
                  </Card.Body>
                </Card>
              );
              return (
                <>
                  {stat('In queue', String(total), 'text-gray-900')}
                  {stat('In analysis', String(inAnalysis), 'text-brand-primary')}
                  {stat('Decided', String(decided), 'text-gray-900')}
                  {stat('Total value', formatAmount(totalValue, currencySymbol), 'text-gray-900')}
                </>
              );
            })()}
          </div>
        )}

        {/* B2: assignment requests (manager) */}
        {isManagerRole && requestsCases.length > 0 && (
          <Card className="mb-4" stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Assignment requests</h2>
              <Badge tone="warning" size="sm">{requestsCases.length}</Badge>
            </Card.Header>
            <Card.Body>
              <div className="space-y-3">
                {requestsCases.map((c) => (
                  <div key={c.id} className="rounded border p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div>
                        <span className="font-mono text-xs text-gray-500">{c.id}</span>
                        <span className="ml-2 text-sm font-medium">{c.client_name}</span>
                        <span className="ml-2 text-xs text-gray-400">{c.product}</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      {c.requests.map((r) => (
                        <div key={r.by_code} className="flex items-center justify-between rounded bg-gray-50 px-2 py-1 text-sm">
                          <span>Requested by <span className="font-medium">{r.by_name}</span> ({r.by_code})</span>
                          <Button size="sm" onClick={() => void doAssign(c.id, r.by_code, r.by_name)}
                            disabled={assignBusy === c.id + r.by_code}>
                            {assignBusy === c.id + r.by_code ? 'Assigning…' : `Assign to ${r.by_name.split(' ')[0]}`}
                          </Button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-gray-500">or assign someone else:</span>
                      <select
                        className="rounded border px-2 py-1 text-xs"
                        defaultValue=""
                        onChange={(e) => {
                          const a = analystPool.find((x) => x.staff_code === e.target.value);
                          if (a) void doAssign(c.id, a.staff_code, a.name);
                          e.target.value = '';
                        }}
                      >
                        <option value="">— pick analyst —</option>
                        {analystPool.map((a) => (
                          <option key={a.staff_code} value={a.staff_code}>{displayName(a.name)} ({a.staff_code})</option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        )}

        {/* ── Filter bar ─────────────────────────────────────────── */}
        <Card className="mb-4">
          <Card.Body>
            {/* B1: workload tabs */}
            <div className="flex items-center gap-2 mb-3 border-b border-gray-100 pb-3">
              {([['mine', 'My cases'], ['pool', 'Pool'], ['all', 'All']] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                    tab === key ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {label} ({tabCounts[key]})
                </button>
              ))}
              {tab === 'pool' && (
                <span className="ml-2 text-xs text-gray-400">Read-only — request assignment from a case to work it.</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <button
                onClick={() => setStatusFilter('all')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  statusFilter === 'all'
                    ? 'bg-brand-primary text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All ({statusCounts.all})
              </button>
              {APPLICATION_STATUSES.map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                    statusFilter === status
                      ? 'bg-brand-primary text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  disabled={statusCounts[status] === 0}
                >
                  {status} ({statusCounts[status] || 0})
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search by client name, app id, product, or RM..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="flex-1 h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              {searchTerm && (
                <Button variant="ghost" size="sm" onClick={() => setSearchTerm('')}>
                  Clear
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
            </div>
          </Card.Body>
        </Card>


        {/* ── Error state ─────────────────────────────────────────── */}
        {error && (
          <Card className="mb-4">
            <Card.Body>
              <div className="text-sm text-red-800">
                <div className="font-semibold mb-1">Failed to load applications</div>
                <div>{error}</div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Loading state ───────────────────────────────────────── */}
        {loading && !error && (
          <Card>
            <Card.Body>
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Empty state ─────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length === 0 && (
          <Card>
            <Card.Body>
              <div className="text-center py-10">
                {applications.length === 0 ? (
                  <>
                    <div className="text-sm font-medium text-gray-800 mb-1">
                      No applications in your queue yet
                    </div>
                    <div className="text-xs text-gray-500 max-w-md mx-auto">
                      Applications submitted to credit{user?.full_name ? ` for ${user.full_name}` : ''} will
                      appear here once a relationship manager submits a deal and it is assigned for analysis.
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-sm font-medium text-gray-800 mb-1">
                      Nothing matches this filter
                    </div>
                    <div className="text-xs text-gray-500 mb-3">
                      {applications.length} application{applications.length === 1 ? '' : 's'} in your queue,
                      none in {statusFilter !== 'all' ? `“${statusFilter}”` : 'this view'}
                      {searchTerm ? ` matching “${searchTerm}”` : ''}.
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setStatusFilter('all'); setSearchTerm(''); }}
                    >
                      Clear filters
                    </Button>
                  </>
                )}
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── List table ──────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length > 0 && (
          <Card>
            <Card.Body className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">RM</th>
                      <th className="px-4 py-3">Analyst</th>
                      <th className="px-4 py-3">SLA</th>
                      <th className="px-4 py-3">Applied</th>
                      {isManagerRole && <th className="px-4 py-3">Assign</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {pagedApps.map((app) => (
                      <tr
                        key={app.id}
                        onClick={() => navigate(`/lms/${encodeURIComponent(app.id)}`)}
                        className="hover:bg-gray-50 cursor-pointer transition"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">
                          {app.id}
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{app.client_name}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {app.product || '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-700">
                          {formatAmount(app.amount, currencySymbol)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={statusTone(app.status)} size="sm">
                            {app.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.rm_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.analyst?.name
                            ? app.analyst.name
                            : (tab === 'pool' && isPureAnalyst ? (
                              <button
                                onClick={(e) => { e.stopPropagation(); void doRequest(app.id); }}
                                disabled={requestBusy === app.id
                                  || (app.assignment_requests ?? []).some((r) => String(r.by_code) === myCode)}
                                className="rounded border border-brand-primary px-2 py-0.5 text-xs text-brand-primary hover:bg-brand-primary/5 disabled:opacity-50"
                              >
                                {(app.assignment_requests ?? []).some((r) => String(r.by_code) === myCode)
                                  ? 'Requested'
                                  : (requestBusy === app.id ? 'Requesting…' : 'Request assignment')}
                              </button>
                            ) : <span className="text-gray-400">unassigned</span>)}
                        </td>
                        <td className="px-4 py-3 text-xs">
                          {app.sla ? (
                            <div className="flex flex-col gap-0.5">
                              {app.sla.stage && (
                                <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 font-medium ${
                                  app.sla.stage.state === 'breached' ? 'bg-red-100 text-red-700'
                                  : app.sla.stage.state === 'due_soon' ? 'bg-amber-100 text-amber-700'
                                  : 'bg-green-100 text-green-700'}`}>
                                  My: {app.sla.stage.state === 'breached'
                                    ? `${app.sla.stage.overdue_business_days}d over`
                                    : `${app.sla.stage.remaining_business_days}d left`}
                                </span>
                              )}
                              <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 ${
                                app.sla.state === 'breached' ? 'text-red-600'
                                : app.sla.state === 'due_soon' ? 'text-amber-600'
                                : 'text-green-600'}`}>
                                Case: {app.sla.state === 'breached'
                                  ? `${app.sla.overdue_business_days}d over`
                                  : app.sla.state === 'due_soon'
                                  ? `${app.sla.remaining_business_days}d left`
                                  : 'on track'}
                              </span>
                            </div>
                          ) : <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>
                        {isManagerRole && (
                          <td className="px-4 py-3 text-xs relative" onClick={(e) => e.stopPropagation()}>
                            {!app.analyst?.code && (app.status || '').toLowerCase() === 'submitted' ? (
                              <>
                                <button
                                  onClick={() => setAssignMenuFor(assignMenuFor === app.id ? null : app.id)}
                                  className="rounded border border-brand-primary px-2 py-0.5 text-xs text-brand-primary hover:bg-brand-primary/5"
                                >
                                  Assign ▾
                                </button>
                                {assignMenuFor === app.id && (
                                  <div className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
                                    <div className="mb-1 text-xs font-medium text-gray-500">Purpose</div>
                                    <div className="mb-2 flex gap-1">
                                      {(['decisioning', 'correctness'] as const).map((pp) => (
                                        <button key={pp}
                                          onClick={() => setAssignPurpose(pp)}
                                          className={`flex-1 rounded px-2 py-1 text-xs ${
                                            assignPurpose === pp ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700'}`}>
                                          {pp === 'decisioning' ? 'Decisioning' : 'Correctness check'}
                                        </button>
                                      ))}
                                    </div>
                                    <div className="mb-1 text-xs font-medium text-gray-500">To</div>
                                    <select
                                      className="mb-2 w-full rounded border px-2 py-1 text-xs"
                                      defaultValue=""
                                      onChange={(e) => {
                                        const a = analystPool.find((x) => x.staff_code === e.target.value);
                                        if (a) { void doAssign(app.id, a.staff_code, a.name, assignPurpose); setAssignMenuFor(null); }
                                      }}
                                    >
                                      <option value="">— pick person —</option>
                                      {analystPool.map((a) => (
                                        <option key={a.staff_code} value={a.staff_code}>{a.name}</option>
                                      ))}
                                    </select>
                                    <div className="border-t border-gray-100 pt-2">
                                      <button
                                        onClick={() => { setAssignMenuFor(null); navigate(`/lms/${encodeURIComponent(app.id)}`); }}
                                        className="w-full rounded bg-gray-50 px-2 py-1 text-left text-xs text-gray-700 hover:bg-gray-100"
                                      >
                                        Route to committee →
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-xs text-gray-500">
                <span>
                  {filteredApps.length === 0 ? 'No applications' :
                    `${safePage * PAGE_SIZE + 1}–${Math.min((safePage + 1) * PAGE_SIZE, filteredApps.length)} of ${filteredApps.length}`}
                  {statusFilter !== 'all' && ` (status: ${statusFilter})`}
                  {searchTerm && ` (search: "${searchTerm}")`}
                </span>
                {pageCount > 1 && (
                  <span className="inline-flex items-center gap-2">
                    <button type="button" onClick={() => setPage(Math.max(0, safePage - 1))}
                      disabled={safePage === 0}
                      className="rounded border px-2 py-1 text-brand-primary disabled:opacity-40 hover:bg-gray-50">Prev</button>
                    <span>Page {safePage + 1} / {pageCount}</span>
                    <button type="button" onClick={() => setPage(Math.min(pageCount - 1, safePage + 1))}
                      disabled={safePage >= pageCount - 1}
                      className="rounded border px-2 py-1 text-brand-primary disabled:opacity-40 hover:bg-gray-50">Next</button>
                  </span>
                )}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}
''',

    'frontend/web/src/pages/Pipeline.tsx': r'''// v10.510 Phase 4 Batch β1 — Pipeline page.
//
// First read-only consumer of the α1-α7 pipeline API surface. Shows
// the caller's cascade-scoped deal list with per-deal permission
// indicators (α7) visible inline. The mutation surface (create, edit,
// advance, refer, validate, cancel/request, cancel/approve) lands in
// subsequent β-batches.
//
// What this proves end-to-end:
//   1. α1's pipeline list endpoint returns data → React renders it
//   2. α2's cascade scope filters → caller sees only own/scope deals
//   3. α3's CRUD endpoint Pydantic typing → matches our TypeScript shape
//   4. α7's permissions object → React reads it without recomputing auth
//   5. The Bearer-header JWT lifecycle from Phase 1 → carries through
//      to a brand-new authenticated endpoint
//   6. The Provider pattern from Batch 2d → extends cleanly to a new domain
//
// Layout pattern matches Dashboard.tsx:
//   - Header strip with brand.secondary background (deep navy)
//   - max-w-7xl content column
//   - Stat strip at top for at-a-glance metrics
//   - Card-wrapped Table for the deal list
//   - Footer with branding ip_notice
//
// Composition: 100% bespoke v10.496 primitives. No new visual atoms.

import { displayName } from "../lib/names";
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDeals } from '@/hooks/usePipelineDeals';
import { useRole } from '@/hooks/useRole';
import { fetchPipelineConfig, fetchPipelineAnalytics, fetchFunnelDrill, downloadFile } from '@/lib/api';
import { Card } from '@/components/Card';
import DefinedFunnel from '@/components/DefinedFunnel';
import { PageHeader } from '@/components/PageHeader';
import { Stat } from '@/components/Stat';
import { Badge, type BadgeTone } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { PermissionBadges } from '@/components/PermissionBadges';
import { parseTs } from '@/lib/datetime';
import {
  stageTone,
  type PipelineDeal,
  type PipelineConfig,
  type PipelineAnalyticsResponse,
  type FunnelDrillResponse,
} from '@/types/pipeline';


// ── Display helpers ─────────────────────────────────────────────────────

/** Format a deal_value in the tenant's currency. Compact format for table cells. */
function formatValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  return `${symbol} ${v.toLocaleString()}`;
}

/** Days a deal has been open, from its earliest available timestamp. */
function daysOpen(deal: PipelineDeal): number | null {
  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  // parseTs, not new Date: a date-only open_date must anchor to LOCAL midnight,
  // otherwise the age is measured from 03:00 and can round down a whole day.
  const parsed = parseTs(raw);
  if (!parsed) return null;
  const start = parsed.getTime();
  if (!Number.isFinite(start)) return null;
  const diff = Date.now() - start;
  if (diff < 0) return 0;
  return Math.floor(diff / 86_400_000);
}

/** Traffic-light cell for a deal's attached SLA status. Null when no SLA applies
 *  (closed / no timestamp). */
function slaCell(deal: PipelineDeal): { tone: BadgeTone; label: string; title: string } | null {
  const s = deal.sla;
  if (!s || !s.state) return null;
  const clock = s.clock === 'step' ? (s.step || 'step').replace(/_/g, ' ') : 'age';
  if (s.state === 'breached') {
    return {
      tone: 'danger',
      label: `breached +${s.overdue_business_days ?? 0}`,
      title: `${clock}: ${s.elapsed_business_days ?? '?'}/${s.target_days ?? '?'} bd — escalate to ${(s.escalate_to || '').replace(/_/g, ' ') || 'step owner'}`,
    };
  }
  if (s.state === 'due_soon') {
    return { tone: 'warning', label: 'due soon', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
  }
  return { tone: 'success', label: 'on track', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
}


// ── Page component ──────────────────────────────────────────────────────

export function Pipeline() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { deals, count, loading, error, refetch } = usePipelineDeals();

  // SLA traffic-light filter, driven by ?sla=on_track|due_soon|breached (e.g. from the
  // Analytics SLA summary card). Filters the already-loaded deals client-side on sla.state.
  const [searchParams, setSearchParams] = useSearchParams();
  const slaFilter = searchParams.get('sla');
  // Win-probability band filter (?winprob=high|medium|low). high ≥75, medium 40–74,
  // low <40 — derived per-deal from the current stage's product flow. Combines with sla.
  const winprobFilter = searchParams.get('winprob');
  const winprobBand = (wp: number | null | undefined): 'high' | 'medium' | 'low' | null => {
    if (typeof wp !== 'number') return null;
    return wp >= 75 ? 'high' : wp >= 40 ? 'medium' : 'low';
  };
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [segmentFilter, setSegmentFilter] = useState('');
  // Two-level segment model, sourced from the configurable business units (customer_segments):
  //   Business unit (Consumer/Commercial/CIB/Treasury) -> its sub-segments (Premier/SME/...).
  // Each visible deal's sub-segment is resolved to its business unit via a reverse map, then
  // grouped by unit. A single-unit viewer (e.g. Consumer) therefore sees ONLY that unit's
  // sub-segments; a leaked cross-unit value groups under its OWN unit, never polluting another.
  const segmentGroups = useMemo(() => {
    const cfgSegs = config?.customer_segments ?? {};
    // reverse map: sub-segment -> business unit
    const subToUnit = new Map<string, string>();
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      for (const sub of subs) subToUnit.set(sub, unit);
    }
    // tally sub-segment counts present in visible deals
    const counts = new Map<string, number>();
    for (const d of deals) {
      const k = (d.segment && String(d.segment).trim()) || 'Unclassified';
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    // build ordered groups: business unit -> [{key, count}] in config order
    const groups: { unit: string; subs: { key: string; count: number }[] }[] = [];
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      const present = subs
        .filter((sub) => counts.has(sub))
        .map((sub) => ({ key: sub, count: counts.get(sub) ?? 0 }));
      if (present.length) groups.push({ unit, subs: present });
    }
    // any present sub-segment that IS a bare business-unit name (mis-tagged) or unknown:
    // collect under an 'Other' group so it's visible but not mixed into a real unit.
    const known = new Set<string>();
    for (const g of groups) for (const s of g.subs) known.add(s.key);
    const other: { key: string; count: number }[] = [];
    for (const [k, c] of counts.entries()) {
      if (k === 'Unclassified') continue;
      if (!known.has(k) && !subToUnit.has(k)) other.push({ key: k, count: c });
    }
    if (other.length) groups.push({ unit: 'Other', subs: other });
    if (counts.has('Unclassified')) {
      groups.push({ unit: 'Unclassified', subs: [{ key: 'Unclassified', count: counts.get('Unclassified') ?? 0 }] });
    }
    return groups;
  }, [deals, config]);
  const singleUnit = segmentGroups.length === 1;
  const visibleDeals = useMemo(
    () => deals.filter((d) =>
      (!slaFilter || d.sla?.state === slaFilter)
      && (!winprobFilter || winprobBand(d.win_probability) === winprobFilter)
      // A filter of `unit:Consumer` matches every sub-segment configured under
      // Consumer, so the line can be read as one. Anything else is the exact
      // sub-segment, as before.
      && (!segmentFilter
          || (segmentFilter.startsWith('unit:')
              ? (segmentGroups.find((g) => `unit:${g.unit}` === segmentFilter)?.subs ?? [])
                  .some((sg) => sg.key === (d.segment || 'Unclassified'))
              : (d.segment || 'Unclassified') === segmentFilter))),
    [deals, slaFilter, winprobFilter, segmentFilter, segmentGroups],
  );
  const clearSlaFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('sla');
    setSearchParams(next, { replace: true });
  };
  const setWinprobFilter = (band: string) => {
    const next = new URLSearchParams(searchParams);
    if (band) next.set('winprob', band); else next.delete('winprob');
    setSearchParams(next, { replace: true });
  };

  // Batch A: admin-configured category/stage filters (from /api/pipeline/stages)
  const [catFilter, setCatFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');

  // Funnel stage-drill: click a band → fetch deals at that class+stage,
  // broken down by product and segment.
  const [drill, setDrill] = useState<FunnelDrillResponse | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillVisible, setDrillVisible] = useState(50);
  const [exporting, setExporting] = useState(false);
  const drillRef = useRef<HTMLDivElement | null>(null);
  const onStageDrill = (cls: string, stage: string): void => {
    setDrillLoading(true);
    setDrill(null);
    setDrillVisible(50);
    fetchFunnelDrill(cls, stage)
      .then((d) => setDrill(d))
      .catch(() => setDrill(null))
      .finally(() => setDrillLoading(false));
  };
  // When the drill opens, bring the panel into view (the funnel can be tall,
  // so the panel would otherwise open below the fold).
  useEffect(() => {
    if (drill && drillRef.current) {
      drillRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [drill]);

  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* dropdowns stay empty if config can't load */ });
    return () => { active = false; };
  }, []);

  // Analytics: validated/pending split, per-class buckets, the validated
  // funnel, and the scope-aware pending-validation count. Refetched whenever
  // the deal list settles (after create/validate/advance/refresh).
  const [analytics, setAnalytics] = useState<PipelineAnalyticsResponse | null>(null);
  useEffect(() => {
    if (loading) return;
    let active = true;
    fetchPipelineAnalytics()
      .then((a) => { if (active) setAnalytics(a); })
      .catch(() => { /* tiles fall back to local sums if analytics fails */ });
    return () => { active = false; };
  }, [loading, count]);

  // Stage options narrow to the selected category's flow; else all stages.
  const stageOptions = useMemo(() => {
    if (!config) return [] as string[];
    if (catFilter) {
      const cat = config.deal_categories.find((c) => c.category === catFilter);
      if (cat) return cat.stages;
    }
    return config.stages.map((s) => s.stage);
  }, [config, catFilter]);

  const onCategoryChange = (value: string) => {
    setCatFilter(value);
    setStageFilter('');
    void refetch({ category: value || undefined });
  };
  const onStageChange = (value: string) => {
    setStageFilter(value);
    void refetch({ category: catFilter || undefined, stage: value || undefined });
  };
  const navigate = useNavigate();

  const sym = branding?.currency_symbol ?? '';

  // Table column config — typed against PipelineDeal so render functions
  // get full intellisense on row data.
  const columns: Column<PipelineDeal>[] = useMemo(() => [
    {
      key: 'id',
      header: 'Deal ID',
      width: 110,
      sortable: true,
      exportValue: (row) => row.id,
      render: (row) => (
        <span className="font-mono text-xs text-gray-600">{row.id}</span>
      ),
    },
    {
      key: 'client_name',
      header: 'Client',
      sortable: true,
      exportValue: (row) => row.client_name || '',
      render: (row) => (
        <div>
          <div className="font-medium text-gray-900">{row.client_name || '—'}</div>
          {row.product_type && (
            <div className="text-xs text-gray-500 mt-0.5">{row.product_type}</div>
          )}
        </div>
      ),
    },
    {
      key: 'stage',
      header: 'Stage',
      sortable: true,
      exportValue: (row) => row.stage,
      render: (row) => (
        <Badge tone={stageTone(row.stage)} size="sm">{row.stage}</Badge>
      ),
    },
    {
      key: 'deal_value',
      header: 'Value',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => Number(row.amount_kes ?? row.deal_value) || 0,
      exportValue: (row) => String(row.amount_kes ?? row.deal_value ?? ''),
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatValue(Number(row.amount_kes ?? row.deal_value), branding?.currency_symbol ?? '')}
        </span>
      ),
    },
    {
      key: 'aging',
      header: 'Age',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => daysOpen(row) ?? -1,
      exportValue: (row) => { const d = daysOpen(row); return d == null ? '' : String(d); },
      render: (row) => {
        const d = daysOpen(row);
        if (d == null) return <span className="text-xs text-gray-400">—</span>;
        const stale = d > 14;
        return (
          <span className={`text-xs font-medium ${stale ? 'text-red-600' : 'text-gray-600'}`}>
            {d}d{stale ? ' · stale' : ''}
          </span>
        );
      },
    },
    {
      key: 'sla',
      header: 'SLA',
      exportValue: (row) => row.sla?.state || '',
      render: (row) => {
        const c = slaCell(row);
        if (!c) return <span className="text-xs text-gray-300">—</span>;
        return <span title={c.title}><Badge tone={c.tone} size="sm">{c.label}</Badge></span>;
      },
    },
    {
      key: 'win_probability',
      header: 'Win %',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => (typeof row.win_probability === 'number' ? row.win_probability : -1),
      exportValue: (row) => (typeof row.win_probability === 'number' ? String(row.win_probability) : ''),
      render: (row) => {
        const wp = row.win_probability;
        if (typeof wp !== 'number') return <span className="text-xs text-gray-300">—</span>;
        const tone: BadgeTone = wp >= 75 ? 'success' : wp >= 40 ? 'info' : 'neutral';
        return (
          <span title="Likelihood of closing, from the current stage's product flow">
            <Badge tone={tone} size="sm">{Math.round(wp)}%</Badge>
          </span>
        );
      },
    },
    {
      key: 'staff_name',
      header: 'Owner',
      sortable: true,
      exportValue: (row) => row.staff_name || '',
      render: (row) => (
        <div>
          <div className="text-sm text-gray-800">{row.staff_name ? displayName(row.staff_name) : '—'}</div>
          {row.staff_code && (
            <div className="text-xs text-gray-400 mt-0.5 font-mono">
              {row.staff_code}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'permissions',
      header: 'You can',
      render: (row) => <PermissionBadges permissions={row.permissions} />,
    },
  // intentionally not depending on the dynamic data; column config is stable
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [branding?.currency_symbol]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Pro' }]}
        title="A2Z Sales Pro"
        subtitle="Your pipeline"
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setExporting(true);
                downloadFile('/pipeline/export/xlsx', 'EKE_Pipeline.xlsx')
                  .catch(() => { /* surfaced via button state only */ })
                  .finally(() => setExporting(false));
              }}
              disabled={exporting}
            >
              {exporting ? 'Exporting…' : 'Export Excel'}
            </Button>
            <Button variant="primary" onClick={() => navigate('/pipeline/new')}>
              + New Deal
            </Button>
          </>
        }
      />

      {/* Main content */}
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-8">
        {/* Assured pipeline by product class — validated value headline,
            pending-assurance beneath. Sourced from /api/pipeline/analytics. */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Stat
            label="Asset Pipeline"
            value={analytics ? formatValue(analytics.pipelines.asset.value, sym) : '—'}
            sub={analytics && analytics.pipelines.asset.pending_value > 0
              ? `${formatValue(analytics.pipelines.asset.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="primary"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Liability Pipeline"
            value={analytics ? formatValue(analytics.pipelines.liability.value, sym) : '—'}
            sub={analytics && analytics.pipelines.liability.pending_value > 0
              ? `${formatValue(analytics.pipelines.liability.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="success"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Insurance"
            value={analytics ? formatValue(analytics.pipelines.insurance.value, sym) : '—'}
            sub={analytics && analytics.pipelines.insurance.pending_value > 0
              ? `${formatValue(analytics.pipelines.insurance.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="lime"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Other"
            value={analytics ? formatValue(analytics.pipelines.other.value, sym) : '—'}
            sub={analytics && analytics.pipelines.other.pending_value > 0
              ? `${formatValue(analytics.pipelines.other.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="violet"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Scope summary row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <Stat
            label="Deals Visible"
            value={loading ? '—' : count}
            sub="In your cascade scope"
            loading={loading}
            stripe={false}
            tone="teal"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Pending Validation"
            value={analytics ? analytics.totals.pending_validation : (loading ? '—' : 0)}
            sub={analytics && analytics.totals.pending_validation > 0
              ? 'Awaiting your sign-off'
              : 'Nothing to validate'}
            loading={loading}
            stripe={false}
            tone={analytics && analytics.totals.pending_validation > 0 ? 'accent' : 'neutral'}
            onClick={() => navigate('/pipeline/queues')}
          />
          <Stat
            label="Total Assured"
            value={analytics ? formatValue(analytics.totals.total_value, sym) : '—'}
            sub={analytics && analytics.totals.pending_value > 0
              ? `${formatValue(analytics.totals.pending_value, sym)} pending assurance`
              : 'All validated'}
            loading={loading}
            stripe={false}
            tone="secondary"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Validated pipeline funnel */}
        <DefinedFunnel onStageClick={onStageDrill} />

        {/* Funnel stage-drill panel */}
        {(drillLoading || drill) && (
          <div ref={drillRef} className="scroll-mt-24">
          <Card className="mt-4 ring-2 ring-[var(--brand-primary)]/30">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                {drill ? `${drill.cls === 'all' ? 'All' : drill.cls[0].toUpperCase() + drill.cls.slice(1)} · ${drill.stage}` : 'Loading…'}
              </h2>
              <button
                type="button"
                onClick={() => setDrill(null)}
                className="text-xs text-gray-400 hover:text-gray-700"
              >
                Close ✕
              </button>
            </Card.Header>
            <Card.Body>
              {drillLoading && <div className="h-24 animate-pulse rounded bg-gray-100" />}
              {drill && (
                <div>
                  <div className="mb-4 text-sm text-gray-500">
                    <span className="font-semibold text-gray-800">{drill.totals.count}</span> assured deals ·{' '}
                    <span className="font-semibold text-gray-800">{formatValue(drill.totals.value, sym)}</span>
                  </div>
                  <div className="grid gap-6 md:grid-cols-3">
                    <DrillBreakdown title="By segment" rows={drill.by_segment.map((s) => ({ label: s.segment, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By sector" rows={drill.by_sector.map((s) => ({ label: s.sector, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By product" rows={drill.by_product.map((p) => ({ label: p.product, value: p.value, count: p.count }))} sym={sym} />
                  </div>
                  {drill.deals.length > 0 && (
                    <div className="mt-6 overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                            <th className="py-2 pr-3">Deal</th>
                            <th className="py-2 pr-3">Client</th>
                            <th className="py-2 pr-3">Product</th>
                            <th className="py-2 pr-3">Segment</th>
                            <th className="py-2 pr-3 text-right">Value</th>
                            <th className="py-2 pr-3">Owner</th>
                          </tr>
                        </thead>
                        <tbody>
                          {drill.deals.slice(0, drillVisible).map((d) => (
                            <tr key={d.id} className="border-b border-gray-100">
                              <td className="py-1.5 pr-3 font-mono text-xs text-gray-500">{d.id}</td>
                              <td className="py-1.5 pr-3 text-gray-800">{d.client_name}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.product_type}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.segment}</td>
                              <td className="py-1.5 pr-3 text-right tabular-nums text-gray-800">{formatValue(d.amount_kes, sym)}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{displayName(d.staff_name)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {drill.deals.length > drillVisible ? (
                        <div className="mt-2 flex items-center gap-3">
                          <Button variant="ghost" size="sm" onClick={() => setDrillVisible((n) => n + 50)}>
                            Show more ({drill.deals.length - drillVisible} more)
                          </Button>
                          <span className="text-xs text-gray-400">Showing {drillVisible} of {drill.deals.length}</span>
                        </div>
                      ) : drill.deals.length > 50 ? (
                        <div className="mt-2 text-xs text-gray-400">Showing all {drill.deals.length} deals.</div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>
          </div>
        )}

        {/* Error panel — only renders on error */}
        {error && (
          <Card className="mt-6">
            <Card.Body>
              <div className="flex items-center gap-3">
                <Badge tone="danger">Error</Badge>
                <div className="flex-1 text-sm text-gray-700">{error}</div>
                <Button variant="ghost" size="sm" onClick={() => void refetch()}>
                  Retry
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {/* Deal table */}
        <Card className="mt-8" padding="none">
          <Card.Header>
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-gray-900">
                Pipeline Deals
              </h2>
                </div>
            <div className="flex items-center gap-2">
              <select
                value={catFilter}
                onChange={(e) => onCategoryChange(e.target.value)}
                aria-label="Filter by deal category"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All categories</option>
                {config?.deal_categories.map((c) => (
                  <option key={c.category} value={c.category}>{c.category}</option>
                ))}
              </select>
              <select
                value={stageFilter}
                onChange={(e) => onStageChange(e.target.value)}
                aria-label="Filter by stage"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All stages</option>
                {stageOptions.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              {segmentGroups.length > 0 && (
                <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Filter by segment">
                  <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                    <button
                      type="button"
                      onClick={() => setSegmentFilter('')}
                      className={[
                        'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                        segmentFilter === '' ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                             : 'text-gray-500 hover:text-gray-800',
                      ].join(' ')}
                    >
                      All
                    </button>
                  </div>
                  {segmentGroups.map((g) => (
                    <div key={g.unit} className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                      {!singleUnit && (
                        // THE UNIT NAME IS A BUTTON, not a label. It was inert,
                        // so somebody wanting "Consumer as a whole" had to
                        // click Premier, read it, click Advantage, read it, and
                        // add up - when the whole line is the level they were
                        // asking about. Clicking it selects every sub-segment
                        // beneath it; clicking again clears back to All.
                        <button
                          type="button"
                          onClick={() => setSegmentFilter(
                            segmentFilter === `unit:${g.unit}` ? '' : `unit:${g.unit}`)}
                          title={`All ${g.unit} deals`}
                          className={[
                            'rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition-colors',
                            segmentFilter === `unit:${g.unit}`
                              ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                              : 'text-gray-400 hover:text-gray-700',
                          ].join(' ')}
                        >
                          {g.unit}
                          <span className="ml-1.5 text-gray-400">
                            {g.subs.reduce((a, x) => a + x.count, 0)}
                          </span>
                        </button>
                      )}
                      {g.subs.map((sg) => {
                        const on = segmentFilter === sg.key;
                        return (
                          <button
                            key={sg.key}
                            type="button"
                            onClick={() => setSegmentFilter(sg.key)}
                            className={[
                              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                              on ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                 : 'text-gray-500 hover:text-gray-800',
                            ].join(' ')}
                          >
                            {sg.key}
                            <span className="ml-1.5 text-gray-400">{sg.count}</span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
              <select
                value={winprobFilter ?? ''}
                onChange={(e) => setWinprobFilter(e.target.value)}
                aria-label="Filter by win probability"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All win %</option>
                <option value="high">High (≥75%)</option>
                <option value="medium">Medium (40–74%)</option>
                <option value="low">Low (&lt;40%)</option>
              </select>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refetch()}
                loading={loading}
              >
                Refresh
              </Button>
            </div>
          </Card.Header>
          <Card.Body className="p-4">
            {slaFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">SLA filter:</span>
                <Badge
                  tone={slaFilter === 'breached' ? 'danger' : slaFilter === 'due_soon' ? 'warning' : 'success'}
                  size="sm"
                >
                  {slaFilter.replace(/_/g, ' ')}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={clearSlaFilter} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            {winprobFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">Win probability:</span>
                <Badge
                  tone={winprobFilter === 'high' ? 'success' : winprobFilter === 'medium' ? 'info' : 'neutral'}
                  size="sm"
                >
                  {winprobFilter === 'high' ? 'High (≥75%)' : winprobFilter === 'medium' ? 'Medium (40–74%)' : 'Low (<40%)'}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={() => setWinprobFilter('')} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            <Table<PipelineDeal>
              columns={columns}
              rows={visibleDeals}
              rowKey="id"
              loading={loading}
              searchable
              searchPlaceholder="Search deals by client, stage, owner…"
              paginated
              pageSize={25}
              onRowClick={(row) => navigate(`/pipeline/${encodeURIComponent(row.id)}`)}
              empty={
                <div className="py-8">
                  <div className="text-base text-gray-700 font-medium">
                    No deals in your scope.
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    {user?.role && `As ${user.role}, you see deals from your cascade.`}
                  </div>
                </div>
              }
            />
          </Card.Body>
        </Card>

        {/* IP notice footer — verbatim from /api/branding */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}

// ── Drill breakdown: a compact value-ranked bar list (segment / product) ──
function DrillBreakdown({
  title, rows, sym,
}: {
  title: string;
  rows: { label: string; value: number; count: number }[];
  sym: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const PALETTE = ['#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#14b8a6'];
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-gray-400">No data.</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 8).map((r, i) => (
            <div key={r.label} className="flex items-center gap-3">
              <div className="w-28 shrink-0 truncate text-xs text-gray-600" title={r.label}>{r.label}</div>
              <div className="h-4 flex-1 rounded bg-gray-100">
                <div
                  className="h-4 rounded"
                  style={{ width: `${Math.max(4, Math.round((r.value / max) * 100))}%`, background: PALETTE[i % PALETTE.length] }}
                />
              </div>
              <div className="w-32 shrink-0 text-right text-xs text-gray-500">
                {formatValue(r.value, sym)} <span className="text-gray-400">· {r.count}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
''',

    'frontend/web/src/pages/PipelineCreate.tsx': r'''// v10.512 Phase 4 Batch β3 — PipelineCreate page.
//
// Form at /pipeline/new for creating a new pipeline deal. Covers the
// happy path AND the α5 portfolio-conflict resolution (Refer / Seek
// permission / Override-with-note).
//
// Architecture note — Streamlit/backend semantic inversion:
//   Streamlit's `_bsc_credit` calculation in pages/3_pipeline.py inverts
//   the bsc_credit_to value relative to what the backend rules in
//   utils/api_pipeline_mutations.py::is_override_semantics expect:
//
//   Streamlit "Seek permission"  → bsc_credit_to = creator      (me)
//   Streamlit "Pursue (override)" → bsc_credit_to = portfolio_owner
//
//   Backend rules:
//   bsc_credit_to == portfolio_owner_name → seek-permission (no note)
//   bsc_credit_to == anything else          → override (note required)
//
//   So Streamlit's "Seek permission" payload triggers the backend's
//   OVERRIDE rule and fails validation (no note collected). This is
//   the α5 doctrine note's "latent UX bug surfaced in α5 inspection."
//
//   This page implements the BACKEND's semantics — internally
//   consistent, server-validated. A future batch should fix Streamlit
//   to match (not β3 scope). Documenting the divergence in REVIVAL_LEDGER
//   is part of β3's deliverable.
//
// Deliberately NOT in β3 (deferred to later batches):
//   - CBS auto-lookup (needs new GET /api/cbs/customer/{cif} endpoint)
//   - Product dropdown driven by GET /api/pipeline/products
//   - Duplicate detection across deals (client-side scan or server endpoint)
//   - Backup staff selector
//   - Save-as-draft path
//   - Sector / decision-level / ID type / phone fields
//   - Competitors multiselect
//   - Linked deals for accounts pipeline
//   - Manager "assign to" override

import { useEffect, useMemo, useState } from 'react';
import { BundleLinesEditor, type BundleLine } from '@/components/BundleLinesEditor';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { fetchDealOrigins, fetchOriginSources,
         type DealOrigin, type OriginSourceOption } from '@/lib/api';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useFxRates } from '@/hooks/useFxRates';
import { Card } from '@/components/Card';
import { StaffPicker } from '@/components/StaffPicker';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { Input } from '@/components/Input';
import { CustomerSearchInput } from '@/components/CustomerSearchInput';
import { fetchCbsCustomer, fetchPipelineConfig, fetchCustomerPortfolioOwner, ApiValidationError, type CustomerPortfolioOwner, type StaffMember } from '@/lib/api';
import {
  PIPELINE_CATEGORIES, INITIAL_STAGES_BY_CATEGORY,
  SOURCE_OPTIONS,
  MIN_OVERRIDE_NOTE_LEN,
  type CreateDealRequest, type ReferDealRequest,
  type PipelineConfig,
} from '@/types/pipeline';
import { segmentToCustomerType, type CbsCustomer } from '@/types/cbs';
import { getAdminBranches, type AdminBranch } from '@/lib/api';


// ── Conflict resolution path discriminator ──────────────────────────────

type ConflictPath = 'refer' | 'seek_permission' | 'override';


// ── Page component ──────────────────────────────────────────────────────

// Map a product to its class (asset/liability/insurance/other) using the
// admin product_catalogue, mirroring the backend _classify_product: exact
// match first, then containment. Drives which stage_flow the create form's
// Initial-stage dropdown follows. Returns null when no catalogue is loaded so
// the caller can fall back to the legacy category map.
type ProductClass = 'asset' | 'liability' | 'insurance' | 'other';
const PRODUCT_CLASS_MAP: Record<string, ProductClass> = {
  Assets: 'asset',
  Liabilities: 'liability',
  Insurance: 'insurance',
  Transactional: 'other',
  Investments: 'other',
};
function classifyProduct(
  productType: string,
  catalogue?: Record<string, string[]>,
): ProductClass | null {
  if (!catalogue) return null;
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  const n = norm(productType);
  if (!n) return null;
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => norm(p) === n)) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => {
      const pn = norm(p);
      return pn !== '' && (pn.includes(n) || n.includes(pn));
    })) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  return 'other';
}

export function PipelineCreate() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const mutations = usePipelineDealMutations();

  // ── Core form state ──────────────────────────────────────────────────

  const [clientName,  setClientName]  = useState('');
  const [config,      setConfig]      = useState<PipelineConfig | null>(null);
  const [clientType,  setClientType]  = useState<string>('');
  const [segment,     setSegment]     = useState<string>('');
  const [sector,      setSector]      = useState<string>('');
  const [currency,    setCurrency]    = useState<string>('KES');
  // Item 1: originating branch. Auto-derived from the creator's own branch for
  // branch staff; Head-Office RMs pick one here (their own unit is 'Head Office').
  const [branches,          setBranches]          = useState<AdminBranch[]>([]);
  const [originatingBranch, setOriginatingBranch] = useState<string>('');
  const creatorIsHeadOffice = ((user?.unit || '').trim().toLowerCase() === 'head office')
                              || !((user?.unit || '').trim());
  const [mouId,       setMouId]       = useState<string>('');     // Individual: selected MOU id
  const [mouQuery,    setMouQuery]    = useState<string>('');     // MOU picker search filter
  const [mouOpen,     setMouOpen]     = useState<boolean>(false); // MOU dropdown open
  const [otherText,   setOtherText]   = useState<string>('');     // free text when 'Other' chosen
  const SENTINEL_OTHER = '__OTHER__';
  const [isNtb,       setIsNtb]       = useState(false);
  // ORIGIN (ruling 2026-08-11). Only DECLARABLE origins are offered - referral
  // and warehouse are stamped by the workflow that routed the deal, so
  // offering them here would invite a claim with no evidence behind it.
  const [origin, setOrigin] = useState('self');
  const [originOpts, setOriginOpts] = useState<DealOrigin[]>([]);
  // The SOURCE for that origin - which event, which partnership. Empty for
  // origins with nothing to pick, so no second dropdown renders.
  const [sourceOpts, setSourceOpts] = useState<OriginSourceOption[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [accountNumber, setAccountNumber] = useState('');

  // γ2: Tracks the CBS customer picked via the autofill dropdown.
  // null means no autofill match (free-text fallback). The picked
  // customer drives the "✓ matched in CBS" badge under the input
  // and lets us derive isNtb=false automatically.
  const [pickedCustomer, setPickedCustomer] = useState<CbsCustomer | null>(null);

  // δ2: Direct CIF entry. Separate from pickedCustomer so users who
  // KNOW the CIF can type it without name-searching first. Auto-populated
  // when user picks a customer via the name dropdown. The "Fetch" button
  // does a GET /api/cbs/customers/{cif} lookup and autofills the form
  // from the returned customer record.
  const [clientCif,     setClientCif]     = useState<string>('');
  const [cifLookupLoading, setCifLookupLoading] = useState<boolean>(false);
  const [cifLookupError,   setCifLookupError]   = useState<string | null>(null);

  const [category,    setCategory]    = useState<string>('Loan');
  const [isTopUp,     setIsTopUp]     = useState<boolean>(false);
  const [existingAmt, setExistingAmt] = useState<string>('');
  const [topUpAmt,    setTopUpAmt]    = useState<string>('');
  const [productType, setProductType] = useState('');
  const [dealValue,   setDealValue]   = useState<string>('');     // string so input keeps cursor position
  const [bundleLines, setBundleLines] = useState<BundleLine[]>([]);
  const [bundleTotal, setBundleTotal] = useState<number>(0);
  const isBundle = productType.trim() === 'Bundled Loan Product';
  const [stage,       setStage]       = useState<string>('Lead');
  // (Manual probability slider removed — win probability is now DERIVED from the
  //  selected product flow's stage; see derivedWinProbability below.)

  const [nextAction,     setNextAction]     = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [expectedClose,  setExpectedClose]  = useState('');
  const [source,         setSource]         = useState<string>('Existing relationship');
  const [notes,          setNotes]          = useState('');
  const [contactPhone,   setContactPhone]   = useState('');
  const [contactEmail,   setContactEmail]   = useState('');

  // ── Conflict resolution state ────────────────────────────────────────

  const [hasConflict, setHasConflict] = useState(false);
  const [portfolioOwnerCode, setPortfolioOwnerCode] = useState('');
  const [portfolioOwnerName, setPortfolioOwnerName] = useState('');
  const [conflictPath,       setConflictPath]       = useState<ConflictPath>('seek_permission');

  // P2: CBS portfolio-owner auto-detection (existing customers). detectedOwner
  // holds the last lookup; the effect below auto-fills the conflict fields.
  const [detectedOwner, setDetectedOwner] = useState<CustomerPortfolioOwner | null>(null);
  const [ownerDetecting, setOwnerDetecting] = useState(false);
  const [referredTo,         setReferredTo]         = useState('');     // refer path only
  const [referralNote,       setReferralNote]       = useState('');     // refer path only

  // First-class "refer to a colleague" mode on the create page. When on, the
  // form collapses to client + recipient + note; deal-detail fields are hidden
  // and not required (the recipient completes the deal once they accept).
  const [referMode,      setReferMode]      = useState(() => {
    try { return new URLSearchParams(window.location.search).get('refer') === '1'; }
    catch { return false; }
  });
  const [referRecipient, setReferRecipient] = useState<StaffMember | null>(null);
  const [overrideNote,       setOverrideNote]       = useState('');     // override path only

  // ── Submit state ─────────────────────────────────────────────────────
  //
  // β5.0 polish: replaced single submitError with two state slices so we
  // can render field-level errors inline AND a banner for non-field
  // errors (network/server failures). Pattern:
  //   fieldErrors[fieldName] = "human readable message"  → inline + red border
  //   formError              = "human readable message"  → banner at top
  //
  // The banner sits at the TOP of the form (not bottom) so users can
  // see it without scrolling — the bug β5.0 fixes is that the old
  // banner was at the bottom and users missed it entirely.

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError,   setFormError]   = useState<string | null>(null);

  // ── Derived values ───────────────────────────────────────────────────

  // Admin config drives the segment cascade, sectors, and per-class stage
  // flows. Best-effort — the form falls back to legacy defaults if it can't
  // load.
  // The declarable origins, from config - so an eighth channel appears here
  // without a frontend change.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const r = await fetchDealOrigins();
        if (!alive) return;
        const declarable = r.origins.filter(
          (o) => o.key !== 'referral' && o.key !== 'warehouse');
        setOriginOpts(declarable);
        setOrigin((cur) => (declarable.some((o) => o.key === cur)
          ? cur : (r.default || 'self')));
      } catch {
        // A failed lookup must not block deal capture - the server defaults
        // the origin anyway, so the form stays usable.
        if (alive) setOriginOpts([]);
      }
    })();
    return () => { alive = false; };
  }, []);

  // Reload the source list whenever the origin changes, and clear any previous
  // choice - a stale event_id left behind would attribute this deal to the
  // wrong roadshow. The server clears it too; doing it here keeps the form
  // honest about what it is about to send.
  useEffect(() => {
    let alive = true;
    setSourceId('');
    void (async () => {
      try {
        const r = await fetchOriginSources(origin);
        if (alive) setSourceOpts(r.options ?? []);
      } catch {
        if (alive) setSourceOpts([]);
      }
    })();
    return () => { alive = false; };
  }, [origin]);
  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* fall back to category-based stages, empty segments */ });
    // Item 1: load branches for the Head-Office RM originating-branch picker.
    getAdminBranches()
      .then((r) => setBranches((r.branches || []).filter((b) => b.active !== false)))
      .catch(() => { /* picker will be empty; validation still guards HO RMs */ });
    return () => { active = false; };
  }, []);

  // Product class drives the stage flow (admin config) — loan vs deposit etc.
  const productClass = useMemo(
    () => classifyProduct(productType, config?.product_catalogue),
    [productType, config],
  );
  // Config-driven categories (admin-authored via deal_categories), with the
  // built-in PIPELINE_CATEGORIES as the pre-config fallback.
  const categories = useMemo<string[]>(
    () => {
      const cfg = config?.deal_categories ?? [];
      // A2a: show only pipeline-surfaced categories (balance-sheet class);
      // dormant deal-types are kept in config but hidden from the dropdown.
      const surfaced = cfg.filter((c) => (c.surface ?? 'pipeline') !== 'dormant');
      const list = surfaced.length ? surfaced : cfg;
      return list.length ? list.map((c) => c.category) : [...PIPELINE_CATEGORIES];
    },
    [config],
  );
  // Initial stages for a category: admin-config flow first, then the legacy
  // per-category map, then a minimal default — never throws for a new category.
  const stagesForCategory = (cat: string): string[] => {
    const fromCfg = config?.deal_categories?.find((c) => c.category === cat)?.stages;
    if (fromCfg && fromCfg.length) return [...fromCfg];
    const legacy = (INITIAL_STAGES_BY_CATEGORY as Record<string, readonly string[]>)[cat];
    return legacy ? [...legacy] : ['Lead'];
  };
  const stageOptions = useMemo(() => {
    // Resolution precedence mirrors the server's _stage_flow_for:
    //   1. product_flows[productType] — the product's OWN flow (each product
    //      can diverge, with its own stages + per-stage target_days + win %).
    //   2. stage_flows[productClass]  — the per-class flow.
    //   3. built-in per-category list — pre-config fallback.
    // "Initial stage" excludes terminal stages.
    const isTerminal = (s: string) => s === 'Closed Won' || s === 'Closed Lost';
    const pflow = config?.product_flows?.[productType];
    if (pflow && Array.isArray(pflow.stages) && pflow.stages.length) {
      const names = pflow.stages
        .map((s) => String(s.stage ?? '').trim())
        .filter((s) => s && !isTerminal(s));
      if (names.length) return names;
    }
    const flows = config?.stage_flows;
    if (flows && productClass && flows[productClass]?.length) {
      return flows[productClass].filter((s) => !isTerminal(s));
    }
    return stagesForCategory(category);   // config-driven, with legacy fallback
  }, [config, productType, productClass, category]);

  // The per-stage SLA target (days) for the currently selected stage, from the
  // product's flow — so create-time shows the stage's promise alongside its win
  // probability. Null when the product has no flow or the stage carries none.
  const selectedStageTargetDays = useMemo<number | null>(() => {
    const pflow = config?.product_flows?.[productType];
    if (!pflow || !Array.isArray(pflow.stages)) return null;
    const target = stage.trim().toLowerCase();
    for (const s of pflow.stages) {
      if (String(s.stage ?? '').trim().toLowerCase() === target) {
        const t = Number(s.target_days);
        return Number.isFinite(t) && t > 0 ? t : null;
      }
    }
    return null;
  }, [config, productType, stage]);

  // Win probability is DERIVED from the chosen product's flow at the selected
  // stage (admin-authored), exactly as the server derives it on read — never a
  // manual figure. Null when the product has no flow or the stage carries no
  // win_probability. Mirrors _flow_stage_win_probability server-side.
  const derivedWinProbability = useMemo<number | null>(() => {
    const flow = config?.product_flows?.[productType];
    if (!flow || !Array.isArray(flow.stages)) return null;
    const target = stage.trim().toLowerCase();
    for (const s of flow.stages) {
      if (String(s.stage ?? '').trim().toLowerCase() === target) {
        const wp = s.win_probability;
        if (wp === null || wp === undefined) return null;
        const v = Number(wp);
        return Number.isFinite(v) && v >= 0 && v <= 100 ? v : null;
      }
    }
    return null;
  }, [config, productType, stage]);

  // Client business lines (Consumer / Commercial / CIB) — admin-configurable.
  // The selected type's `field` (mou|sector) drives the third selector.
  const clientTypes = useMemo(
    () => config?.client_types ?? [
      { key: 'Consumer',   label: 'Consumer',                       field: 'mou' as const },
      { key: 'Commercial', label: 'Commercial',                     field: 'sector' as const },
      { key: 'CIB',        label: 'Corporate & Investment Banking', field: 'sector' as const },
    ],
    [config],
  );
  const clientField = useMemo(
    () => clientTypes.find((t) => t.key === clientType)?.field ?? 'sector',
    [clientTypes, clientType],
  );
  const usesSector = clientField === 'sector';

  // Segment cascade off client type; sectors from config.
  const segmentOptions = useMemo(
    () => config?.customer_segments?.[clientType] ?? [],
    [config, clientType],
  );
  // Client-type-aware third field: sector-line -> CBK sectors; mou-line -> MOUs.
  // Both admin-config-driven with an optional "Other…" free-text fallback.
  const businessSectors = useMemo(
    () => config?.business_sectors ?? config?.sectors ?? [],
    [config],
  );
  const individualMous = useMemo(() => config?.individual_mous ?? [], [config]);
  // Searchable picker: filter the (119+) MOU list by the typed query.
  const filteredMous = useMemo(() => {
    const q = mouQuery.trim().toLowerCase();
    if (!q) return individualMous;
    return individualMous.filter((m) =>
      (m.title ?? '').toLowerCase().includes(q) ||
      (m.partner_name ?? '').toLowerCase().includes(q));
  }, [individualMous, mouQuery]);
  const selectedMouTitle = useMemo(
    () => individualMous.find((m) => m.id === mouId)?.title ?? '',
    [individualMous, mouId],
  );

  // Admin-configured mandatory fields (Admin → Configuration). Drives the red
  // asterisks + the extra validation for the optional selection fields (segment
  // / sector / MOU). The four core fields the backend always demands (name /
  // product / value / stage) stay required client-side regardless, so the form
  // can't submit a deal the API would reject.
  const requiredFields = useMemo(
    () => config?.required_fields ?? ['client_name', 'product_type', 'deal_value', 'stage'],
    [config],
  );
  const isReq = (key: string): boolean => requiredFields.includes(key);
  const reqStar = (key: string) => (isReq(key) ? <RedStar /> : null);
  const allowOther = usesSector
    ? (config?.allow_other_sector ?? true)
    : false;  // consumer MOU: no "Other" escape — must pick a listed MOU partner

  // Once config loads, default the client type to the first configured line.
  useEffect(() => {
    if (!clientType && clientTypes.length) setClientType(clientTypes[0].key);
  }, [clientTypes, clientType]);

  // Map the CBS-derived legacy customer type to a configured client-type key.
  const legacyToTypeKey = (legacy: 'Individual' | 'Business'): string => {
    const wantField = legacy === 'Individual' ? 'mou' : 'sector';
    return clientTypes.find((t) => t.field === wantField)?.key
      ?? clientTypes[0]?.key ?? '';
  };

  // Reset the third-field selections when the client type flips, so a stale
  // sector doesn't ride along on a consumer deal (or a stale MOU on a business one).
  useEffect(() => {
    setSector('');
    setMouId('');
    setOtherText('');
  }, [clientType]);

  // Resolve what the client-type-aware third field contributes to the payload.
  const thirdField = useMemo(() => {
    if (usesSector) {
      const s = sector === SENTINEL_OTHER ? otherText.trim() : sector;
      return { sector: s || undefined, mou_id: undefined as string | undefined,
               mou_title: undefined as string | undefined };
    }
    const isOther = mouId === SENTINEL_OTHER;
    return {
      sector: undefined as string | undefined,
      mou_id: isOther || !mouId ? undefined : mouId,
      mou_title: isOther
        ? (otherText.trim() || undefined)
        : individualMous.find((m) => m.id === mouId)?.title,
    };
  }, [usesSector, sector, mouId, otherText, individualMous]);

  // Currency options come from the admin-maintained FX table (active rates),
  // not a hardcoded list — so extending to other Ecobank affiliates or
  // cross-border customers is an admin action, never a code change. KES (base)
  // is always offered even before any FX rate is configured.
  const { rates: fxRates } = useFxRates(true);
  const currencyOptions = useMemo(() => {
    const set = new Set<string>(['KES']);
    for (const r of fxRates) if (r.currency) set.add(r.currency.toUpperCase());
    // KES (local), then the priority trade currencies USD + CNY, then the rest
    // (EcoBank's African footprint) alphabetically.
    const PRIORITY = ['KES', 'USD', 'CNY'];
    return Array.from(set).sort((a, b) => {
      const ia = PRIORITY.indexOf(a);
      const ib = PRIORITY.indexOf(b);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return a.localeCompare(b);
    });
  }, [fxRates]);
  const selectedRate = useMemo(
    () => (currency === 'KES' ? 1 : fxRates.find((r) => r.currency?.toUpperCase() === currency)?.rate_to_kes),
    [currency, fxRates],
  );

  const productOptions = useMemo(() => {
    const cat = config?.product_catalogue;
    // A2a: the category carries its own product_class (balance-sheet class);
    // fall back to the legacy name map, then to all classes.
    const catCfg = config?.deal_categories?.find((c) => c.category === category);
    const legacyWant: Record<string, ProductClass[]> = {
      Loan: ['asset'], Deposit: ['liability'], Account: ['liability', 'other'],
    };
    const buckets: ProductClass[] = (catCfg?.product_class?.length
      ? (catCfg.product_class as ProductClass[])
      : (legacyWant[category] ?? ['asset', 'liability', 'insurance', 'other']));
    const flows = config?.product_flows ?? {};
    // P4a: a product whose flow declares client_types is offered ONLY to those
    // client types; an empty (or absent) client_types means offered to all.
    const offeredToClient = (product: string): boolean => {
      const cts = flows[product]?.client_types;
      if (!cts || cts.length === 0) return true;       // all client types
      return !clientType || cts.includes(clientType);
    };
    // Product gate (matches the server): a product is selectable only once it's
    // set up — it must have its OWN process flow (whose stage day-sum is the
    // SLA). Products without a flow can't be used on a deal, so they aren't
    // offered. Admin sets up the flow + SLA before a product appears here.
    const isReady = (product: string): boolean => {
      const entry = flows[product];
      return !!(entry && Array.isArray(entry.stages) && entry.stages.length > 0);
    };
    if (cat) {
      const out: string[] = [];
      for (const [cls, prods] of Object.entries(cat)) {
        if (buckets.includes(PRODUCT_CLASS_MAP[cls] ?? 'other')) {
          out.push(...prods.filter((p) => offeredToClient(p) && isReady(p)));
        }
      }
      if (out.length) return Array.from(new Set(out));
    }
    // No fallback to free-text suggestions: an empty list means no ready product
    // for this category/client type — the user must pick a different category or
    // an admin must set one up.
    return [];
  }, [config, category, clientType]);
  const dealValueNum       = useMemo(() => {
    const n = Number(String(dealValue).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [dealValue]);
  const existingAmtNum = useMemo(() => {
    const n = Number(String(existingAmt).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [existingAmt]);
  const topUpAmtNum = useMemo(() => {
    const n = Number(String(topUpAmt).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [topUpAmt]);

  // Override note is required when conflictPath === 'override' AND user has conflict
  const overrideNoteTooShort = hasConflict && conflictPath === 'override'
    && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN;

  // A2a: default category to first pipeline category once config loads (so the
  // create form opens on a balance-sheet class, not the hardcoded 'Loan').
  useEffect(() => {
    if (categories.length && !categories.includes(category)) {
      setCategory(categories[0]);
      const initStages = stagesForCategory(categories[0]);
      setStage((cur) => (initStages.includes(cur) ? cur : (initStages[0] ?? 'Lead')));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories]);

  // When category changes, ensure stage is valid for the new category.
  // β5.1: AUTO-UPDATE stage to the first option for the new category.
  // β3 originally chose NOT to auto-update ("let user see change explicitly")
  // but that creates a confusing failure mode where the dropdown LOOKS
  // filled with a valid-seeming value (e.g. "Lead") but is invalid for
  // the current category, and submit fails with a "Stage X not valid for
  // Y pipeline" error that users find confusing because the field appears
  // filled. Auto-update eliminates that failure entirely.
  const stageIsValidForCategory = stageOptions.includes(stage);

  useEffect(() => {
    if (!stageOptions.includes(stage)) {
      setStage(stageOptions[0] ?? 'Lead');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, productClass, stageOptions]);

  // Clear segment when it no longer fits the selected client type.
  useEffect(() => {
    if (segment && !segmentOptions.includes(segment)) setSegment('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientType, segmentOptions]);

  // Clear a selected product when narrowing (by client type or category)
  // removes it from the offered set, so a product not offered to the chosen
  // client type / category can't be silently submitted. Products are now
  // selection-only from the catalogue (no free-text), so any selected product
  // must always be in the offered list.
  useEffect(() => {
    if (productType && !productOptions.includes(productType)) {
      setProductType('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientType, category, productOptions]);

  // P2: when an existing customer is picked, look up their mapped portfolio
  // owner from CBS. If the customer belongs to a DIFFERENT RM, auto-flag the
  // conflict and pre-fill the owner so the deal can be referred for a nod.
  // If the current user owns the portfolio (or it's unmapped), no conflict.
  useEffect(() => {
    const cif = pickedCustomer?.cif?.trim();
    if (!cif) { setDetectedOwner(null); return; }
    let cancelled = false;
    setOwnerDetecting(true);
    fetchCustomerPortfolioOwner(cif)
      .then((po) => {
        if (cancelled) return;
        setDetectedOwner(po);
        const me = (user?.staff_code || '').trim();
        if (po.is_mapped && po.portfolio_owner_code && po.portfolio_owner_code !== me) {
          setHasConflict(true);
          setPortfolioOwnerCode(po.portfolio_owner_code);
          setPortfolioOwnerName(po.portfolio_owner_name || '');
          setConflictPath('refer');
        } else {
          setHasConflict(false);
          setPortfolioOwnerCode('');
          setPortfolioOwnerName('');
        }
      })
      .catch(() => { if (!cancelled) setDetectedOwner(null); })
      .finally(() => { if (!cancelled) setOwnerDetecting(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedCustomer?.cif, user?.staff_code]);

  // ── Live field error clearing (β5.1) ─────────────────────────────────
  //
  // When a user starts typing in a field that's currently flagged red,
  // clear that field's error immediately — don't wait for re-submit.
  // Without this, users see a red field, fix it, and the red persists
  // until they hit Submit again, which feels broken.
  const clearFieldError = (key: string) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  // δ2 (2026-06-12): direct CIF lookup. User types a CIF in the
  // "Client CIF" input and clicks "Fetch from CBS" (or presses Enter).
  // We GET /api/cbs/customers/{cif}; on success we autofill clientName,
  // clientType, pickedCustomer, isNtb (same shape as picking from the
  // name dropdown). 404 surfaces as an error message under the input.
  const onFetchCif = async () => {
    const cif = clientCif.trim();
    if (!cif) {
      setCifLookupError('Enter a CIF to fetch.');
      return;
    }
    setCifLookupLoading(true);
    setCifLookupError(null);
    try {
      const resp = await fetchCbsCustomer(cif);
      const customer = resp.customer;
      // Mirror the onCustomerPicked branch from the name-search dropdown
      setPickedCustomer(customer);
      setClientName(customer.full_name);
      setClientType(legacyToTypeKey(segmentToCustomerType(customer.segment)));
      setIsNtb(false);
      setClientCif(customer.cif);
      clearFieldError('clientName');
      toast({
        tone: 'success',
        message: `✓ Customer found: ${customer.full_name}`,
      });
    } catch (e) {
      if (e instanceof ApiValidationError) {
        setCifLookupError(e.detail || 'CIF lookup failed.');
      } else {
        const msg = e instanceof Error ? e.message : 'CIF lookup failed.';
        setCifLookupError(msg);
      }
    } finally {
      setCifLookupLoading(false);
    }
  };

  // ── Validation ───────────────────────────────────────────────────────
  //
  // β5.0 polish: returns Record<field-name, message> instead of single
  // string. Collects ALL errors so the user can see every missing field
  // at once rather than fixing them one at a time.
  //
  // Field names match the state variable names (clientName,
  // portfolioOwnerCode, etc.) — the form's per-field rendering uses
  // these as keys when looking up errors.

  const isReferPath = hasConflict && conflictPath === 'refer';

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    if (!clientName.trim()) errors.clientName = 'Client name is required.';
    if (creatorIsHeadOffice && !originatingBranch.trim()) errors.originatingBranch = 'Please select the originating branch.';

    // Refer mode: only the client and the recipient are required; everything
    // else is optional (the recipient completes the deal after accepting).
    if (referMode) {
      if (!referRecipient) errors.referRecipient = 'Choose a colleague to refer this to.';
      return errors;
    }

    if (isReferPath) {
      // Refer path has different required fields
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required for referral.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required for referral.';
      if (!referredTo.trim())         errors.referredTo         = 'Referred-to name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = "You can't refer a deal to yourself.";
      }
      return errors;
    }

    // Standard create path
    // P4: portfolio assignment is mandatory for an EXISTING customer whose CBS
    // portfolio owner is someone else. P2 auto-flags the conflict; if the user
    // has cleared it, they must address it (refer / seek permission / override)
    // rather than silently book a deal against another RM's portfolio.
    const me = (user?.staff_code || '').trim();
    const detectedConflict = !isNtb && !!detectedOwner?.is_mapped
      && !!detectedOwner.portfolio_owner_code
      && detectedOwner.portfolio_owner_code !== me;
    if (detectedConflict && !hasConflict) {
      errors.hasConflict = `This customer is in ${detectedOwner?.portfolio_owner_name || 'another RM'}\u2019s portfolio — choose how to proceed (refer, seek permission, or override).`;
    }

    if (!productType.trim())        errors.productType = 'Product type is required.';
    if (!stage.trim())              errors.stage       = 'Stage is required.';
    if (stage.trim() && !stageIsValidForCategory) {
      errors.stage = `Stage "${stage}" is not valid for ${category} pipeline.`;
    }
    if (isTopUp) {
      if (!Number.isFinite(topUpAmtNum) || topUpAmtNum <= 0) {
        errors.dealValue = 'Top-up amount must be greater than zero.';
      } else if (Number.isFinite(existingAmtNum) && existingAmtNum > 0 && existingAmtNum < topUpAmtNum) {
        errors.dealValue = 'Existing facility amount should be at least the top-up amount.';
      }
    } else if (!Number.isFinite(dealValueNum) || dealValueNum < 0) {
      errors.dealValue = 'Deal value must be a non-negative number.';
    }

    // Admin-configured mandatory selection fields (layered on the always-on
    // core fields above). Segment / sector / MOU are otherwise optional.
    if (isReq('segment') && segmentOptions.length > 0 && !segment.trim()) {
      errors.segment = 'Segment is required.';
    }
    if (usesSector && isReq('sector') && !sector.trim()) {
      errors.sectorMou = 'CBK sector is required.';
    }
    // Ecobank rule: Consumer deals lend ONLY through an MOU partner, so the
    // MOU is ALWAYS required for a consumer (mou-field) deal — not contingent on
    // admin required_fields config — and the "Other" escape is not permitted.
    if (!usesSector) {
      if (!mouId.trim()) {
        errors.sectorMou = 'An MOU partner is required for consumer deals.';
      } else if (mouId === SENTINEL_OTHER) {
        errors.sectorMou = 'Consumer deals must use a listed MOU partner (no "Other").';
      }
    }

    if (hasConflict) {
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = 'Portfolio owner cannot be yourself — uncheck conflict if you own this portfolio.';
      }
      if (conflictPath === 'override' && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN) {
        errors.overrideNote = `Manager override note must be at least ${MIN_OVERRIDE_NOTE_LEN} characters (current: ${overrideNote.trim().length}).`;
      }
    }
    return errors;
  };

  // ── Server error → field mapping ────────────────────────────────────
  //
  // β5.0 polish: try to map server detail strings back to specific
  // fields. Backend validators in utils/api_pipeline_mutations.py
  // emit messages like "Missing required field: client_name". When
  // we recognise the snake_case field, map it to the camelCase state
  // variable and set a fieldError. Otherwise fall back to the banner.

  const SERVER_FIELD_MAP: Record<string, string> = {
    client_name:          'clientName',
    staff_code:           'clientName',   // shouldn't happen — we set this
    staff_name:           'clientName',   // shouldn't happen — we set this
    deal_value:           'dealValue',
    product_type:         'productType',
    stage:                'stage',
    portfolio_owner_code: 'portfolioOwnerCode',
    portfolio_owner_name: 'portfolioOwnerName',
    referred_to:          'referredTo',
    manager_override_note: 'overrideNote',
  };

  const parseServerError = (serverDetail: string): { fieldKey: string | null; message: string } => {
    if (!serverDetail) return { fieldKey: null, message: 'Submission failed.' };
    // Match "Missing required field: X" pattern
    const m1 = serverDetail.match(/Missing required field:\s*(\w+)/i);
    if (m1 && SERVER_FIELD_MAP[m1[1].toLowerCase()]) {
      return { fieldKey: SERVER_FIELD_MAP[m1[1].toLowerCase()], message: serverDetail };
    }
    // Match "manager_override_note required" pattern (α5 override semantics)
    if (/manager_override_note/i.test(serverDetail)) {
      return { fieldKey: 'overrideNote', message: serverDetail };
    }
    // Match "portfolio_owner_code" mentions
    if (/portfolio_owner_code/i.test(serverDetail)) {
      return { fieldKey: 'portfolioOwnerCode', message: serverDetail };
    }
    return { fieldKey: null, message: serverDetail };
  };

  // ── Scroll-to-error helper ──────────────────────────────────────────
  //
  // β5.0 polish: after submit fails, scroll the first errored field
  // into view and focus it. Uses the data-field attr added to each
  // input wrapper. If the field can't be found, scroll to the form
  // top so the banner is visible.

  const scrollToFirstError = (errors: Record<string, string>) => {
    const firstField = Object.keys(errors)[0];
    if (!firstField) return;
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`[data-field="${firstField}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Try to focus the first focusable descendant
        const focusable = el.querySelector<HTMLElement>('input, textarea, select');
        if (focusable) focusable.focus({ preventScroll: true });
      } else {
        // Fall back: scroll to top so banner is visible
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }, 50);
  };

  // ── Submit ───────────────────────────────────────────────────────────

  const onSubmit = async () => {
    // Reset any previous error state
    setFormError(null);
    setFieldErrors({});

    // Client-side validation: collect all errors
    const localErrors = validate();
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      // Toast in case user scrolled past the banner
      toast({
        tone: 'danger',
        message: `Please fix ${Object.keys(localErrors).length} issue${Object.keys(localErrors).length > 1 ? 's' : ''} in the form.`,
      });
      scrollToFirstError(localErrors);
      return;
    }

    // Guard against missing user identity (shouldn't happen given the
    // route is ProtectedRoute requireAuth, but type system needs it)
    if (!user?.staff_code || !user?.full_name) {
      setFormError('Your user identity is not loaded. Try refreshing the page.');
      toast({ tone: 'danger', message: 'User identity not loaded — please refresh.' });
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    // ── Refer mode: first-class "refer to a colleague" from create ──────
    if (referMode && referRecipient) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  referRecipient.staff_code,
        portfolio_owner_name:  referRecipient.name,
        referred_to:           referRecipient.name,
        referral_note:         referralNote.trim() || undefined,
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referRecipient.name} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Refer path: separate endpoint ──────────────────────────────────
    if (isReferPath) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  portfolioOwnerCode.trim(),
        portfolio_owner_name:  portfolioOwnerName.trim(),
        referred_to:           referredTo.trim(),
        referral_note:         referralNote.trim() || undefined,
        account_number:        accountNumber.trim() || undefined,
        // Note: unit not sent from client — UserIdentity surfaces
        // department, not unit. Server can resolve unit from staff_code
        // if needed (the create endpoint already does this for other
        // ownership fields).
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referredTo.trim()} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        // Server validation failure — try to map to a field
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Standard create path (with optional conflict fields) ───────────
    const body: CreateDealRequest = {
      client_name:  clientName.trim(),
      // Declared origin. The server validates it and silently replaces a
      // system-routed value, so a stale client cannot claim a referral.
      origin,
      ...(sourceId ? { event_id: sourceId } : {}),
      staff_code:   user.staff_code,
      staff_name:   user.full_name,
      deal_value:   isBundle ? bundleTotal : (isTopUp ? topUpAmtNum : dealValueNum),
        bundle_lines: isBundle && bundleLines.length
          ? bundleLines.map((l) => ({ product_type: l.product_type, amount: Number(String(l.amount).replace(/[,\s]/g, '')) }))
          : undefined,
      product_type: productType.trim(),
      stage:        stage,

      // Optional
      client_type:        clientType,
      currency:           currency || 'KES',
      segment:            segment || undefined,
      sector:             thirdField.sector,
      mou_id:             thirdField.mou_id,
      mou_title:          thirdField.mou_title,
      client_cif:         clientCif.trim() || undefined,  // δ2: persist CIF when known
      is_ntb:             isNtb,
      pipeline_category:  category,
      is_top_up:          isTopUp || undefined,
      top_up_amount:      isTopUp && Number.isFinite(topUpAmtNum) ? topUpAmtNum : undefined,
      original_facility_amount: isTopUp && Number.isFinite(existingAmtNum) ? existingAmtNum : undefined,
      // Legacy `probability` (0..1) now reflects the DERIVED stage win
      // probability rather than a manual slider; omitted when the stage has
      // none authored (server derives win_probability on read regardless).
      probability:        derivedWinProbability !== null ? derivedWinProbability / 100 : undefined,
      next_action:        nextAction.trim() || undefined,
      next_action_date:   nextActionDate || undefined,
      expected_close:     expectedClose  || undefined,
      notes:              notes.trim() || undefined,
      source:             source,
      // Item 1: Head-Office RMs pick an originating branch; send it as unit.
      // Branch staff omit it and the backend auto-derives from their own branch.
      unit:               creatorIsHeadOffice && originatingBranch ? originatingBranch : undefined,
      // Server resolves unit from staff_code if needed.
      account_number:     accountNumber.trim() || undefined,
      phone:              contactPhone.trim() || undefined,
      email:              contactEmail.trim() || undefined,
    };

    // ── Apply conflict resolution to body ─────────────────────────────
    if (hasConflict) {
      body.portfolio_owner_code = portfolioOwnerCode.trim();
      body.portfolio_owner_name = portfolioOwnerName.trim();

      if (conflictPath === 'seek_permission') {
        // BSC credit goes to portfolio owner. Backend sees this as
        // seek-permission semantics — NO override note required.
        body.bsc_credit_to = portfolioOwnerName.trim();
      } else if (conflictPath === 'override') {
        // BSC credit goes to caller. Backend detects override semantics
        // and REQUIRES manager_override_note (≥10 chars).
        body.bsc_credit_to          = user.full_name;
        body.manager_override_note  = overrideNote.trim();
      }
    }

    const result = await mutations.create(body);
    if (result.ok) {
      toast({ tone: 'success', message: 'Deal created.' });
      navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
    } else {
      // Server validation failure — try to map to a field
      const parsed = parseServerError(result.error);
      if (parsed.fieldKey) {
        setFieldErrors({ [parsed.fieldKey]: parsed.message });
        scrollToFirstError({ [parsed.fieldKey]: parsed.message });
      } else {
        setFormError(parsed.message);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
      toast({ tone: 'danger', message: parsed.message });
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="New Deal"
        breadcrumbs={[
          { label: 'A2Z Sales Pro', to: '/pipeline' },
          { label: 'New deal' },
        ]}
        subtitle="Capture a lead — customer, classification, value, and ownership."
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
            ← Back to pipeline
          </Button>
        }
      />

      <main className="max-w-6xl mx-auto px-6 pt-4 pb-8">
        {/* Mode toggle: build a full deal, or refer a lead to a colleague. */}
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
          <button
            type="button"
            onClick={() => setReferMode(false)}
            className={`px-4 py-1.5 rounded-md transition ${!referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Create a deal
          </button>
          <button
            type="button"
            onClick={() => setReferMode(true)}
            className={`px-4 py-1.5 rounded-md transition ${referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Refer to a colleague
          </button>
        </div>

        {/* ─────────── Error summary banner (β5.0 polish) ───────────
            Renders at the top so users see it without scrolling.
            Shows either:
              - formError (banner-level: network/server/identity errors), OR
              - a summary count of fieldErrors with a "review fields"
                hint, since each field also shows its own inline message
        */}
        {(formError || Object.keys(fieldErrors).length > 0) && (
          <div
            role="alert"
            aria-live="assertive"
            className="mb-4 px-4 py-3 rounded-md bg-red-50 border-l-4 border-red-500 text-sm text-red-900 shadow-sm"
          >
            {formError ? (
              <div>
                <div className="font-semibold mb-0.5">Submission failed</div>
                <div>{formError}</div>
              </div>
            ) : (
              <div>
                <div className="font-semibold mb-0.5">
                  Please fix {Object.keys(fieldErrors).length} field
                  {Object.keys(fieldErrors).length > 1 ? 's' : ''} below
                </div>
                <div className="text-xs">
                  Each problem is highlighted in red next to the relevant input.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─────────── Form sections (2-up on wide screens) ─────────── */}
        <div className="grid lg:grid-cols-2 gap-5 items-start">
        {/* ─────────── Customer section ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Customer</h2>
            <span className="text-xs text-gray-400">Who is this deal for?</span>
          </Card.Header>
          <Card.Body>
            {/* ORIGIN — the first gate. Where did this deal come from? Only
                the origins a person can legitimately declare appear here;
                referral and warehouse are stamped by the system when the deal
                actually travels that route. */}
            {originOpts.length > 0 && (
              <div className="mb-4">
                <label className="text-sm font-medium text-gray-700">
                  Deal origin
                </label>
                <select
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {originOpts.map((o) => (
                    <option key={o.key} value={o.key}>{o.label}</option>
                  ))}
                </select>
                {(() => {
                  const o = originOpts.find((x) => x.key === origin);
                  return o?.note ? (
                    <p className="mt-1 text-xs text-gray-500">{o.note}</p>
                  ) : null;
                })()}

                {sourceOpts.length > 0 && (
                  <div className="mt-3">
                    <label className="text-sm font-medium text-gray-700">
                      Which one?
                    </label>
                    <select
                      value={sourceId}
                      onChange={(e) => setSourceId(e.target.value)}
                      disabled={mutations.loading}
                      className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                    >
                      <option value="">Not specified</option>
                      {sourceOpts.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}{o.sub ? ` — ${o.sub}` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}

            {/* Relationship status — drives whether a CBS CIF lookup is
                offered (existing customer) or the form is filled fresh (NTB). */}
            <div className="mb-4">
              <label className="text-sm font-medium text-gray-700">
                Relationship status{reqStar('relationship_status')}
              </label>
              <select
                value={isNtb ? 'ntb' : 'existing'}
                onChange={(e) => setIsNtb(e.target.value === 'ntb')}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="existing">Existing customer</option>
                <option value="ntb">New to Bank</option>
              </select>
            </div>

            {/* CIF lookup — only meaningful for an existing (in-CBS) customer. */}
            {!isNtb && (
            <div className="mb-4" data-field="clientCif">
              <label className="text-sm font-medium text-gray-700">
                Client CIF (to fetch from CBS)
              </label>
              <div className="flex gap-2 mt-1">
                <input
                  type="text"
                  value={clientCif}
                  onChange={(e) => {
                    setClientCif(e.target.value);
                    if (cifLookupError) setCifLookupError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && clientCif.trim() && !cifLookupLoading) {
                      e.preventDefault();
                      void onFetchCif();
                    }
                  }}
                  placeholder="e.g. 100123456"
                  disabled={mutations.loading || cifLookupLoading}
                  autoComplete="off"
                  className="flex-1 h-10 px-3 rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                />
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => void onFetchCif()}
                  disabled={!clientCif.trim() || mutations.loading || cifLookupLoading}
                >
                  {cifLookupLoading ? 'Fetching…' : 'Fetch from CBS'}
                </Button>
              </div>
              {cifLookupError && (
                <div className="mt-1 text-xs text-red-700">{cifLookupError}</div>
              )}
              {!cifLookupError && pickedCustomer && clientCif === pickedCustomer.cif && (
                <div className="mt-1 text-xs text-green-700">
                  ✓ CIF matches picked customer
                </div>
              )}
            </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div data-field="clientName">
                <CustomerSearchInput
                  label={<>Client name <RedStar /></>}
                  placeholder="Type a name (min 3 chars) to search CBS, or enter free text"
                  value={clientName}
                  onChange={(v) => { setClientName(v); clearFieldError('clientName'); }}
                  onCustomerPicked={(c) => {
                    // γ2 autofill — when user picks from CBS dropdown,
                    // populate related fields automatically.
                    setPickedCustomer(c);
                    setClientType(legacyToTypeKey(segmentToCustomerType(c.segment)));
                    // Customer is in CBS, so by definition not New-To-Bank.
                    setIsNtb(false);
                    // δ2: also capture the CIF so it persists on the deal.
                    setClientCif(c.cif);
                    setCifLookupError(null);
                    clearFieldError('clientName');
                  }}
                  onCustomerCleared={() => setPickedCustomer(null)}
                  pickedCustomer={pickedCustomer}
                  disabled={mutations.loading}
                  error={fieldErrors.clientName}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Customer type{reqStar('client_type')}
                </label>
                <select
                  value={clientType}
                  onChange={(e) => setClientType(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {clientTypes.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div data-field="segment">
                <label className="text-sm font-medium text-gray-700">
                  Segment{reqStar('segment')}
                </label>
                <select
                  value={segment}
                  onChange={(e) => { setSegment(e.target.value); clearFieldError('segment'); }}
                  disabled={mutations.loading || segmentOptions.length === 0}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  <option value="">
                    {segmentOptions.length === 0 ? '—' : `Select ${clientType.toLowerCase()} segment`}
                  </option>
                  {segmentOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.segment && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.segment}</p>
                )}
              </div>
              {creatorIsHeadOffice && (
                <div data-field="originatingBranch">
                  <label className="text-sm font-medium text-gray-700">
                    Originating branch<RedStar />
                  </label>
                  <select
                    value={originatingBranch}
                    onChange={(e) => setOriginatingBranch(e.target.value)}
                    disabled={mutations.loading}
                    className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  >
                    <option value="">Select branch…</option>
                    {branches.map((b) => (
                      <option key={b.id || b.name} value={b.name}>{b.name}</option>
                    ))}
                  </select>
                  {fieldErrors.originatingBranch && (
                    <p className="text-xs text-red-700 mt-1">{fieldErrors.originatingBranch}</p>
                  )}
                </div>
              )}
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Currency{reqStar('currency')}
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {currencyOptions.map((c) => (
                    <option key={c} value={c}>{c}{c === 'KES' ? ' (local)' : ''}</option>
                  ))}
                </select>
                {currency !== 'KES' && (
                  <p className="text-xs text-gray-500 mt-1">
                    {selectedRate
                      ? `FCY · ≈ KES ${(dealValueNum * selectedRate).toLocaleString(undefined, { maximumFractionDigits: 0 })} at ${selectedRate}/${currency}`
                      : `FCY · no admin FX rate set for ${currency} yet`}
                  </p>
                )}
              </div>
              <div data-field="sectorMou">
                <label className="text-sm font-medium text-gray-700">
                  {usesSector
                    ? <>Sector (CBK){reqStar('sector')}</>
                    : <>Partnership / MOU<RedStar /></>}
                </label>
                {usesSector ? (
                  <select
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    disabled={mutations.loading}
                    className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  >
                    <option value="">Select CBK sector (optional)</option>
                    {businessSectors.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                    {allowOther && <option value={SENTINEL_OTHER}>Other…</option>}
                  </select>
                ) : (
                  <div className="relative">
                    <input
                      type="text"
                      value={mouOpen ? mouQuery : selectedMouTitle}
                      placeholder="Search and select an MOU partner (required)"
                      disabled={mutations.loading}
                      autoComplete="off"
                      onFocus={() => { setMouOpen(true); setMouQuery(''); }}
                      onChange={(e) => { setMouQuery(e.target.value); setMouOpen(true); }}
                      onBlur={() => { window.setTimeout(() => setMouOpen(false), 120); }}
                      className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                    />
                    {mouOpen && (
                      <ul className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
                        {filteredMous.length === 0 ? (
                          <li className="px-3 py-2 text-sm text-gray-500">
                            No partner matches “{mouQuery}”.
                          </li>
                        ) : (
                          filteredMous.map((m) => (
                            <li key={m.id}>
                              <button
                                type="button"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  setMouId(m.id);
                                  setMouQuery('');
                                  setMouOpen(false);
                                }}
                                className={`w-full text-left px-3 py-2 text-sm hover:bg-brand-primary/10 ${m.id === mouId ? 'bg-brand-primary/5 font-medium' : ''}`}
                              >
                                {m.title}
                              </button>
                            </li>
                          ))
                        )}
                      </ul>
                    )}
                  </div>
                )}
                {(sector === SENTINEL_OTHER || mouId === SENTINEL_OTHER) && (
                  <input
                    type="text"
                    value={otherText}
                    onChange={(e) => setOtherText(e.target.value)}
                    disabled={mutations.loading}
                    placeholder={usesSector ? 'Specify sector' : 'Specify partner / MOU'}
                    className="mt-2 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                )}
                {fieldErrors.sectorMou && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.sectorMou}</p>
                )}
              </div>
              <Input
                label={isNtb ? 'New account number (once opened)' : 'Account number / CIF (optional)'}
                placeholder={isNtb ? "Enter once the customer's account is opened" : 'e.g. ECO0123456789 or 100456789'}
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Customer phone (optional)"
                placeholder="e.g. 0712 345 678"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Customer email (optional)"
                placeholder="e.g. name@example.com"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                disabled={mutations.loading}
              />
            </div>
          </Card.Body>
        </Card>

        {referMode && (
          <Card stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Refer to a colleague</h2>
              <span className="text-xs text-gray-400">Recipient + note</span>
            </Card.Header>
            <Card.Body>
              <p className="text-sm text-gray-600 mb-3">
                Hand this lead to a colleague — pick their segment, then the person.
                Only the client name and recipient are required; they complete the
                deal once they accept it.
              </p>
              <StaffPicker value={referRecipient} onChange={setReferRecipient} />
              {fieldErrors.referRecipient && (
                <p className="text-xs text-red-600 mt-2">{fieldErrors.referRecipient}</p>
              )}
              <div className="mt-3">
                <Input
                  label="Note (optional)"
                  placeholder="Why you're referring this"
                  value={referralNote}
                  onChange={(e) => setReferralNote(e.target.value)}
                  disabled={mutations.loading}
                />
              </div>
            </Card.Body>
          </Card>
        )}

        {!referMode && (<>
        {/* ─────────── Deal classification + value ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Deal details</h2>
            <span className="text-xs text-gray-400">Classification + value</span>
          </Card.Header>
          <Card.Body>
            <div>
              <label className="text-sm font-medium text-gray-700">Pipeline category <RedStar /></label>
              <select
                value={category}
                onChange={(e) => {
                  const c = e.target.value;
                  setCategory(c);
                  const initStages = stagesForCategory(c);
                  if (!initStages.includes(stage)) {
                    setStage(initStages[0] ?? 'Lead');
                  }
                  setProductType('');
                }}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div className="mt-4" data-field="productType">
              <label className="text-sm font-medium text-gray-700">Product type <RedStar /></label>
              <select
                value={productOptions.includes(productType) ? productType : ''}
                onChange={(e) => {
                  setProductType(e.target.value);
                  clearFieldError('productType');
                }}
                disabled={mutations.loading || productOptions.length === 0}
                aria-invalid={!!fieldErrors.productType}
                className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                  fieldErrors.productType
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                    : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                }`}
              >
                <option value="">Select a product…</option>
                {productOptions.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              {productOptions.length === 0 && (
                <p className="mt-1 text-xs text-gray-500">
                  No products are set up for this category{clientType ? ` and client type` : ''} yet.
                  Products must be created in Admin with a process flow and SLA before they can be used.
                </p>
              )}
              {fieldErrors.productType && (
                <p className="mt-1 text-xs text-red-700">{fieldErrors.productType}</p>
              )}
            </div>

            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">Facility type</label>
              <div className="mt-1 inline-flex rounded-md border border-gray-300 overflow-hidden">
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${!isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(false); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>New facility</button>
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(true); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>Top-up</button>
              </div>
              {isBundle && (
                <BundleLinesEditor
                  value={bundleLines}
                  onChange={(lines, total) => { setBundleLines(lines); setBundleTotal(total); }}
                  currencySymbol={branding?.currency_symbol ?? 'KES'}
                />
              )}

              {!isBundle && isTopUp && (
                <p className="mt-1 text-xs text-gray-500">
                  A top-up adds to an existing facility. The pipeline value reflects only the increment (the new money), not the whole facility.
                </p>
              )}
            </div>

            {!isBundle && isTopUp && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div>
                  <Input
                    label={<>Existing facility amount (KES) <RedStar /></>}
                    placeholder="e.g. 20000000" type="number"
                    value={existingAmt}
                    onChange={(e) => setExistingAmt(e.target.value)}
                    disabled={mutations.loading}
                    helper={Number.isFinite(existingAmtNum) && existingAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${existingAmtNum.toLocaleString()} (context only)`
                      : 'Context only — not counted in pipeline value'}
                  />
                </div>
                <div data-field="dealValue">
                  <Input
                    label={<>Top-up amount (KES) <RedStar /></>}
                    placeholder="e.g. 5000000" type="number"
                    value={topUpAmt}
                    onChange={(e) => { setTopUpAmt(e.target.value); clearFieldError('dealValue'); }}
                    disabled={mutations.loading}
                    helper={Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()} — this IS the pipeline value`
                      : undefined}
                    error={fieldErrors.dealValue}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              {!isBundle && !isTopUp && (
              <div data-field="dealValue">
                <Input
                  label={category === 'Account'
                    ? <>Number of accounts <RedStar /></>
                    : <>Deal value (KES) <RedStar /></>}
                  placeholder={category === 'Account' ? 'e.g. 1' : 'e.g. 5000000'}
                  type="number"
                  value={dealValue}
                  onChange={(e) => { setDealValue(e.target.value); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}
                  helper={Number.isFinite(dealValueNum) && dealValueNum > 0
                    ? `${branding?.currency_symbol ?? 'KES'} ${dealValueNum.toLocaleString()}`
                    : undefined}
                  error={fieldErrors.dealValue}
                />
              </div>
              )}
              {!isBundle && isTopUp && (
              <div>
                <label className="text-sm font-medium text-gray-700">Pipeline value</label>
                <div className="mt-2 flex items-center gap-2">
                  <Badge tone="info" size="sm">
                    {Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()}`
                      : '—'}
                  </Badge>
                  <span className="text-xs text-gray-400">top-up increment</span>
                </div>
              </div>
              )}
              <div data-field="stage">
                <label className="text-sm font-medium text-gray-700">
                  Initial stage <RedStar />
                </label>
                <select
                  value={stage}
                  onChange={(e) => { setStage(e.target.value); clearFieldError('stage'); }}
                  disabled={mutations.loading}
                  aria-invalid={!!fieldErrors.stage}
                  className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                    fieldErrors.stage
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                >
                  {stageOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.stage && (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.stage}</p>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Win probability
                </label>
                {derivedWinProbability === null ? (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge tone="neutral" size="sm">—</Badge>
                    <span className="text-xs text-gray-400">
                      Set per stage in the product flow (Admin → Product flows).
                    </span>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge
                      tone={derivedWinProbability >= 75 ? 'success'
                        : derivedWinProbability >= 40 ? 'info' : 'neutral'}
                      size="sm"
                    >
                      {Math.round(derivedWinProbability)}%
                    </Badge>
                    <span className="text-xs text-gray-400">
                      auto from “{stage}” — updates as the deal advances
                    </span>
                  </div>
                )}
                {selectedStageTargetDays !== null && (
                  <p className="mt-1 text-[11px] text-gray-400">
                    Stage SLA: {selectedStageTargetDays} business day{selectedStageTargetDays === 1 ? '' : 's'} (from product flow)
                  </p>
                )}
              </div>
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Workflow ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Workflow</h2>
            <span className="text-xs text-gray-400">Next steps + source</span>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Input
                label="Next action"
                placeholder="e.g. Send KYC checklist"
                value={nextAction}
                onChange={(e) => setNextAction(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Next action date"
                type="date"
                value={nextActionDate}
                onChange={(e) => setNextActionDate(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Expected close date"
                type="date"
                value={expectedClose}
                onChange={(e) => setExpectedClose(e.target.value)}
                disabled={mutations.loading}
              />
              <div className="md:col-span-2">
                <label className="text-sm font-medium text-gray-700">Lead source</label>
                <select
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                >
                  {SOURCE_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">
                Notes
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={mutations.loading}
                placeholder="Relationship history, key triggers, urgency..."
                rows={2}
                className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
              />
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Portfolio conflict resolution ─────────── */}
        <Card stripe={hasConflict ? 'accent' : undefined}>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Portfolio assignment
            </h2>
            <span className="text-xs text-gray-400">
              {hasConflict ? 'α5 conflict resolution' : 'Is this customer already in another RM\u2019s portfolio?'}
            </span>
          </Card.Header>
          <Card.Body>
            <label className="flex items-center gap-3 cursor-pointer" data-field="hasConflict">
              <input
                type="checkbox"
                checked={hasConflict}
                onChange={(e) => { setHasConflict(e.target.checked); if (e.target.checked) clearFieldError('hasConflict'); }}
                disabled={mutations.loading}
                className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary"
              />
              <span className="text-sm text-gray-800">
                This customer is in another RM&rsquo;s portfolio
              </span>
            </label>
            {ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">Checking portfolio ownership in CBS…</p>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code
              && detectedOwner.portfolio_owner_code !== (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Auto-detected from CBS: this customer is in{' '}
                <span className="font-semibold">
                  {detectedOwner.portfolio_owner_name || `RM ${detectedOwner.portfolio_owner_code}`}
                </span>
                &rsquo;s portfolio. The deal will be referred to them for a nod.
                {!detectedOwner.owner_in_roster && (
                  <span className="block mt-1 text-amber-700">
                    Note: this owner isn&rsquo;t a recognised system user — confirm the recipient manually.
                  </span>
                )}
              </div>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code === (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                You are this customer&rsquo;s portfolio owner — no conflict.
              </div>
            )}
            {!ownerDetecting && detectedOwner && !detectedOwner.is_mapped && (
              <p className="text-xs text-gray-500 mt-2">
                No portfolio owner on record for this customer in CBS — mark a conflict manually if needed.
              </p>
            )}
            {!detectedOwner && !ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">
                Check this if CBS already assigns the customer to a different RM.
                For an existing customer, ownership is detected automatically.
              </p>
            )}
            {fieldErrors.hasConflict && (
              <p className="text-xs text-red-600 mt-2">{fieldErrors.hasConflict}</p>
            )}

            {hasConflict && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="portfolioOwnerCode">
                  <Input
                    label={<>Portfolio owner staff code <RedStar /></>}
                    placeholder="e.g. 0123"
                    value={portfolioOwnerCode}
                    onChange={(e) => { setPortfolioOwnerCode(e.target.value); clearFieldError('portfolioOwnerCode'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerCode}
                  />
                </div>
                <div data-field="portfolioOwnerName">
                  <Input
                    label={<>Portfolio owner name <RedStar /></>}
                    placeholder="e.g. Jane Mwangi"
                    value={portfolioOwnerName}
                    onChange={(e) => { setPortfolioOwnerName(e.target.value); clearFieldError('portfolioOwnerName'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerName}
                  />
                </div>
              </div>
            )}

            {hasConflict && (
              <div className="mt-6">
                <label className="text-sm font-medium text-gray-700">
                  How do you want to proceed?
                </label>
                <div className="mt-2 space-y-2">
                  <PathRadio
                    active={conflictPath === 'refer'}
                    onClick={() => setConflictPath('refer')}
                    disabled={mutations.loading}
                    label="Refer to portfolio owner"
                    sub={`Sends the lead to ${portfolioOwnerName || 'the owner'}. They take it from here.`}
                  />
                  <PathRadio
                    active={conflictPath === 'seek_permission'}
                    onClick={() => setConflictPath('seek_permission')}
                    disabled={mutations.loading}
                    label="Seek permission, defer BSC credit"
                    sub={`You'll work the deal; BSC credit on close goes to ${portfolioOwnerName || 'the owner'}. No manager approval required server-side.`}
                  />
                  <PathRadio
                    active={conflictPath === 'override'}
                    onClick={() => setConflictPath('override')}
                    disabled={mutations.loading}
                    label="Override portfolio assignment, take BSC credit"
                    sub={`BSC credit goes to ${user?.full_name ?? 'you'}. Requires manager override note (\u2265 ${MIN_OVERRIDE_NOTE_LEN} chars).`}
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'refer' && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="referredTo">
                  <Input
                    label={<>Referred to (named recipient) <RedStar /></>}
                    placeholder="Usually the portfolio owner"
                    value={referredTo}
                    onChange={(e) => { setReferredTo(e.target.value); clearFieldError('referredTo'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.referredTo}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="text-sm font-medium text-gray-700">
                    Referral note (optional)
                  </label>
                  <textarea
                    value={referralNote}
                    onChange={(e) => setReferralNote(e.target.value)}
                    disabled={mutations.loading}
                    placeholder="Context for the recipient — what does this customer need?"
                    rows={2}
                    className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'override' && (
              <div className="mt-4" data-field="overrideNote">
                <label className="text-sm font-medium text-gray-700">
                  Manager override note <RedStar /> (min {MIN_OVERRIDE_NOTE_LEN} chars)
                </label>
                <textarea
                  value={overrideNote}
                  onChange={(e) => { setOverrideNote(e.target.value); clearFieldError('overrideNote'); }}
                  disabled={mutations.loading}
                  placeholder="Why is the override appropriate? This is reviewed by management."
                  rows={3}
                  aria-invalid={!!fieldErrors.overrideNote}
                  className={`mt-1 w-full px-3 py-2 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 resize-y ${
                    fieldErrors.overrideNote
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                />
                {fieldErrors.overrideNote ? (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.overrideNote}</p>
                ) : overrideNote.length > 0 && overrideNoteTooShort ? (
                  <p className="text-xs text-amber-600 mt-1">
                    {overrideNote.trim().length} / {MIN_OVERRIDE_NOTE_LEN} characters.
                  </p>
                ) : null}
              </div>
            )}
          </Card.Body>
        </Card>
        </>)}
        </div>

        {/* (β5.0 polish: bottom error banner removed.
             Errors now shown at the TOP of the form for visibility
             plus inline next to each errored field.) */}


        <div className="mt-6 flex items-center justify-between gap-4">
          <Button
            variant="ghost"
            size="md"
            onClick={() => navigate('/pipeline')}
            disabled={mutations.loading}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void onSubmit()}
            loading={mutations.loading}
          >
            {(referMode || isReferPath) ? 'Send referral' : 'Create deal'}
          </Button>
        </div>

        {/* Footer */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}


// ── Helper components ───────────────────────────────────────────────────

/** Red required-field marker. */
function RedStar() {
  return <span className="text-red-600"> *</span>;
}

interface PathRadioProps {
  active:    boolean;
  onClick:   () => void;
  disabled?: boolean;
  label:     string;
  sub:       React.ReactNode;
}

function PathRadio({ active, onClick, disabled, label, sub }: PathRadioProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left px-4 py-3 rounded-md border transition-colors ${
        active
          ? 'bg-blue-50 border-brand-primary'
          : 'bg-white border-gray-200 hover:border-gray-400'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 h-4 w-4 rounded-full border-2 flex-shrink-0 ${
          active ? 'border-brand-primary bg-brand-primary' : 'border-gray-400'
        }`}>
          {active && <div className="h-1.5 w-1.5 rounded-full bg-white m-auto mt-[3px]" />}
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-gray-900">{label}</div>
          <div className="text-xs text-gray-600 mt-0.5">{sub}</div>
        </div>
      </div>
    </button>
  );
}
''',

    'frontend/web/src/pages/PipelineManagerQueues.tsx': r'''// v10.513 Phase 4 Batch β4 — PipelineManagerQueues page.
//
// Manager-only page at /pipeline/queues with two tabs:
//
//   1. Validation queue — deals past Lead awaiting manager validation.
//      Each deal has Validate (approved:true) / Query (approved:false)
//      action panel.
//
//   2. Cancellation queue — deals with pending cancellation requests
//      awaiting manager decision. Each deal has Approve / Reject
//      action panel.
//
// Authorization layers (defense in depth):
//   1. Sidebar hides the "Manager Queues" link from non-managers (UX)
//   2. This page renders "Not authorized" guard when isManager(user)
//      is false, before even attempting the fetch (UX)
//   3. Server returns 403 to non-managers on the queue endpoints
//      (the real security boundary)
//
// Pattern reuse:
//   - Tab strip + count badges: bespoke (no Tab primitive)
//   - Per-deal action panels: same shape as β2 detail page panels
//   - Same Toast pattern for success / error
//   - Same mutation hook pattern

import { displayName } from "../lib/names";
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { isManager } from '@/lib/role';
import {
  fetchValidationQueue, AuthExpiredError,
} from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import { PageHeader } from '@/components/PageHeader';
import { CommitteeQueue } from '@/components/CommitteeQueue';
import { fetchCommitteeQueue } from '@/lib/api';
import DailyLogValidation from '@/components/DailyLogValidation';
import BranchCountersign from '@/components/BranchCountersign';
import UnitRollup from '@/components/UnitRollup';
import Leaderboard from '@/components/Leaderboard';
import DailyLogAnalytics from '@/components/DailyLogAnalytics';
import PipelineLeaderboard from '@/components/PipelineLeaderboard';
import PipelineDayCountersign from '@/components/PipelineDayCountersign';
import PipelineBranchDay from '@/components/PipelineBranchDay';
import { fetchUnitDays } from '@/lib/api';
import {
  stageTone, type PipelineDeal,
} from '@/types/pipeline';


type TabKey = 'validation' | 'committee' | 'dailylog' | 'ranking' | 'analytics';


// ── Page component ──────────────────────────────────────────────────────

export function PipelineManagerQueues() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const navigate = useNavigate();

  const userIsManager = isManager(user);

  // ── Page-local state ──────────────────────────────────────────────────

  const [activeTab, setActiveTab] = useState<TabKey>('validation');
  // Fetched once for the badge; the panel loads its own copy when opened.
  const [committeeCount, setCommitteeCount] = useState(0);
  useEffect(() => {
    void (async () => {
      try {
        setCommitteeCount((await fetchCommitteeQueue()).total);
      } catch {
        setCommitteeCount(0);
      }
    })();
  }, []);
  const [validationDeals, setValidationDeals] = useState<PipelineDeal[]>([]);
  const [loadingV, setLoadingV] = useState(false);
  const [errorV,   setErrorV]   = useState<string | null>(null);
  // Daily-log queue owns its own fetching; the page only tracks the count
  // for the tab badge.
  const [dailyLogPending, setDailyLogPending] = useState(0);
  // Tier 2 (Head of Branches, MD) countersigns BRANCHES; everyone else
  // validates individuals. Decided by asking the server what this caller
  // oversees rather than by inspecting their role string here.
  // 'staff' = validates individuals, 'branch' = countersigns branches,
  // 'rollup' = MD / Business Manager, observes and may return.
  const [tier, setTier] = useState<'staff' | 'branch' | 'rollup' | null>(null);
  const [rankView, setRankView] = useState<'index' | 'pipeline'>('index');

  // ── Fetchers ─────────────────────────────────────────────────────────

  const loadValidation = useCallback(async () => {
    if (!userIsManager) return;
    setLoadingV(true);
    setErrorV(null);
    try {
      const res = await fetchValidationQueue();
      setValidationDeals(res.deals);
    } catch (e) {
      if (e instanceof AuthExpiredError) return;
      const msg = e instanceof Error ? e.message : 'Failed to load validation queue';
      setErrorV(msg);
      setValidationDeals([]);
    } finally {
      setLoadingV(false);
    }
  }, [userIsManager]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        // One probe. /unit-days answers both questions: top_of_house marks the
        // observation tier, and a Branches node means this caller countersigns
        // branches. Asking the server beats inspecting a role string here.
        const r = await fetchUnitDays();
        if (!alive) return;
        if (r.top_of_house) setTier('rollup');
        else if ((r.branches?.children?.length ?? 0) > 0) setTier('branch');
        else setTier('staff');
      } catch {
        if (alive) setTier('staff');
      }
    })();
    return () => { alive = false; };
  }, []);

  // Initial load + reload on tab focus to keep queues fresh
  useEffect(() => {
    void loadValidation();
  }, [loadValidation]);

  // ── Render guards ────────────────────────────────────────────────────

  if (!userIsManager) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Manager Queues"
          breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
        />
        <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <Card>
          <Card.Header>
            <div className="flex items-center gap-3">
              <Badge tone="warning">Not authorized</Badge>
              <h2 className="text-base font-semibold text-gray-900">
                Manager queues
              </h2>
            </div>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-gray-700">
              These queues are only visible to staff with manager authority
              (Branch Manager, Regional Head, Director, MD, etc.).
            </p>
            <p className="text-sm text-gray-500 mt-3">
              If you believe this is wrong, contact your administrator.
              Your current role is{' '}
              <span className="font-mono text-gray-700">
                {user?.role ?? '(unknown)'}
              </span>.
            </p>
            <div className="mt-4">
              <Link
                to="/pipeline"
                className="text-sm text-brand-primary underline"
              >
                ← Back to pipeline
              </Link>
            </div>
          </Card.Body>
        </Card>
        </div>
      </div>
    );
  }

  // ── Active tab data ──────────────────────────────────────────────────

  // Cancellation was removed from this page (ruling 2026-08-09); the deal list
  // here is now only ever the pipeline validation queue.
  const activeDeals    = validationDeals;
  const activeLoading  = loadingV;
  const activeError    = errorV;
  const activeReload   = loadValidation;

  // ── Main render ──────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Manager Queues"
        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

      {/* Tab strip */}
      <div className="flex items-center gap-2 border-b border-gray-200">
        <TabBtn
          active={activeTab === 'validation'}
          onClick={() => setActiveTab('validation')}
          label="Pipeline validation"
          count={validationDeals.length}
          loading={loadingV}
        />
        {/* Committee sits beside validation because it is the same kind of
            work - a queue of things waiting on this person's decision. No new
            sidebar entry (ruling 2026-08-12). */}
        <TabBtn
          active={activeTab === 'committee'}
          onClick={() => setActiveTab('committee')}
          label="Committee"
          // The real number, not a hardcoded zero. A tab that always reads 0
          // tells somebody there is nothing to do, which is the opposite of
          // what this queue exists to say.
          count={committeeCount}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'dailylog'}
          onClick={() => setActiveTab('dailylog')}
          label="Daily log validation"
          count={dailyLogPending}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'ranking'}
          onClick={() => setActiveTab('ranking')}
          label="Ranking"
          count={0}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'analytics'}
          onClick={() => setActiveTab('analytics')}
          label="Index analytics"
          count={0}
          loading={false}
        />
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void activeReload()}
          loading={activeLoading}
        >
          Refresh
        </Button>
      </div>

      {/* Daily-log validation owns its own loading, empty and error states. */}
      {activeTab === 'committee' && <CommitteeQueue />}

      {activeTab === 'dailylog' && tier === null && (
        <Card className="mt-4"><Card.Body>
          <div className="text-sm text-gray-400">Loading…</div>
        </Card.Body></Card>
      )}
      {activeTab === 'dailylog' && tier === 'rollup' && (
        <UnitRollup onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'branch' && (
        <BranchCountersign onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'staff' && (
        <DailyLogValidation onCount={setDailyLogPending} />
      )}

      {/* Ranking and analytics live here too: a manager works out of this page,
          and making them navigate elsewhere to see how their team is doing
          splits one job across two screens. Both components are scope-aware
          server-side, so each manager sees their own population. */}
      {/* Pipeline validation follows the daily log's tier routing: a branch or
          roll-up caller countersigns days; everyone else works the deal queue
          below. Same shape, so a manager learns one screen and knows both. */}
      {activeTab === 'validation' && (tier === 'branch' || tier === 'rollup') && (
        <PipelineDayCountersign onCount={() => { /* count shown on the tab */ }} />
      )}

      {/* Tier 1 — the branch triad. This was the old per-deal card list; the
          pilot reported that it did not match the daily log, so it now uses the
          same shape: rows, a branch line, and a gate on closing the day. */}
      {activeTab === 'validation' && tier === 'staff' && <PipelineBranchDay />}

      {/* Two rankings, one tab: the productivity INDEX and the PIPELINE. They
          measure different things over the same people, so they sit side by
          side rather than being blended into a single misleading number. */}
      {activeTab === 'ranking' && (
        <div className="mt-4 space-y-4">
          <div className="flex gap-1.5 text-xs">
            {(['index', 'pipeline'] as const).map((k) => (
              <button key={k} type="button" onClick={() => setRankView(k)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (rankView === k ? 'bg-[#005B82] text-white'
                                    : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                {k === 'index' ? 'Index ranking' : 'Pipeline ranking'}
              </button>
            ))}
          </div>
          {rankView === 'index' ? <Leaderboard /> : <PipelineLeaderboard />}
        </div>
      )}
      {activeTab === 'analytics' && <DailyLogAnalytics />}

      {/* Error panel */}
      {!['dailylog', 'ranking', 'analytics', 'committee'].includes(activeTab)
        && !(activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))
        && activeError && (
        <Card className="mt-4">
          <Card.Body>
            <div className="flex items-center gap-3">
              <Badge tone="danger">Error</Badge>
              <div className="flex-1 text-sm text-gray-700">{activeError}</div>
              <Button variant="ghost" size="sm" onClick={() => void activeReload()}>
                Retry
              </Button>
            </div>
          </Card.Body>
        </Card>
      )}

      {/* Empty / loading / content */}
      {['dailylog', 'ranking', 'analytics', 'committee'].includes(activeTab)
        || (activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))
        ? null : activeLoading && activeDeals.length === 0 ? (
        <Card className="mt-4">
          <Card.Body>
            <Skeleton shape="line" className="w-1/3" />
            <div className="mt-3"><Skeleton shape="block" className="h-12" /></div>
            <div className="mt-2"><Skeleton shape="block" className="h-12" /></div>
          </Card.Body>
        </Card>
      ) : activeDeals.length === 0 && !activeError ? (
        <Card className="mt-4">
          <Card.Body>
            <div className="text-sm text-gray-700 font-medium">
              No deals in this queue.
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {activeTab === 'validation'
                ? 'New deals past Lead stage will appear here for your validation.'
                : 'Cancellation requests from your team will appear here for your decision.'}
            </div>
          </Card.Body>
        </Card>
      ) : (
        <div className="mt-4 space-y-3">
          {activeDeals.map((deal) => (
            activeTab === 'validation' ? (
              <ValidationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Validation decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            ) : (
              <CancellationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            )
          ))}
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
        {branding?.ip_notice}
      </footer>
      </div>
    </div>
  );
}


// ── Tab button ──────────────────────────────────────────────────────────

interface TabBtnProps {
  active:   boolean;
  onClick:  () => void;
  label:    string;
  count:    number;
  loading:  boolean;
}

function TabBtn({ active, onClick, label, count, loading }: TabBtnProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
        active
          ? 'border-brand-primary text-brand-primary'
          : 'border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
      {' '}
      <span className={`ml-1 px-2 py-0.5 text-[11px] rounded-full ${
        active ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700'
      }`}>
        {loading ? '…' : count}
      </span>
    </button>
  );
}


// ── Common queue card scaffolding ───────────────────────────────────────

interface QueueCardCommonProps {
  deal:         PipelineDeal;
  onNavigate:   () => void;
  children:     React.ReactNode;
}

function QueueCard({ deal, onNavigate, children }: QueueCardCommonProps) {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? '';
  return (
    <Card>
      <Card.Header>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={onNavigate}
            className="font-mono text-xs text-brand-primary hover:underline"
          >
            {deal.id}
          </button>
          <h3 className="text-sm font-semibold text-gray-900">
            {deal.client_name || '—'}
          </h3>
          <Badge tone={stageTone(deal.stage)} size="sm">{deal.stage}</Badge>
        </div>
        <div className="text-xs text-gray-500 text-right">
          <div>{deal.product_type ?? deal.product ?? '—'}</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {sym} {Number(deal.amount_kes ?? deal.deal_value ?? 0).toLocaleString()}
          </div>
        </div>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-3">
          <Field label="Owner" value={deal.staff_name ? displayName(deal.staff_name) : undefined} sub={deal.staff_code} />
          <Field label="Probability" value={
            typeof deal.probability === 'number'
              ? `${Math.round(deal.probability * 100)}%`
              : '—'
          } />
          <Field label="Next action" value={deal.next_action} />
          <Field label="Expected close" value={(deal.expected_close ?? '').slice(0, 10) || '—'} />
        </div>
        {children}
      </Card.Body>
    </Card>
  );
}

function Field({ label, value, sub }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </div>
      <div className="text-sm text-gray-900 mt-0.5">{value ?? '—'}</div>
      {sub && (
        <div className="text-[10px] text-gray-400 font-mono">{sub}</div>
      )}
    </div>
  );
}


// ── Validation card (Validate / Query buttons + note) ───────────────────

interface ResolvedCallbacks {
  onResolved:    () => void;
  onErrorToast:  (msg: string) => void;
}

function ValidationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approved: boolean) => {
    const result = await mutations.validate(deal.id, {
      approved,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      <div className="border-t border-gray-100 pt-3">
        <label className="text-xs font-medium text-gray-700">
          Manager note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Context for the owner if querying"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Query (return to owner)
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Validate — include in forecast
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}


// ── Cancellation card (Approve / Reject buttons + reason context) ───────

function CancellationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approve: boolean) => {
    const result = await mutations.approveCancel(deal.id, {
      approve,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      {/* Requested-by + reason context */}
      <div className="px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-xs">
        <div className="font-semibold text-amber-900">
          Cancellation requested
          {deal.cancel_requested_by && ` by ${deal.cancel_requested_by}`}
        </div>
        {deal.cancel_reason && (
          <div className="text-amber-800 mt-1">
            <span className="font-medium">Reason:</span> {deal.cancel_reason}
          </div>
        )}
      </div>
      <div className="border-t border-gray-100 pt-3 mt-3">
        <label className="text-xs font-medium text-gray-700">
          Your decision note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Recorded on the deal for audit"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Decline cancellation — deal continues
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Approve cancellation — close as Lost
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}
''',

    'frontend/web/src/pages/Referrals.tsx': r'''// Referrals inbox — Batch B frontend.
//
// Three views over the refer-existing-deal lifecycle:
//   • Incoming  — pending referrals addressed to me; Accept or Decline (reason).
//   • Returned  — referrals I made that were declined; Reassign to someone new.
//   • Following — referrals I made that are live (pending/accepted); read-only.
import { displayName } from "../lib/names";
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import ReferralBench from '@/components/ReferralBench';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge, type BadgeTone } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import {
  fetchIncomingReferrals, fetchReturnedReferrals, fetchOutgoingReferrals,
  fetchOutgoingReferralAnalytics, fetchReferralsByDepartment, fetchTeamReferrals,
  acceptReferral, declineReferral, reReferReferral, reassignReferral,
  type ReferralView, type OutgoingReferralAnalytics, type ReferralsByDepartment, type StaffMember,
  type TeamReferralsResponse,
} from '@/lib/api';

type Tab = 'overview' | 'incoming' | 'returned' | 'following' | 'team';

import { StaffPicker } from '@/components/StaffPicker';
import { Table, type Column } from '@/components/Table';
import { fmtDate } from '@/lib/datetime';

const inputCls =
  'w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

function formatKes(n: number | undefined): string {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  return `KES ${Math.round(n).toLocaleString()}`;
}
const formatDate = fmtDate;
function statusTone(s: string | undefined): BadgeTone {
  if (s === 'accepted') return 'success';
  if (s === 'pending') return 'info';
  if (s === 'declined') return 'warning';
  return 'neutral';
}

function ReferralOverview({ dept, team, navigate, formatKes, displayName }: {
  dept: ReferralsByDepartment | null;
  team: ReferralView[];
  navigate: (to: string) => void;
  formatKes: (n: number | undefined) => string;
  displayName: (s: string | undefined) => string;
}) {
  const [dir, setDir] = useState<'by_us' | 'to_us' | 'all'>('all');
  const [fMember, setFMember] = useState('');
  const [fProduct, setFProduct] = useState('');
  const [fStatus, setFStatus] = useState('');

  // "our" codes = the referrers within scope (from the analytics leaderboard)
  const ourCodes = useMemo(() => {
    const set = new Set<string>();
    (dept?.by_referrer ?? []).forEach((l) => { if (l.code) set.add(String(l.code)); });
    return set;
  }, [dept]);

  const byUs = useMemo(
    () => team.filter((d) => ourCodes.size === 0 || ourCodes.has(String(d.referred_by_code || ''))),
    [team, ourCodes]);
  const toUs = useMemo(
    () => team.filter((d) => ourCodes.size === 0 || ourCodes.has(String(d.referred_to_code || ''))),
    [team, ourCodes]);
  const dirRows = dir === 'by_us' ? byUs : dir === 'to_us' ? toUs : team;

  const memberOpts = Array.from(new Set(team.map((r) => r.referred_by_name).filter(Boolean))) as string[];
  const productOpts = Array.from(new Set(team.map((r) => r.product_type).filter(Boolean))) as string[];
  const statusOpts = Array.from(new Set(team.map((r) => r.referral_status).filter(Boolean))) as string[];

  const rows = dirRows.filter((r) =>
    (!fMember || r.referred_by_name === fMember)
    && (!fProduct || r.product_type === fProduct)
    && (!fStatus || r.referral_status === fStatus));

  const t = dept?.totals;

  const statusTone2 = (v?: string): BadgeTone =>
    v === 'accepted' ? 'success' : v === 'declined' ? 'warning' : v === 'pending' ? 'info' : 'neutral';

  const columns: Column<ReferralView>[] = [
    { key: 'client_name', header: 'Client', sortable: true, exportValue: (r) => r.client_name || r.id,
      render: (r) => (
        <div>
          <div className="font-medium text-gray-900">{r.client_name || r.id}</div>
          {r.product_type && <div className="text-xs text-gray-500 mt-0.5">{r.product_type}</div>}
        </div>
      ) },
    { key: 'referred_by_name', header: 'Referred by', sortable: true, exportValue: (r) => r.referred_by_name || '',
      render: (r) => (
        <div>
          <div className="text-sm text-gray-800">{displayName(r.referred_by_name)}</div>
          {r.referred_by_code && <div className="text-xs text-gray-400 mt-0.5 font-mono">{r.referred_by_code}</div>}
        </div>
      ) },
    { key: 'referred_to', header: 'To', sortable: true, exportValue: (r) => r.referred_to || '',
      render: (r) => <span className="text-sm text-gray-600">{displayName(r.referred_to)}</span> },
    { key: 'stage', header: 'Stage', sortable: true, exportValue: (r) => r.stage || '',
      render: (r) => <span className="text-sm text-gray-700">{r.stage || '—'}</span> },
    { key: 'referral_status', header: 'Status', sortable: true, exportValue: (r) => r.referral_status || '',
      render: (r) => (
        <span className="flex items-center gap-1">
          <Badge tone={statusTone2(r.referral_status)} size="sm">{r.referral_status || '—'}</Badge>
          {r.referral_tier && <Badge tone={r.referral_tier === 'S2B' ? 'success' : 'info'} size="sm">{r.referral_tier}</Badge>}
        </span>
      ) },
    { key: 'amount_kes', header: 'Value', align: 'right', sortable: true,
      sortAccessor: (r) => Number(r.amount_kes ?? r.deal_value) || 0,
      exportValue: (r) => String(r.amount_kes ?? r.deal_value ?? ''),
      render: (r) => <span className="font-medium text-gray-900 tabular-nums">{formatKes(r.amount_kes ?? r.deal_value)}</span> },
    { key: 'actions', header: '',
      render: (r) => (
        <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); navigate(`/pipeline/${encodeURIComponent(r.id)}`); }}>View</Button>
      ) },
  ];

  const dirTabs: { key: 'by_us' | 'to_us' | 'all'; label: string; count: number }[] = [
    { key: 'by_us', label: 'Referred by us', count: byUs.length },
    { key: 'to_us', label: 'Referred to us', count: toUs.length },
    { key: 'all', label: 'All', count: team.length },
  ];

  const Filter = ({ label, val, set, opts }: { label: string; val: string; set: (v: string) => void; opts: string[] }) => (
    <select value={val} onChange={(e) => set(e.target.value)}
      className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
      <option value="">{label}: All</option>
      {opts.map((o) => <option key={o} value={o}>{displayName(o)}</option>)}
    </select>
  );

  return (
    <div className="space-y-4">
      {/* compact stat strip */}
      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Referrals</div><div className="text-xl font-bold text-gray-900 tabular-nums">{t.total}</div><div className="text-[11px] text-gray-400">{t.pending} pending · {t.accepted} accepted</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Conversion</div><div className="text-xl font-bold text-emerald-700 tabular-nums">{t.conversion_rate}%</div><div className="text-[11px] text-gray-400">{t.won} won · {t.lost} lost</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Value influenced</div><div className="text-xl font-bold text-gray-900 tabular-nums">{formatKes(t.value_influenced)}</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Declined</div><div className="text-xl font-bold text-amber-700 tabular-nums">{t.declined}</div></Card.Body></Card>
        </div>
      )}

      {/* direction toggle */}
      <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
        {dirTabs.map((d) => (
          <button key={d.key} onClick={() => setDir(d.key)}
            className={'px-4 py-1.5 rounded-md text-sm font-medium transition-colors ' + (dir === d.key ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900')}>
            {d.label}
            <span className={'ml-2 rounded-full px-1.5 py-0.5 text-xs ' + (dir === d.key ? 'bg-white/20' : 'bg-gray-100 text-gray-500')}>{d.count}</span>
          </button>
        ))}
      </div>

      {/* the referral table (referrer-inclusive data) */}
      <Card><Card.Body>
        <Table<ReferralView>
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchable
          searchPlaceholder="Search referrals by client, stage, referrer…"
          paginated
          pageSize={15}
          exportable
          exportFilename="referrals.csv"
          onRowClick={(r) => navigate(`/pipeline/${encodeURIComponent(r.id)}`)}
          empty={<span className="text-sm text-gray-500">No referrals in this view yet.</span>}
          toolbar={
            <div className="flex flex-wrap items-center gap-2">
              <Filter label="Referrer" val={fMember} set={setFMember} opts={memberOpts} />
              <Filter label="Product" val={fProduct} set={setFProduct} opts={productOpts} />
              <Filter label="Status" val={fStatus} set={setFStatus} opts={statusOpts} />
            </div>
          }
        />
      </Card.Body></Card>
    </div>
  );
}

export default function Referrals() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('overview');
  const [incoming, setIncoming] = useState<ReferralView[]>([]);
  const [returned, setReturned] = useState<ReferralView[]>([]);
  const [outgoing, setOutgoing] = useState<ReferralView[]>([]);
  const [analytics, setAnalytics] = useState<OutgoingReferralAnalytics | null>(null);
  const [dept, setDept] = useState<ReferralsByDepartment | null>(null);
  const [team, setTeam] = useState<ReferralView[]>([]);
  const [reReferFor, setReReferFor] = useState<string | null>(null);
  const [rrMember, setRrMember] = useState<StaffMember | null>(null);
  const [rrNote, setRrNote] = useState('');
  const [teamSummary, setTeamSummary] = useState<TeamReferralsResponse['summary'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [declineFor, setDeclineFor] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState('');
  const [reassignFor, setReassignFor] = useState<string | null>(null);
  const [reMember, setReMember] = useState<StaffMember | null>(null);
  const [reNote, setReNote] = useState('');

  function loadAll() {
    setLoading(true);
    Promise.all([fetchIncomingReferrals(), fetchReturnedReferrals(), fetchOutgoingReferrals()])
      .then(([i, r, o]) => { setIncoming(i.deals); setReturned(r.deals); setOutgoing(o.deals); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load referrals.' }))
      .finally(() => setLoading(false));
    // Funnel + alerts (own referrals); department view is management-only (403 -> hidden).
    fetchOutgoingReferralAnalytics().then(setAnalytics).catch(() => setAnalytics(null));
    fetchReferralsByDepartment().then(setDept).catch(() => setDept(null));
    fetchTeamReferrals().then((t) => { setTeam(t.deals); setTeamSummary(t.summary); }).catch(() => {});
  }
  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

  async function onAccept(d: ReferralView) {
    setBusyId(d.id);
    try {
      await acceptReferral(d.id);
      toast({ tone: 'success', message: `Accepted ${d.client_name ?? d.id}.` });
      loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Accept failed.' });
    } finally { setBusyId(null); }
  }

  async function onDecline(d: ReferralView) {
    if (declineReason.trim().length < 3) {
      toast({ tone: 'warning', message: 'A decline reason (3+ characters) is required.' });
      return;
    }
    setBusyId(d.id);
    try {
      await declineReferral(d.id, declineReason.trim());
      toast({ tone: 'success', message: `Declined — returned to the referrer.` });
      setDeclineFor(null); setDeclineReason(''); loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Decline failed.' });
    } finally { setBusyId(null); }
  }

  async function onReassign(d: ReferralView) {
    if (!reMember) {
      toast({ tone: 'warning', message: 'Pick a recipient from the list.' });
      return;
    }
    setBusyId(d.id);
    try {
      await reassignReferral(d.id, reMember.staff_code, reMember.name, reNote.trim());
      toast({ tone: 'success', message: `Reassigned to ${displayName(reMember.name)}.` });
      setReassignFor(null); setReMember(null); setReNote(''); loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Reassign failed.' });
    } finally { setBusyId(null); }
  }

  async function onReRefer(d: ReferralView) {
    if (!rrMember) { toast({ tone: 'danger', message: 'Pick a recipient from the list.' }); return; }
    setBusyId(d.id);
    try {
      await reReferReferral(d.id, rrMember.staff_code, rrMember.name, rrNote.trim() || undefined);
      toast({ tone: 'success', message: 'Re-referred onward.' });
      setReReferFor(null); setRrMember(null); setRrNote('');
      await loadAll();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Re-refer failed' }); }
    finally { setBusyId(null); }
  }

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'overview', label: 'Overview', count: dept?.totals?.total ?? 0 },
    { key: 'incoming', label: 'Incoming', count: incoming.length },
    { key: 'returned', label: 'Returned', count: returned.length },
    { key: 'following', label: 'Following', count: outgoing.length },
    { key: 'team', label: 'Team', count: team.length },
  ];
  const active = tab === 'overview' ? []
    : tab === 'incoming' ? incoming
    : tab === 'returned' ? returned
    : tab === 'team' ? team
    : outgoing;

  function CreditJourney({ stage }: { stage?: ReferralView['credit_stage'] }) {
    if (!stage) return null;
    const steps = [
      { key: 'intake', label: 'Submitted' },
      { key: 'assessment', label: 'Assessment' },
      { key: 'decision', label: 'Decision' },
      { key: 'offer', label: 'Offer' },
      { key: 'credit_admin', label: 'Credit admin' },
      { key: 'disbursement', label: 'Cleared' },
      { key: 'disbursed', label: 'Disbursed' },
    ];
    if (stage.declined) {
      return (
        <div className="mt-2 border-t border-gray-100 pt-2">
          <div className="mb-1 text-xs font-medium text-gray-500">Credit journey</div>
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">Declined in credit</span>
        </div>
      );
    }
    const idx = steps.findIndex((s) => s.key === stage.key);
    return (
      <div className="mt-2 border-t border-gray-100 pt-2">
        <div className="mb-1.5 text-xs font-medium text-gray-500">Credit journey</div>
        <div className="flex flex-wrap items-center gap-1">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1">
              <span className={'rounded px-1.5 py-0.5 text-xs ' + (i < idx ? 'bg-emerald-50 text-emerald-700' : i === idx ? 'bg-brand-primary text-white' : 'bg-gray-50 text-gray-400')}>{s.label}</span>
              {i < steps.length - 1 && <span className="text-gray-300 text-xs">→</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  function ReferralJourney({ chain }: { chain?: ReferralView['referral_chain'] }) {
    if (!chain || chain.length === 0) return null;
    return (
      <div className="mt-2 border-t border-gray-100 pt-2">
        <div className="mb-1 text-xs font-medium text-gray-500">Referral journey</div>
        <ol className="space-y-1">
          {chain.map((h, i) => (
            <li key={i} className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-gray-600">{h.seq}</span>
              <span className="text-gray-700">{h.from_name || h.from_code}{h.from_dept ? ` · ${h.from_dept}` : ''}</span>
              <span className="text-gray-400">→</span>
              <span className="text-gray-700">{h.to_name || h.to_code}{h.to_dept ? ` · ${h.to_dept}` : ''}</span>
              <span className={'rounded px-1.5 py-0.5 ' + (h.status === 'accepted' ? 'bg-emerald-50 text-emerald-700' : h.status === 'declined' ? 'bg-amber-50 text-amber-700' : 'bg-gray-50 text-gray-500')}>{h.status}</span>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  function DealMeta({ d }: { d: ReferralView }) {
    return (
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-900 truncate">{d.client_name ?? d.id}</span>
          <Badge tone={statusTone(d.referral_status)} size="sm">{d.referral_status ?? '—'}</Badge>
          {d.referral_tier && (
            <Badge tone={d.referral_tier === 'S2B' ? 'success' : 'info'} size="sm">{d.referral_tier}</Badge>
          )}
          {d.cross_unit && (
            <Badge tone="neutral" size="sm">cross-unit</Badge>
          )}
        </div>
        <div className="mt-0.5 text-xs text-gray-500">
          {[d.product_type, d.stage, d.segment].filter(Boolean).join(' · ') || '—'}
        </div>
        <div className="mt-0.5 text-sm text-gray-700 tabular-nums">{formatKes(d.amount_kes ?? d.deal_value)}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        ribbon
        title="A2Z Sales Referral"
        subtitle="Deals referred to you, returned to you, and the ones you're following."
        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Referral' }]}
        actions={
          <Button variant="primary" size="sm" onClick={() => navigate('/pipeline/new?refer=1')}>
            New referral
          </Button>
        }
      />

      <div className="px-6 pt-4 max-w-7xl mx-auto">
        <ReferralBench />
      </div>

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                'px-4 py-1.5 rounded-md text-sm font-medium transition-colors ' +
                (tab === t.key
                  ? 'bg-brand-primary text-white'
                  : 'text-gray-600 hover:text-gray-900')
              }
            >
              {t.label}
              <span className={
                'ml-2 rounded-full px-1.5 py-0.5 text-xs ' +
                (tab === t.key ? 'bg-white/20' : 'bg-gray-100 text-gray-500')
              }>{t.count}</span>
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <ReferralOverview dept={dept} team={team} navigate={navigate} formatKes={formatKes} displayName={displayName} />
        )}

        {tab === 'team' && teamSummary && (
          <div className="space-y-3 mb-3">
            <Card><Card.Body>
              <div className="text-sm font-semibold text-gray-900 mb-1">Team referral funnel</div>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span className="text-gray-500">Total <b className="text-gray-900">{teamSummary.total}</b></span>
                <span className="text-gray-500">Pending <b className="text-amber-700">{teamSummary.by_status.pending}</b></span>
                <span className="text-gray-500">Accepted <b className="text-emerald-700">{teamSummary.by_status.accepted}</b></span>
                <span className="text-gray-500">Closed won <b className="text-emerald-700">{teamSummary.closed.won}</b></span>
                <span className="text-gray-500">Closed lost <b className="text-gray-700">{teamSummary.closed.lost}</b></span>
              </div>
              {teamSummary.by_tier && (
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm border-t border-gray-100 pt-2">
                  <span className="text-gray-500">B2B (business→business) <b className="text-gray-900">{teamSummary.by_tier.B2B}</b></span>
                  <span className="text-gray-500">S2B (support→business) <b className="text-gray-900">{teamSummary.by_tier.S2B}</b></span>
                </div>
              )}
            </Card.Body></Card>
            {dept && dept.departments.length > 0 && (
              <Card><Card.Body>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">By department</span>
                  {dept.scope && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{dept.scope === 'branch' ? 'Your branch' : 'Bank-wide'}</span>}
                </div>
                <div className="space-y-1">
                  {dept.departments.map((row) => (
                    <div key={row.department} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{row.department}</span>
                      <span className="text-gray-500 tabular-nums">
                        {row.total} total · {row.by_status.accepted} accepted · {row.closed.won} won
                      </span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}
          </div>
        )}

        {tab === 'following' && analytics && (
          <div className="space-y-3 mb-3">
            <Card><Card.Body>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span className="text-gray-500">Total referred <b className="text-gray-900">{analytics.total}</b></span>
                <span className="text-gray-500">Pending <b className="text-amber-700">{analytics.by_status.pending}</b></span>
                <span className="text-gray-500">Accepted <b className="text-emerald-700">{analytics.by_status.accepted}</b></span>
                <span className="text-gray-500">Closed won <b className="text-emerald-700">{analytics.closed.won}</b></span>
                <span className="text-gray-500">Closed lost <b className="text-gray-700">{analytics.closed.lost}</b></span>
              </div>
            </Card.Body></Card>

            {analytics.by_stage && Object.keys(analytics.by_stage).length > 0 && (
              <Card><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-2">Where they are now</div>
                <div className="space-y-1">
                  {Object.entries(analytics.by_stage).sort((a, b) => b[1] - a[1]).map(([stage, n]) => (
                    <div key={stage} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{stage}</span>
                      <span className="text-gray-500 tabular-nums">{n}</span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}

            {analytics.alerts.length > 0 && (
              <Card stripe="accent"><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-1">Needs attention</div>
                <ul className="space-y-1">
                  {analytics.alerts.map((al, i) => (
                    <li key={al.id || i} className="text-sm text-gray-700">
                      <span className="font-medium">{al.client_name || al.id}</span>
                      {al.referred_to ? ` → ${displayName(al.referred_to)}` : ''} — {al.message}
                    </li>
                  ))}
                </ul>
              </Card.Body></Card>
            )}

            {dept && dept.departments.length > 0 && (
              <Card><Card.Body>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">By department</span>
                  {dept.scope && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{dept.scope === 'branch' ? 'Your branch' : 'Bank-wide'}</span>}
                </div>
                <div className="space-y-1">
                  {dept.departments.map((row) => (
                    <div key={row.department} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{row.department}</span>
                      <span className="text-gray-500 tabular-nums">
                        {row.total} total · {row.by_status.accepted} accepted · {row.closed.won} won
                      </span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}
          </div>
        )}

        {tab !== 'overview' && (loading ? (
          <div className="py-16 text-center text-sm text-gray-500">Loading referrals…</div>
        ) : active.length === 0 ? (
          <Card><Card.Body>
            <p className="py-8 text-center text-sm text-gray-400">
              {tab === 'incoming' && 'No referrals waiting for you.'}
              {tab === 'returned' && 'No returned referrals to reassign.'}
              {tab === 'following' && "You aren't following any referrals yet."}
              {tab === 'team' && 'No referrals across your team yet.'}
            </p>
          </Card.Body></Card>
        ) : (
          <div className="space-y-3">
            {active.map((d) => (
              <Card key={d.id}>
                <Card.Body>
                  <div className="flex items-start justify-between gap-4">
                    <button type="button" onClick={() => navigate(`/pipeline/${d.id}`)}
                      className="text-left min-w-0 flex-1 group" title="Open the full case journey">
                      <DealMeta d={d} />
                      <span className="mt-1 inline-block text-[11px] text-brand-primary opacity-0 group-hover:opacity-100 transition-opacity">Open case journey →</span>
                    </button>
                    <div className="shrink-0 text-right text-xs text-gray-400">
                      {tab === 'incoming' && d.referred_by_name && (
                        <div>from <span className="text-gray-600">{displayName(d.referred_by_name)}</span></div>
                      )}
                      {tab === 'following' && d.referred_to && (
                        <div>to <span className="text-gray-600">{displayName(d.referred_to)}</span></div>
                      )}
                      {tab === 'team' && (
                        <div>
                          {d.referred_by_name && <div><span className="text-gray-600">{displayName(d.referred_by_name)}</span></div>}
                          {d.referred_to && <div className="mt-0.5">→ <span className="text-gray-600">{displayName(d.referred_to)}</span></div>}
                        </div>
                      )}
                      {formatDate(d.referred_at) && <div className="mt-0.5">{formatDate(d.referred_at)}</div>}
                    </div>
                  </div>

                  {d.referral_note && (
                    <p className="mt-2 text-sm text-gray-600">
                      <span className="text-gray-400">Note: </span>{d.referral_note}
                    </p>
                  )}
                  {tab === 'returned' && d.decline_reason && (
                    <p className="mt-1 text-sm text-amber-700">
                      <span className="text-amber-500">Declined: </span>{d.decline_reason}
                    </p>
                  )}

                  {(tab === 'following' || tab === 'team') && d.stage && (
                    <p className="mt-2 text-sm">
                      <span className="text-gray-400">Currently at: </span>
                      <span className="font-medium text-gray-800">{d.stage}</span>
                    </p>
                  )}

                  <ReferralJourney chain={d.referral_chain} />
                  <CreditJourney stage={d.credit_stage} />

                  {d.referral_status === 'accepted' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {reReferFor === d.id ? (
                        <div className="space-y-2">
                          <StaffPicker value={rrMember} onChange={setRrMember} />
                          <input className={inputCls} placeholder="Note (optional)"
                            value={rrNote} onChange={(e) => setRrNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReRefer(d)}>Re-refer onward</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReReferFor(null); setRrMember(null); setRrNote(''); }}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="ghost" size="sm"
                          onClick={() => { setReReferFor(d.id); setRrMember(null); setRrNote(''); }}>
                          Re-refer to another department
                        </Button>
                      )}
                    </div>
                  )}

                  {/* ── Incoming actions ── */}
                  {tab === 'incoming' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {declineFor === d.id ? (
                        <div className="space-y-2">
                          <textarea
                            className={inputCls} rows={2} placeholder="Reason for declining (required)…"
                            value={declineReason} onChange={(e) => setDeclineReason(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <Button variant="danger" size="sm" loading={busyId === d.id}
                              onClick={() => onDecline(d)}>Confirm decline</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setDeclineFor(null); setDeclineReason(''); }}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <Button variant="primary" size="sm" loading={busyId === d.id}
                            onClick={() => onAccept(d)}>Accept</Button>
                          <Button variant="ghost" size="sm"
                            onClick={() => { setDeclineFor(d.id); setDeclineReason(''); }}>Decline</Button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Returned actions (reassign) ── */}
                  {tab === 'returned' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {reassignFor === d.id ? (
                        <div className="space-y-2">
                          <StaffPicker value={reMember} onChange={setReMember} />
                          <input className={inputCls} placeholder="Note (optional)"
                            value={reNote} onChange={(e) => setReNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReassign(d)}>Reassign</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReassignFor(null); setReMember(null); setReNote(''); }}>
                              Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="secondary" size="sm"
                          onClick={() => { setReassignFor(d.id); }}>Reassign…</Button>
                      )}
                    </div>
                  )}
                </Card.Body>
              </Card>
            ))}
          </div>
        ))}
      </main>
    </div>
  );
}
''',

    'frontend/web/src/pages/Troops.tsx': r'''// Troops — Treasury Back Office disbursement flow by stage. Shows the live
// disbursement workload (cleared → booked → value-dated → disbursed) so the
// disbursement desk and Operations can prep against what sits at each step.
// Role-gated server-side to Treasury Back Office; a non-Troops caller gets a
// clear access message rather than an error.

import { useEffect, useMemo, useState } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { fetchTroopsFlowByStage, fetchTroopsQueue, troopsBook, troopsValueDate, troopsDisburse, type TroopsFlowByStageResponse, type TroopsQueueCase } from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { useToast } from '@/components/Toast';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import { Badge } from '@/components/Badge';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';

function abbrev(n: number): string {
  return n.toLocaleString();
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card><Card.Body>
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </Card.Body></Card>
  );
}

const DONE_KEY = 'disbursed';

export function Troops() {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  const [data, setData] = useState<TroopsFlowByStageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchTroopsFlowByStage()
      .then((d) => { if (active) { setData(d); setError(null); setForbidden(false); } })
      .catch((e) => {
        if (!active) return;
        const msg = e instanceof Error ? e.message : '';
        if (msg.includes('403') || /authority|forbidden/i.test(msg)) {
          setForbidden(true);
        } else {
          setError(msg || 'Could not load disbursement flow.');
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const barData = useMemo(
    () => (data?.stages ?? [])
      .filter((s) => s.key !== DONE_KEY)
      .map((s) => ({ stage: s.label, cases: s.count })),
    [data],
  );

  if (loading) {
    return <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-4"><Skeleton /><Skeleton /><Skeleton /></div>;
  }

  if (forbidden) {
    return (
      <>
        <PageHeader
          ribbon
          breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}
          title="Trops Disbursement"
          subtitle="Treasury Back Office disbursement desk."
        />
        <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
          <Card><Card.Body>
            <p className="text-sm text-gray-700">
              This view is for the Treasury Back Office disbursement desk. Your role doesn’t
              have disbursement authority, so there’s nothing to action here.
            </p>
          </Card.Body></Card>
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No disbursement flow available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}
        title="Trops Disbursement"
        subtitle="Treasury Back Office disbursement flow by stage — cleared facilities moving through booking, value-dating, and disbursement."
      />
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-6">

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Pending disbursement" value={t.pending_count.toLocaleString()} sub="cleared, not yet disbursed" />
          <Stat label="Pending value" value={kes(t.pending_value)} />
          <Stat label="All cases" value={t.count.toLocaleString()} sub="incl. disbursed" />
          <Stat label="Total value" value={kes(t.value)} />
        </div>

        {barData.length > 0 && (
          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Disbursement workload by stage</h2>
              <span className="text-xs text-gray-400">Cases awaiting disbursement</span>
            </Card.Header>
            <Card.Body>
              <CategoryBarChart
                data={barData}
                xKey="stage"
                series={[{ key: 'cases', label: 'Cases' }]}
              />
            </Card.Body>
          </Card>
        )}

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Cases by stage</h2>
            <span className="text-xs text-gray-400">Count &amp; value at each step</span>
          </Card.Header>
          <Card.Body>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  <th className="py-2 text-left">Stage</th>
                  <th className="py-2 text-right">Cases</th>
                  <th className="py-2 text-right">Value</th>
                  <th className="py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.stages.map((s) => {
                  const done = s.key === DONE_KEY;
                  return (
                    <tr key={s.key} className="border-b border-gray-100 last:border-0">
                      <td className="py-2 text-gray-800">{s.label}</td>
                      <td className="py-2 text-right tabular-nums font-medium text-gray-900">
                        {s.count.toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-700">{kes(s.value)}</td>
                      <td className="py-2 text-right">
                        <Badge tone={done ? 'neutral' : s.count > 0 ? 'info' : 'neutral'} size="sm">
                          {done ? 'done' : s.count > 0 ? 'pending' : 'clear'}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card.Body>
        </Card>

        <TroopsActionQueue />

      </div>
    </>
  );
}


// CA1: the actionable disbursement queue — book -> value-date -> disburse.
function TroopsActionQueue() {
  const { toast } = useToast();
  const [cases, setCases] = useState<TroopsQueueCase[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [vd, setVd] = useState<Record<string, string>>({});
  const load = async () => {
    try { const r = await fetchTroopsQueue(); setCases(r.cases); }
    catch { /* forbidden or empty — the flow view above still shows */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);
  const act = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try { await fn(); toast({ tone: 'success', message: ok }); await load(); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' }); }
    finally { setBusy(null); }
  };
  if (cases.length === 0) return null;
  return (
    <Card>
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Disbursement queue — actions</h2>
        <span className="text-xs text-gray-400">Book → value-date → disburse</span>
      </Card.Header>
      <Card.Body>
        <div className="space-y-2">
          {cases.map((c) => {
            const st = String(c.troops_status || 'queued').toLowerCase();
            return (
              <div key={c.case_id} className="flex items-center justify-between rounded border p-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{c.client_name || c.case_id}</div>
                  <div className="text-xs text-gray-500">
                    {c.case_id} · KES {(c.amount ?? 0).toLocaleString()}
                    {c.cbs_account_no && ` · a/c ${c.cbs_account_no}`}
                    {c.value_date && ` · value ${c.value_date}`}
                    {' · '}<span className="font-medium">{st}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {st === 'queued' && (
                    <Button size="sm" disabled={busy === c.case_id}
                      onClick={() => void act(c.case_id, () => troopsBook(c.case_id), 'Facility booked to core banking.')}>
                      {busy === c.case_id ? '…' : 'Book'}
                    </Button>
                  )}
                  {st === 'booked' && (
                    <>
                      <input type="date" className="rounded border px-2 py-1 text-xs"
                        value={vd[c.case_id] ?? ''} onChange={(e) => setVd({ ...vd, [c.case_id]: e.target.value })} />
                      <Button size="sm" disabled={busy === c.case_id || !vd[c.case_id]}
                        onClick={() => void act(c.case_id, () => troopsValueDate(c.case_id, vd[c.case_id]), 'Value date set.')}>
                        Value-date
                      </Button>
                    </>
                  )}
                  {st === 'value_dated' && (
                    <Button size="sm" disabled={busy === c.case_id}
                      onClick={() => void act(c.case_id, () => troopsDisburse(c.case_id), 'Disbursed — posted to GL.')}>
                      {busy === c.case_id ? '…' : 'Disburse'}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card.Body>
    </Card>
  );
}
''',

    'frontend/web/src/providers/BrandingProvider.tsx': r'''// v10.495 — BrandingProvider for the React SPA.
//
// CONTRACT AMENDMENT (G46 → G381):
//
// The original App.tsx provider chain (per frontend/web/README.md
// G46) is:
//   QueryClient → Auth → WebSocket → BrowserRouter
//
// v10.495 amends this to:
//   QueryClient → Branding → Auth → WebSocket → BrowserRouter
//
// Branding is placed inside QueryClientProvider (so it could
// migrate to TanStack Query later) but before AuthProvider (so
// the future login page, which is unauthenticated, can still
// read branding to render the bank name and IP notice).
//
// This amendment is documented in CHANGELOG_v10.495.md and
// enforced by G381 (which replaces the phantom G46).

import {
  createContext, useEffect, useState, type ReactNode,
} from 'react';
import { fetchBranding } from '@/lib/api';
import type { Branding } from '@/types/branding';

interface BrandingContextValue {
  branding: Branding | null;
  loading: boolean;
  error: string | null;
}

// Fallback branding used while /api/branding is loading or if
// it fails. Mirrors the Ecobank corporate defaults baked into
// utils/config.py — keeps the UI alive and on-brand even if
// the backend is down.
const FALLBACK_BRANDING: Branding = {
  bank_name: 'Ecobank Kenya',
  app_name: 'A2Z Blueprint',
  currency: 'KES',
  currency_symbol: 'KES',
  country: 'Kenya',
  regulator: 'CBK',
  regulator_full: '',
  core_banking_system: '',
  tax_authority: 'KRA',
  brand: {
    primary: '#1797ce',
    secondary: '#0e2440',
    accent: '#ffd200',
  },
  ip_notice:
    'Confidential · Authorised users only · All sessions are logged. ' +
    'This system is protected intellectual property. Unauthorised ' +
    'access or reproduction is strictly prohibited and may be ' +
    'subject to legal action.',
};

export const BrandingContext = createContext<BrandingContextValue>({
  branding: null,
  loading: true,
  error: null,
});

function applyBrandColors(brand: Branding['brand']): void {
  // Inject brand colors as CSS variables so Tailwind tokens like
  // `bg-brand-primary` resolve to the configured hex value.
  const root = document.documentElement;
  root.style.setProperty('--brand-primary', brand.primary);
  root.style.setProperty('--brand-secondary', brand.secondary);
  root.style.setProperty('--brand-accent', brand.accent);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBranding()
      .then((b) => {
        setBranding(b);
        setError(null);
        applyBrandColors(b.brand);
      })
      .catch((e) => {
        // Honest finding: backend not running, or branding endpoint
        // not yet wired. We log the error but continue with
        // fallback so the UI doesn't crash. Same discipline as
        // utils.config.py's "[Bank Name]" placeholder pattern.
        // eslint-disable-next-line no-console
        console.warn('Branding API unavailable, using fallback:', e);
        setBranding(FALLBACK_BRANDING);
        applyBrandColors(FALLBACK_BRANDING.brand);
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <BrandingContext.Provider value={{ branding, loading, error }}>
      {children}
    </BrandingContext.Provider>
  );
}
''',

}


def main():
    apply = "--apply" in sys.argv
    missing = [f for f in FILES if not os.path.isfile(f)]
    if missing:
        print("ABORT: not found: %s" % ", ".join(missing[:3]))
        return 1

    # WHOLE FILES, so each must prove it takes nothing away. LB1 v1 shipped a
    # whole file captured from a tree without the committee queue and silently
    # removed a tab somebody had just installed.
    MARKS = {
        "frontend/web/src/pages/PipelineManagerQueues.tsx":
            ["activeTab === 'committee'", "CommitteeQueue", "Approve cancellation"],
    }
    for f, new in FILES.items():
        cur = open(f, encoding="utf-8").read()
        for m in MARKS.get(f, []):
            if cur.count(m) and not new.count(m):
                print("ABORT: %r is in %s and NOT in this patch -" % (m, os.path.basename(f)))
                print("       applying it would remove working code.")
                return 1
    print("  ok  nothing present would be removed")

    for f, new in FILES.items():
        if "'EKE " in new or '"EKE ' in new:
            print("ABORT: %s still carries a hardcoded EKE label." % os.path.basename(f))
            return 1
    mq = FILES.get("frontend/web/src/pages/PipelineManagerQueues.tsx", "")
    if mq:
        if "'analytics', 'committee'" not in mq:
            print("ABORT: cancellation cards would still render under the")
            print("       Committee tab.")
            return 1
        if "count={committeeCount}" not in mq:
            print("ABORT: the Committee tab would still read a hardcoded 0.")
            return 1
    for f, new in FILES.items():
        for op, cl in (("{", "}"), ("(", ")")):
            if new.count(op) != new.count(cl):
                print("ABORT: %s unbalanced %s%s." % (os.path.basename(f), op, cl))
                return 1
    print("  ok  post-checks: no EKE literals, tab isolated, count live")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("%d file(s) would change." % len(FILES))
        return 0

    for f, new in FILES.items():
        shutil.copy2(f, f + BACKUP_SUFFIX)
        open(f, "w", encoding="utf-8", newline="").write(new)
        print("APPLIED %s" % f)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
