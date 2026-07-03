// AffordabilityAppraisal.tsx — shared RM/analyst multi-source affordability appraisal.
// Deterministic (no AI). Each income source (Bank X, M-Pesa, ...) has its own DSR + months
// + anomaly exclusions; a consolidation line SUMS the affordable instalments = total
// borrowing capacity. Named scenarios can be saved for the report. Amortization calc.
// Placed on BOTH the LMS application detail and the pipeline deal detail.
import { useState } from 'react';
import { analyzeMultiSource, computeAmortization, type MultiSourceResult, type AmortizationResult } from '@/lib/api';
import { useToast } from '@/components/Toast';
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

export function AffordabilityAppraisal({ defaultCif }: { defaultCif?: string }) {
  const { toast } = useToast();
  const [sources, setSources] = useState<SourceInput[]>([
    { label: 'Bank statement 1', cif: defaultCif ?? '', dsr_pct: 40, months_window: 6 },
  ]);
  const [result, setResult] = useState<MultiSourceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [scenarioName, setScenarioName] = useState('');
  const [scenarios, setScenarios] = useState<SavedScenario[]>([]);

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
      const payloadSources = sources.map((s) => {
        const txns = s.raw_transactions ? parseTxns(s.raw_transactions) : undefined;
        return {
          label: s.label,
          ...(txns && txns.length ? { transactions: txns } : {}),
          ...(s.cif ? { cif: s.cif } : {}),
          ...(s.dsr_pct != null ? { dsr_pct: s.dsr_pct } : {}),
          ...(s.months_window != null ? { months_window: s.months_window } : {}),
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

        {/* Sources */}
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

        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="ghost" onClick={addSource}>+ Add statement</Button>
          <Button variant="primary" onClick={() => void run()} disabled={busy}>{busy ? 'Analysing…' : 'Analyse & consolidate'}</Button>
        </div>

        {/* Result */}
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
          </div>
        )}

        {/* Scenarios */}
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

        {/* Amortization calculator */}
        <div className="mt-4 border-t pt-3">
          <p className="mb-2 text-xs font-medium text-gray-600">Amortization calculator</p>
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="flex flex-col">Amount (KES)
              <input type="number" value={amAmount} onChange={(e) => setAmAmount(e.target.value)} className="mt-1 rounded border border-gray-300 px-2 py-1" /></label>
            <label className="flex flex-col">Rate %/mo (blank=config)
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
