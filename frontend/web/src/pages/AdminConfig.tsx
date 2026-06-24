// Admin → Configuration (Batch 1b).
//
// CEO / MD / Director surface for editing pipeline + credit reference config
// that today lives in Streamlit: deal-create required fields, customer segments
// (Ecobank display names + per-type options), the product catalogue, the MOU
// register, and CBK sectors. Each panel reads its slice from /api/pipeline/stages
// and PATCHes via /api/admin/pipeline-config (gated server-side by
// require_config_admin). Currency/FX has its own dedicated page (/fx-rates).
//
// The page is also UX-gated to the executive tier; the server is the real
// authority (a non-exec PATCH returns 403).

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchPipelineConfig,
  updatePipelineConfig,
  upsertMou,
  upsertProductFlow,
  getCommitteeTiers,
  saveCommitteeTiers,
  type AdminConfigPatch,
  type CommitteeTier,
} from '@/lib/api';
import type { PipelineConfig, ProductFlow } from '@/types/pipeline';

type Mou = { id: string; title: string; partner_name?: string; active?: boolean };
type ClientType = { key: string; label: string; field: 'mou' | 'sector' };

// Deal-create fields that can be toggled mandatory. Keys must match what the
// create form + backend _required_fields understand.
const REQUIRABLE_FIELDS: { key: string; label: string }[] = [
  { key: 'client_name', label: 'Client name' },
  { key: 'product_type', label: 'Product type' },
  { key: 'deal_value', label: 'Deal value' },
  { key: 'stage', label: 'Initial stage' },
  { key: 'segment', label: 'Segment' },
  { key: 'currency', label: 'Currency' },
  { key: 'relationship_status', label: 'Relationship status (NTB / Existing)' },
  { key: 'mou_id', label: 'Partnership / MOU' },
  { key: 'sector', label: 'CBK sector (business)' },
];

function isConfigAdminRole(role: string | undefined, isAdmin: boolean): boolean {
  if (isAdmin) return true;
  const r = (role ?? '').toLowerCase();
  return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
}

// ── Small reusable editors ───────────────────────────────────────────────

