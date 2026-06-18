// SLA Monitor + Configuration (Phase 4 S1/S2).
//   - Violations tab: hierarchy-scoped breach dashboard from
//     /api/pipeline/sla/violations (open deals over their step/product target,
//     with the escalation tier the overdue days reach).
//   - Configuration tab (config-admin only): edit per-step targets, the
//     escalation ladder, and per-product promises; saved via
//     /api/admin/sla-config with mandatory-before-save validation surfaced
//     back to the user.
import { useEffect, useMemo, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Badge, type BadgeTone } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchSlaConfig, saveSlaConfig, fetchSlaViolations, recordSlaCommitment,
  type SlaConfig, type SlaStep, type SlaTier, type SlaViolations, type SlaViolation,
} from '@/lib/api';

function isConfigAdminRole(role: string | undefined, isAdmin: boolean): boolean {
  if (isAdmin) return true;
  const r = (role || '').toLowerCase();
  return r.includes('chief') || r.includes('managing director')
    || r.includes('admin') || r.includes('head of');
}

function escTone(role: string | null | undefined): BadgeTone {
  switch ((role || '').toLowerCase()) {
    case 'managing_director': return 'danger';
    case 'regional_head': return 'warning';
    case 'line_manager': return 'info';
    default: return 'neutral';
  }
}

function prettyRole(role: string | null | undefined): string {
  return (role || '—').replace(/_/g, ' ');
}

type Tab = 'violations' | 'config';

