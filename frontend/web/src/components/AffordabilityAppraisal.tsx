// AffordabilityAppraisal.tsx — shared RM/analyst multi-source affordability appraisal.
// Deterministic (no AI). Each income source (Bank X, M-Pesa, ...) has its own DSR + months
// + anomaly exclusions; a consolidation line SUMS the affordable instalments = total
// borrowing capacity. Named scenarios can be saved for the report. Amortization calc.
// Placed on BOTH the LMS application detail and the pipeline deal detail.
import { useState } from 'react';
import { analyzeMultiSource, computeAmortization, computeQualifyingAmount, getDealAppraisal, saveDealAppraisal, getAppAppraisal, saveAppAppraisal, type MultiSourceResult, type AmortizationResult, type QualifyingResult } from '@/lib/api';
import { useEffect } from 'react';
import { useToast } from '@/components/Toast';
import { useBranding } from '@/hooks/useBranding';
import { Card } from '@/components/Card';
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

export function AffordabilityAppraisal({ defaultCif, dealId, appId }: { defaultCif?: string; dealId?: string; appId?: string }) {
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

  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Affordability Appraisal (multi-source)</h3></Card.Header>
      <Card.Body>
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
          {(dealId || appId) && <Button variant="ghost" onClick={() => void saveAppraisal()}>Save appraisal</Button>}
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
      </Card.Body>
    </Card>
  );
}