function StringListEditor({
  items, onChange, placeholder, disabled,
}: {
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (!v || items.includes(v)) { setDraft(''); return; }
    onChange([...items, v]);
    setDraft('');
  };
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {items.map((it) => (
          <span
            key={it}
            className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800"
          >
            {it}
            {!disabled && (
              <button
                type="button"
                onClick={() => onChange(items.filter((x) => x !== it))}
                className="text-gray-400 hover:text-red-600"
                aria-label={`Remove ${it}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
        {items.length === 0 && <span className="text-sm text-gray-400">None yet.</span>}
      </div>
      {!disabled && (
        <div className="mt-2 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
            placeholder={placeholder ?? 'Add…'}
            className="flex-1 px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
          <Button variant="ghost" size="sm" onClick={add}>Add</Button>
        </div>
      )}
    </div>
  );
}

function PanelShell({
  title, hint, onSave, saving, children,
}: {
  title: string;
  hint?: string;
  onSave?: () => void;
  saving?: boolean;
  children: ReactNode;
}) {
  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
        </div>
        {onSave && (
          <Button variant="primary" size="sm" onClick={onSave} loading={saving}>
            Save
          </Button>
        )}
      </Card.Header>
      <Card.Body className="space-y-4">{children}</Card.Body>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function AdminConfig() {
  const navigate = useNavigate();
  const { user, isAdmin } = useRole();
  const { toast } = useToast();

  const allowed = useMemo(
    () => isConfigAdminRole(user?.role, isAdmin),
    [user?.role, isAdmin],
  );

  const [cfg, setCfg] = useState<PipelineConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  // Local drafts
  const [required, setRequired] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [custSeg, setCustSeg] = useState<Record<string, string[]>>({});
  const [products, setProducts] = useState<Record<string, string[]>>({});
  const [mous, setMous] = useState<Mou[]>([]);
  // MOU register: add-a-partner form + search filter over the (long) list.
  const [newMouName, setNewMouName] = useState('');
  const [newMouType, setNewMouType] = useState('');
  const [newMouDept, setNewMouDept] = useState('');
  const [mouSearch, setMouSearch] = useState('');
  const [mouBusy, setMouBusy] = useState(false);
  const [sectors, setSectors] = useState<string[]>([]);
  const [clientTypes, setClientTypes] = useState<ClientType[]>([]);
  // Product flows: the authored map + which product is being edited + a draft.
  const [productFlows, setProductFlows] = useState<Record<string, ProductFlow>>({});
  const [flowProduct, setFlowProduct] = useState<string>('');
  const [flowDraft, setFlowDraft] = useState<ProductFlow>({ client_types: [], stages: [] });
  const [flowBusy, setFlowBusy] = useState(false);

  const hydrate = (c: PipelineConfig) => {
    setCfg(c);
    setRequired(c.required_fields ?? []);
    setLabels({ ...(c.segment_labels ?? {}) });
    setCustSeg({ ...(c.customer_segments ?? {}) });
    setProducts({ ...(c.product_catalogue ?? {}) });
    setMous((c.individual_mous ?? []).map((m) => ({ active: true, ...m })));
    setSectors([...(c.business_sectors ?? [])]);
    setClientTypes((c.client_types ?? []).map((t) => ({ ...t })));
    setProductFlows({ ...(c.product_flows ?? {}) });
  };

  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) hydrate(c); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load configuration.' }))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed]);

  const save = async (key: string, patch: AdminConfigPatch, label: string) => {
    setSavingKey(key);
    try {
      const res = await updatePipelineConfig(patch);
      // Re-hydrate from the authoritative effective config the server returns.
      setCfg((prev) => (prev ? { ...prev, ...res.config } : prev));
      if (res.config.required_fields) setRequired(res.config.required_fields);
      if (res.config.segment_labels) setLabels({ ...res.config.segment_labels });
      if (res.config.customer_segments) setCustSeg({ ...res.config.customer_segments });
      if (res.config.product_catalogue) setProducts({ ...res.config.product_catalogue });
      if (res.config.individual_mous) setMous(res.config.individual_mous.map((m) => ({ active: true, ...m })));
      if (res.config.business_sectors) setSectors([...res.config.business_sectors]);
      if (res.config.client_types) setClientTypes(res.config.client_types.map((t) => ({ ...t })));
      toast({ tone: 'success', message: `${label} saved.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : `Could not save ${label.toLowerCase()}.` });
    } finally {
      setSavingKey(null);
    }
  };

  // MOU register writes go to the dedicated /admin/mous endpoint (partnerships_
  // mous.json), NOT pipeline-config — so a newly added partner is immediately
  // selectable on a deal. Add takes a name (+ optional type/dept); the backend
  // mints the id and defaults the rest.
  const addMou = async () => {
    const name = newMouName.trim();
    if (!name) return;
    setMouBusy(true);
    try {
      const res = await upsertMou({
        partner_name: name,
        mou_type: newMouType.trim() || undefined,
        department: newMouDept.trim() || undefined,
      });
      setMous((p) => [...p, { id: res.mou.id, title: res.mou.title, partner_name: res.mou.partner_name, active: true }]);
      setNewMouName('');
      setNewMouType('');
      setNewMouDept('');
      toast({ tone: 'success', message: `Added ${res.mou.partner_name}.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not add the MOU partner.' });
    } finally {
      setMouBusy(false);
    }
  };

  const setMouActive = async (id: string, active: boolean) => {
    setMouBusy(true);
    try {
      await upsertMou({ id, status: active ? 'Active' : 'Inactive' });
      setMous((p) => p.map((m) => (m.id === id ? { ...m, active } : m)));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not update the MOU.' });
    } finally {
      setMouBusy(false);
    }
  };

  const visibleMous = useMemo(() => {
    const q = mouSearch.trim().toLowerCase();
    if (!q) return mous;
    return mous.filter((m) =>
      (m.title ?? '').toLowerCase().includes(q) ||
      (m.partner_name ?? '').toLowerCase().includes(q) ||
      (m.id ?? '').toLowerCase().includes(q));
  }, [mous, mouSearch]);

  // ── Product flows ──
  // All catalogued products, flattened, for the picker.
  const allProducts = useMemo(
    () => Array.from(new Set(Object.values(products).flat())).sort(),
    [products],
  );
  // When a product is selected, load its authored flow into the draft (or a
  // single empty stage if it has none yet).
  const selectFlowProduct = (product: string) => {
    setFlowProduct(product);
    const existing = productFlows[product];
    setFlowDraft(existing
      ? { client_types: [...existing.client_types], stages: existing.stages.map((s) => ({ ...s })) }
      : { client_types: [], stages: [{ stage: '', target_days: 3 }] });
  };
  const saveFlow = async () => {
    if (!flowProduct) return;
    const stages = flowDraft.stages
      .map((s) => ({ stage: s.stage.trim(), target_days: Number(s.target_days) }))
      .filter((s) => s.stage && Number.isFinite(s.target_days) && s.target_days > 0);
    if (stages.length === 0) {
      toast({ tone: 'danger', message: 'Add at least one stage with a positive target.' });
      return;
    }
    setFlowBusy(true);
    try {
      await upsertProductFlow({ product: flowProduct, stages, client_types: flowDraft.client_types });
      setProductFlows((p) => ({ ...p, [flowProduct]: { client_types: flowDraft.client_types, stages } }));
      toast({ tone: 'success', message: `${flowProduct} flow saved.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save the flow.' });
    } finally {
      setFlowBusy(false);
    }
  };
  const resetFlowToClass = async () => {
    if (!flowProduct) return;
    setFlowBusy(true);
    try {
      await upsertProductFlow({ product: flowProduct, delete: true });
      setProductFlows((p) => { const n = { ...p }; delete n[flowProduct]; return n; });
      setFlowDraft({ client_types: [], stages: [{ stage: '', target_days: 3 }] });
      toast({ tone: 'success', message: `${flowProduct} reverted to its class flow.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not reset the flow.' });
    } finally {
      setFlowBusy(false);
    }
  };

  if (!allowed) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Configuration"
          breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Configuration' }]}
        />
        <main className="max-w-3xl mx-auto px-6 py-10">
          <Card stripe="accent">
            <Card.Body>
              <h2 className="text-base font-semibold text-gray-900">Restricted</h2>
              <p className="mt-1 text-sm text-gray-600">
                Reference configuration can only be viewed and edited by the CEO, MD,
                or a Director. If you believe you should have access, contact your administrator.
              </p>
              <div className="mt-4">
                <Button variant="ghost" size="sm" onClick={() => navigate('/')}>← Back to dashboard</Button>
              </div>
            </Card.Body>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Configuration"
        breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Configuration' }]}
        subtitle="Reference data that drives the pipeline and credit factory. Changes apply on the next refresh."
      />

      <main className="max-w-6xl mx-auto px-6 py-6">
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-500">Loading configuration…</div>
        ) : !cfg ? (
          <div className="py-16 text-center text-sm text-gray-500">Configuration unavailable.</div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            {/* Client business lines */}
            <PanelShell
              title="Client business lines"
              hint="Consumer / Commercial / CIB. 'Field' picks the third selector: MOU (consumer) or CBK sector (business)."
              onSave={() =>
                save('clientTypes',
                  { client_types: clientTypes.filter((t) => t.key.trim() && t.label.trim()) },
                  'Client business lines')
              }
              saving={savingKey === 'clientTypes'}
            >
              <div className="space-y-2">
                {clientTypes.map((t, i) => (
                  <div key={`${t.key}-${i}`} className="grid grid-cols-[1.2fr_1.6fr_1fr_auto] items-center gap-2">
                    <Input
                      value={t.key}
                      placeholder="Key (stored)"
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}
                    />
                    <Input
                      value={t.label}
                      placeholder="Display label"
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                    />
                    <select
                      value={t.field}
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, field: e.target.value as 'mou' | 'sector' } : x)))}
                      className="h-10 px-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                    >
                      <option value="mou">MOU</option>
                      <option value="sector">Sector</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => setClientTypes((p) => p.filter((_, j) => j !== i))}
                      className="text-gray-400 hover:text-red-600 px-1"
                      aria-label="Remove client type"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setClientTypes((p) => [...p, { key: '', label: '', field: 'sector' }])}
                >
                  + Add business line
                </Button>
              </div>
            </PanelShell>

            {/* Required fields */}
            <PanelShell
              title="Required fields"
              hint="Which inputs a new deal must have before it can be created."
              onSave={() => save('required', { required_fields: required }, 'Required fields')}
              saving={savingKey === 'required'}
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {REQUIRABLE_FIELDS.map((f) => {
                  const on = required.includes(f.key);
                  return (
                    <label key={f.key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() =>
                          setRequired((prev) =>
                            on ? prev.filter((k) => k !== f.key) : [...prev, f.key],
                          )
                        }
                        className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary/30"
                      />
                      {f.label}
                    </label>
                  );
                })}
              </div>
            </PanelShell>

            {/* Sectors */}
            <PanelShell
              title="CBK economic sectors"
              hint="Sector classification offered for business clients."
              onSave={() => save('sectors', { business_sectors: sectors }, 'Sectors')}
              saving={savingKey === 'sectors'}
            >
              <StringListEditor items={sectors} onChange={setSectors} placeholder="Add a sector…" />
            </PanelShell>

            {/* Segment display names */}
            <PanelShell
              title="Segment display names"
              hint="Map internal segment buckets to the bank's own names (e.g. Affluent → Premier)."
              onSave={() => save('labels', { segment_labels: labels }, 'Segment names')}
              saving={savingKey === 'labels'}
            >
              {Object.keys(labels).length === 0 ? (
                <p className="text-sm text-gray-400">No segment labels configured.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(labels).map(([base, display]) => (
                    <div key={base} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                      <span className="text-sm text-gray-500 truncate">{base}</span>
                      <span className="text-gray-300">→</span>
                      <Input
                        value={display}
                        onChange={(e) => setLabels((p) => ({ ...p, [base]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              )}
            </PanelShell>

            {/* Customer segments per client business line */}
            <PanelShell
              title="Customer segment options"
              hint="The segment choices offered on the deal form, per business line."
              onSave={() => {
                // Save ONLY the segment lists for the configured business lines —
                // this drops any orphaned keys (e.g. legacy Individual/Business).
                const cleaned: Record<string, string[]> = {};
                clientTypes.forEach((t) => { cleaned[t.key] = custSeg[t.key] ?? []; });
                save('custseg', { customer_segments: cleaned }, 'Customer segments');
              }}
              saving={savingKey === 'custseg'}
            >
              {clientTypes.length === 0 ? (
                <p className="text-sm text-gray-400">Define client business lines first.</p>
              ) : (
                clientTypes.map((t) => (
                  <div key={t.key}>
                    <div className="mb-1.5 text-sm font-medium text-gray-700">{t.label}</div>
                    <StringListEditor
                      items={custSeg[t.key] ?? []}
                      onChange={(next) => setCustSeg((p) => ({ ...p, [t.key]: next }))}
                      placeholder={`Add ${t.label} segment…`}
                    />
                  </div>
                ))
              )}
            </PanelShell>

            {/* Product catalogue */}
            <PanelShell
              title="Product catalogue"
              hint="Products offered, grouped by class. Class drives the pipeline buckets."
              onSave={() => save('products', { product_catalogue: products }, 'Product catalogue')}
              saving={savingKey === 'products'}
            >
              {Object.keys(products).length === 0 ? (
                <p className="text-sm text-gray-400">No products configured.</p>
              ) : (
                Object.entries(products).map(([cls, list]) => (
                  <div key={cls}>
                    <div className="mb-1.5 text-sm font-medium text-gray-700">{cls}</div>
                    <StringListEditor
                      items={list}
                      onChange={(next) => setProducts((p) => ({ ...p, [cls]: next }))}
                      placeholder={`Add ${cls} product…`}
                    />
                  </div>
                ))
              )}
            </PanelShell>

            {/* MOU register — writes go to the dedicated endpoint, so additions
                are immediately selectable on consumer deals. */}
            <PanelShell
              title="Partnership / MOU register"
              hint="Partners offered on consumer deals. Add a partner here and it's selectable immediately."
            >
              <div className="space-y-3">
                {/* Add a partner */}
                <div className="grid grid-cols-[2fr_1.3fr_1.3fr_auto] items-center gap-2">
                  <Input
                    value={newMouName}
                    placeholder="Partner name"
                    onChange={(e) => setNewMouName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') addMou(); }}
                  />
                  <Input
                    value={newMouType}
                    placeholder="Type (optional)"
                    onChange={(e) => setNewMouType(e.target.value)}
                  />
                  <Input
                    value={newMouDept}
                    placeholder="Department (optional)"
                    onChange={(e) => setNewMouDept(e.target.value)}
                  />
                  <Button size="sm" onClick={addMou} disabled={mouBusy || !newMouName.trim()}>
                    Add partner
                  </Button>
                </div>

                {/* Search the register */}
                <Input
                  value={mouSearch}
                  placeholder={`Search ${mous.length} partners…`}
                  onChange={(e) => setMouSearch(e.target.value)}
                />

                {/* List (read-only id/title; toggle Active to deactivate) */}
                <div className="max-h-72 overflow-y-auto rounded-md border border-gray-200 divide-y divide-gray-100">
                  {visibleMous.length === 0 ? (
                    <p className="px-3 py-4 text-sm text-gray-500">No partners match “{mouSearch}”.</p>
                  ) : (
                    visibleMous.map((m) => (
                      <div key={m.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                        <span className="font-mono text-xs text-gray-400 w-20 shrink-0">{m.id}</span>
                        <span className="flex-1 text-gray-900">{m.title}</span>
                        <label className="flex items-center gap-1 text-xs text-gray-600 shrink-0">
                          <input
                            type="checkbox"
                            checked={m.active !== false}
                            disabled={mouBusy}
                            onChange={(e) => setMouActive(m.id, e.target.checked)}
                            className="h-4 w-4 rounded border-gray-300 text-brand-primary"
                          />
                          Active
                        </label>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </PanelShell>

            {/* Product flows — per-product stage sequence + per-stage SLA */}
            <PanelShell
              title="Product flows"
              hint="Each product can have its own stage sequence and per-stage target days. Pick a product to customise its flow; unset products follow their class flow."
            >
              <div className="space-y-3">
                <select
                  value={flowProduct}
                  onChange={(e) => selectFlowProduct(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                >
                  <option value="">Select a product to edit its flow…</option>
                  {allProducts.map((p) => (
                    <option key={p} value={p}>
                      {p}{productFlows[p] ? '  • customised' : ''}
                    </option>
                  ))}
                </select>

                {flowProduct && (
                  <>
                    {/* Client types that offer this product */}
                    <div>
                      <p className="text-xs font-medium text-gray-600 mb-1">Offered to</p>
                      <div className="flex flex-wrap gap-2">
                        {clientTypes.map((ct) => {
                          const on = flowDraft.client_types.includes(ct.key);
                          return (
                            <button
                              key={ct.key}
                              type="button"
                              onClick={() => setFlowDraft((d) => ({
                                ...d,
                                client_types: on
                                  ? d.client_types.filter((k) => k !== ct.key)
                                  : [...d.client_types, ct.key],
                              }))}
                              className={`px-2.5 py-1 rounded-full text-xs border ${on
                                ? 'bg-brand-primary/10 border-brand-primary text-brand-primary'
                                : 'bg-white border-gray-300 text-gray-600'}`}
                            >
                              {ct.label}
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-gray-400 mt-1">
                        {flowDraft.client_types.length === 0
                          ? 'No selection = offered to all client types.'
                          : 'Offered only to the selected client types.'}
                      </p>
                    </div>

                    {/* Stage sequence with per-stage target_days */}
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-gray-600">Stages &amp; targets (days)</p>
                      {flowDraft.stages.map((s, i) => (
                        <div key={i} className="grid grid-cols-[1fr_5rem_auto] items-center gap-2">
                          <Input
                            value={s.stage}
                            placeholder={`Stage ${i + 1}`}
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i ? { ...x, stage: e.target.value } : x)),
                            }))}
                          />
                          <Input
                            value={String(s.target_days)}
                            type="number"
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i ? { ...x, target_days: Number(e.target.value) } : x)),
                            }))}
                          />
                          <button
                            type="button"
                            onClick={() => setFlowDraft((d) => ({
                              ...d, stages: d.stages.filter((_, j) => j !== i),
                            }))}
                            className="text-gray-400 hover:text-red-600 px-1"
                            aria-label="Remove stage"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFlowDraft((d) => ({
                          ...d, stages: [...d.stages, { stage: '', target_days: 3 }],
                        }))}
                      >
                        + Add stage
                      </Button>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <Button size="sm" onClick={saveFlow} disabled={flowBusy}>
                        Save flow
                      </Button>
                      {productFlows[flowProduct] && (
                        <Button variant="secondary" size="sm" onClick={resetFlowToClass} disabled={flowBusy}>
                          Reset to class flow
                        </Button>
                      )}
                    </div>
                  </>
                )}
              </div>
            </PanelShell>

            {/* Currency pointer */}
            <Card>
              <Card.Header>
                <h2 className="text-base font-semibold text-gray-900">Currency &amp; FX rates</h2>
              </Card.Header>
              <Card.Body>
                <p className="text-sm text-gray-600">
                  Exchange rates and currency books are managed on their own page.
                </p>
                <div className="mt-3">
                  <Button variant="secondary" size="sm" onClick={() => navigate('/fx-rates')}>
                    Open FX Rates →
                  </Button>
                </div>
              </Card.Body>
            </Card>

            {/* Committee tiers — the multi-tier credit committee ladder. */}
            <CommitteeTiersPanel />
          </div>
        )}
      </main>
    </div>
  );
}


// ─── Committee tiers panel ─────────────────────────────────────────────
// Self-contained: loads + saves the multi-tier credit committee ladder via
// the dedicated /api/lms/committee/tiers endpoint, independent of the main
// pipeline config flow. Lets the business rename tiers, set authority limits,
// and control which tiers permit direct entry (CIB leeway).
function CommitteeTiersPanel() {
  const { toast } = useToast();
  const [tiers, setTiers] = useState<CommitteeTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    getCommitteeTiers()
      .then((r) => { if (live) setTiers(r.tiers || []); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load committee tiers.' }))
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [toast]);

  const update = (i: number, patch: Partial<CommitteeTier>) =>
    setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));

  const addTier = () => {
    const nextNum = tiers.length ? Math.max(...tiers.map((t) => t.tier)) + 1 : 1;
    setTiers((prev) => [...prev, {
      tier: nextNum, key: `tier_${nextNum}`, name: '',
      authority_limit_kes: null, can_be_entry: true,
    }]);
  };
  const removeTier = (i: number) => setTiers((prev) => prev.filter((_, idx) => idx !== i));

  const save = async () => {
    setSaving(true);
    try {
      const r = await saveCommitteeTiers(tiers);
      setTiers(r.tiers || []);
      toast({ tone: 'success', message: 'Committee tiers saved.' });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save tiers.' });
    } finally { setSaving(false); }
  };

  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Credit committee tiers</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            The ordered committee ladder. A case enters at a tier and the committee submits it
            upward as needed. Limits inform routing; entry-permitted tiers can be skipped to.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={loading}>
          Save
        </Button>
      </Card.Header>
      <Card.Body className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <div className="hidden md:grid grid-cols-[60px_1fr_1.2fr_110px_auto] gap-2 text-xs text-gray-500 px-1">
              <span>Tier</span><span>Name</span><span>Authority limit (KES)</span><span>Entry?</span><span></span>
            </div>
            {tiers.map((t, i) => (
              <div key={i} className="grid grid-cols-1 md:grid-cols-[60px_1fr_1.2fr_110px_auto] gap-2 items-center">
                <Input value={String(t.tier)} onChange={(e) => update(i, { tier: Number(e.target.value) || t.tier })} disabled={saving} />
                <Input value={t.name} placeholder="Tier name" onChange={(e) => update(i, { name: e.target.value })} disabled={saving} />
                <Input
                  value={t.authority_limit_kes == null ? '' : String(t.authority_limit_kes)}
                  placeholder="No ceiling"
                  onChange={(e) => update(i, { authority_limit_kes: e.target.value === '' ? null : Number(e.target.value) })}
                  disabled={saving}
                />
                <label className="flex items-center gap-1.5 text-sm text-gray-700">
                  <input type="checkbox" checked={t.can_be_entry}
                    onChange={(e) => update(i, { can_be_entry: e.target.checked })} disabled={saving} />
                  Entry
                </label>
                <Button variant="ghost" size="sm" onClick={() => removeTier(i)} disabled={saving}>Remove</Button>
              </div>
            ))}
            <Button variant="secondary" size="sm" onClick={addTier} disabled={saving}>Add tier</Button>
          </>
        )}
      </Card.Body>
    </Card>
  );
}