export default function Sla() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const canEdit = useMemo(() => isConfigAdminRole(user?.role, isAdmin), [user?.role, isAdmin]);
  const [tab, setTab] = useState<Tab>('violations');

  const [vio, setVio] = useState<SlaViolations | null>(null);
  const [vLoading, setVLoading] = useState(true);
  const [cfg, setCfg] = useState<SlaConfig | null>(null);
  const [cLoading, setCLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newProduct, setNewProduct] = useState('');
  const [newPromise, setNewPromise] = useState('');

  // Commitment capture (S3) — which breach row's form is open + its draft.
  const [commitFor, setCommitFor] = useState<string | null>(null);
  const [cReason, setCReason] = useState('');
  const [cDate, setCDate] = useState('');
  const [cSubmitting, setCSubmitting] = useState(false);

  function refetchVio() {
    setVLoading(true);
    fetchSlaViolations().then(setVio).catch(() => setVio(null)).finally(() => setVLoading(false));
  }

  function openCommit(v: SlaViolation) {
    setCommitFor(v.deal_id);
    setCReason(v.commitment?.reason || '');
    setCDate(v.commitment?.committed_date || '');
  }
  function closeCommit() {
    setCommitFor(null);
    setCReason('');
    setCDate('');
  }
  async function submitCommit(dealId: string) {
    const reason = cReason.trim();
    if (reason.length < 5) {
      toast({ tone: 'warning', message: 'Enter a reason of at least 5 characters.' });
      return;
    }
    if (!cDate) {
      toast({ tone: 'warning', message: 'Pick a committed close date.' });
      return;
    }
    setCSubmitting(true);
    try {
      await recordSlaCommitment(dealId, reason, cDate);
      toast({ tone: 'success', message: 'Commitment recorded against the current step.' });
      closeCommit();
      refetchVio();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not record the commitment.' });
    } finally {
      setCSubmitting(false);
    }
  }

  useEffect(() => {
    fetchSlaViolations().then(setVio).catch(() => setVio(null)).finally(() => setVLoading(false));
    fetchSlaConfig().then((r) => setCfg(r.sla_config)).catch(() => setCfg(null)).finally(() => setCLoading(false));
  }, []);

  function updateStep(i: number, patch: Partial<SlaStep>) {
    setCfg((c) => (c ? { ...c, steps: c.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) } : c));
  }
  function updateTier(i: number, patch: Partial<SlaTier>) {
    setCfg((c) => (c
      ? { ...c, escalation_ladder: c.escalation_ladder.map((t, j) => (j === i ? { ...t, ...patch } : t)) }
      : c));
  }
  function setPromiseVal(prod: string, days: number) {
    setCfg((c) => (c ? { ...c, product_promise: { ...c.product_promise, [prod]: days } } : c));
  }
  function removePromise(prod: string) {
    setCfg((c) => {
      if (!c) return c;
      const pp = { ...c.product_promise };
      delete pp[prod];
      return { ...c, product_promise: pp };
    });
  }
  function addPromise() {
    const p = newProduct.trim();
    const d = Number(newPromise);
    if (!p || !Number.isFinite(d) || d <= 0) {
      toast({ tone: 'warning', message: 'Enter a product and a positive number of days.' });
      return;
    }
    setPromiseVal(p, d);
    setNewProduct('');
    setNewPromise('');
  }

  async function onSave() {
    if (!cfg) return;
    setSaving(true);
    try {
      const r = await saveSlaConfig(cfg);
      setCfg(r.sla_config);
      toast({ tone: 'success', message: 'SLA configuration saved — live immediately.' });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed — check targets and the escalation ladder.' });
    } finally {
      setSaving(false);
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'violations', label: 'Violations' },
    ...(canEdit ? [{ key: 'config' as Tab, label: 'Configuration' }] : []),
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="SLA Monitor"
        subtitle="Process turnaround targets and the deals breaching them."
        breadcrumbs={[{ label: 'Executive Intelligence' }, { label: 'SLA Monitor' }]}
      />

      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-4">
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={
                'px-4 py-1.5 rounded-md text-sm font-medium transition '
                + (tab === t.key ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900')
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'violations' && (
          <div className="space-y-3">
            {vLoading ? (
              <div className="py-16 text-center text-sm text-gray-500">Loading SLA status…</div>
            ) : !vio ? (
              <Card><Card.Body><p className="py-8 text-center text-sm text-gray-400">SLA status is unavailable.</p></Card.Body></Card>
            ) : (
              <>
                <Card><Card.Body>
                  <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                    <span className="text-gray-500">Open deals <b className="text-gray-900">{vio.open_deals}</b></span>
                    <span className="text-gray-500">Breaching <b className="text-red-700">{vio.count}</b></span>
                    <span className="text-gray-500">On step clock <b className="text-gray-900">{vio.by_clock.step}</b></span>
                    <span className="text-gray-500">On age clock <b className="text-gray-900">{vio.by_clock.age}</b></span>
                  </div>
                  {Object.keys(vio.by_escalation).length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2 text-sm">
                      <span className="text-gray-500">Escalated to:</span>
                      {Object.entries(vio.by_escalation).map(([role, n]) => (
                        <Badge key={role} tone={escTone(role)} size="sm">{prettyRole(role)} · {n}</Badge>
                      ))}
                    </div>
                  )}
                </Card.Body></Card>

                {vio.violations.length === 0 ? (
                  <Card><Card.Body><p className="py-8 text-center text-sm text-gray-400">No deals are breaching their SLA. </p></Card.Body></Card>
                ) : (
                  <Card><Card.Body>
                    <div className="text-sm font-semibold text-gray-900 mb-2">Breaching deals</div>
                    <div className="divide-y divide-gray-100">
                      {vio.violations.map((v) => (
                        <div key={v.deal_id} className="py-2.5">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium text-gray-900 truncate">{v.client_name || v.deal_id}</span>
                                <Badge tone={v.clock === 'step' ? 'info' : 'neutral'} size="sm">
                                  {v.clock === 'step' ? (v.step || 'step').replace(/_/g, ' ') : 'age clock'}
                                </Badge>
                                {v.commitment_status === 'active' && (
                                  <Badge tone="info" size="sm">committed {v.commitment?.committed_date}</Badge>
                                )}
                                {v.commitment_status === 'unfulfilled' && (
                                  <Badge tone="danger" size="sm">commitment overdue</Badge>
                                )}
                              </div>
                              <div className="mt-0.5 text-xs text-gray-500">
                                {[v.product_type, v.stage].filter(Boolean).join(' · ') || '—'}
                              </div>
                            </div>
                            <div className="flex shrink-0 items-start gap-3">
                              <div className="text-right">
                                <div className="text-sm text-gray-700 tabular-nums">
                                  {v.elapsed_business_days} / {v.target_days} bd
                                  <span className="ml-1 text-red-700 font-semibold">+{v.overdue_business_days}</span>
                                </div>
                                <div className="mt-0.5">
                                  <Badge tone={escTone(v.escalate_to)} size="sm">{prettyRole(v.escalate_to)}</Badge>
                                </div>
                              </div>
                              {v.clock === 'step' && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => (commitFor === v.deal_id ? closeCommit() : openCommit(v))}
                                >
                                  {v.commitment ? 'Update' : 'Commit'}
                                </Button>
                              )}
                            </div>
                          </div>
                          {commitFor === v.deal_id && (
                            <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
                              <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                                <Input
                                  type="text"
                                  placeholder="Reason (≥ 5 chars) — what's blocking closure?"
                                  value={cReason}
                                  onChange={(e) => setCReason(e.target.value)}
                                />
                                <Input
                                  type="date"
                                  value={cDate}
                                  onChange={(e) => setCDate(e.target.value)}
                                />
                              </div>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <Button variant="primary" size="sm" loading={cSubmitting} onClick={() => submitCommit(v.deal_id)}>
                                  Save commitment
                                </Button>
                                <Button variant="ghost" size="sm" onClick={closeCommit}>Cancel</Button>
                                <span className="text-xs text-gray-400">A missed committed date escalates to the top tier.</span>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card.Body></Card>
                )}
              </>
            )}
          </div>
        )}

        {tab === 'config' && canEdit && (
          <div className="space-y-3">
            {cLoading ? (
              <div className="py-16 text-center text-sm text-gray-500">Loading configuration…</div>
            ) : !cfg ? (
              <Card><Card.Body><p className="py-8 text-center text-sm text-gray-400">Configuration is unavailable.</p></Card.Body></Card>
            ) : (
              <>
                {!canEdit && (
                  <Card stripe="accent"><Card.Body>
                    <p className="text-sm text-gray-600">You can view the SLA configuration; editing requires a config-admin role.</p>
                  </Card.Body></Card>
                )}

                <Card><Card.Body>
                  <div className="text-sm font-semibold text-gray-900 mb-2">Step targets (business days)</div>
                  <div className="space-y-2">
                    {cfg.steps.map((s, i) => (
                      <div key={s.key} className="grid grid-cols-12 items-center gap-2">
                        <div className="col-span-5 text-sm text-gray-800">{s.label}</div>
                        <div className="col-span-4">
                          <Input
                            value={s.owner_role}
                            disabled={!canEdit}
                            onChange={(e) => updateStep(i, { owner_role: e.target.value })}
                          />
                        </div>
                        <div className="col-span-3">
                          <Input
                            type="number"
                            min={1}
                            value={String(s.target_days)}
                            disabled={!canEdit}
                            onChange={(e) => updateStep(i, { target_days: Number(e.target.value) })}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card.Body></Card>

                <Card><Card.Body>
                  <div className="text-sm font-semibold text-gray-900 mb-1">Escalation ladder</div>
                  <p className="text-xs text-gray-500 mb-2">Business days past the step target at which the breach escalates to the named role. Must increase down the list.</p>
                  <div className="space-y-2">
                    {cfg.escalation_ladder.map((t, i) => (
                      <div key={i} className="grid grid-cols-12 items-center gap-2">
                        <div className="col-span-3">
                          <Input
                            type="number"
                            min={0}
                            value={String(t.after_days)}
                            disabled={!canEdit}
                            onChange={(e) => updateTier(i, { after_days: Number(e.target.value) })}
                          />
                        </div>
                        <div className="col-span-2 text-xs text-gray-500">days →</div>
                        <div className="col-span-7">
                          <Input
                            value={t.escalate_to}
                            disabled={!canEdit}
                            onChange={(e) => updateTier(i, { escalate_to: e.target.value })}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card.Body></Card>

                <Card><Card.Body>
                  <div className="text-sm font-semibold text-gray-900 mb-1">Product promise (create → closed, business days)</div>
                  <p className="text-xs text-gray-500 mb-2">Optional per-product end-to-end target. Products without an entry fall back to the sum of step targets.</p>
                  <div className="space-y-1.5">
                    {Object.entries(cfg.product_promise).map(([prod, days]) => (
                      <div key={prod} className="grid grid-cols-12 items-center gap-2">
                        <div className="col-span-6 text-sm text-gray-800 truncate">{prod}</div>
                        <div className="col-span-4">
                          <Input
                            type="number"
                            min={1}
                            value={String(days)}
                            disabled={!canEdit}
                            onChange={(e) => setPromiseVal(prod, Number(e.target.value))}
                          />
                        </div>
                        <div className="col-span-2">
                          {canEdit && (
                            <Button variant="ghost" size="sm" onClick={() => removePromise(prod)}>Remove</Button>
                          )}
                        </div>
                      </div>
                    ))}
                    {Object.keys(cfg.product_promise).length === 0 && (
                      <p className="text-sm text-gray-400">No per-product promises set.</p>
                    )}
                  </div>
                  {canEdit && (
                    <div className="mt-3 grid grid-cols-12 items-center gap-2 border-t border-gray-100 pt-3">
                      <div className="col-span-6">
                        <Input placeholder="Product (e.g. Term Loan)" value={newProduct} onChange={(e) => setNewProduct(e.target.value)} />
                      </div>
                      <div className="col-span-4">
                        <Input type="number" min={1} placeholder="Days" value={newPromise} onChange={(e) => setNewPromise(e.target.value)} />
                      </div>
                      <div className="col-span-2">
                        <Button variant="secondary" size="sm" onClick={addPromise}>Add</Button>
                      </div>
                    </div>
                  )}
                </Card.Body></Card>

                {canEdit && (
                  <div className="flex justify-end">
                    <Button variant="primary" loading={saving} onClick={onSave}>Save configuration</Button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
