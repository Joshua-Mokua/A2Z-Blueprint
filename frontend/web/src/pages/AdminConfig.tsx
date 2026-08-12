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

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { AdminTabs } from '@/components/AdminTabs';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchPipelineConfig,
  updatePipelineConfig,
  upsertMou,
  upsertProductFlow,
  fetchDocumentCatalog,
  addDocumentType,
  fetchCommitteePalette,
  type CommitteeDef,
  getCommitteeTiers,
  saveCommitteeTiers,
  getAdminBranches,
  saveAdminBranches,
  fetchSlaConfig,
  saveSlaConfig,
  type AdminConfigPatch,
  type CommitteeTier,
  type AdminBranch,
  type SlaConfig,
} from '@/lib/api';
import type { PipelineConfig, ProductFlow, DealCategoryConfig } from '@/types/pipeline';

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

const SubTabCtx = createContext<string>('');

const SUBTABS: { id: string; label: string }[] = [
  { id: 'lines',    label: 'Business Lines' },
  { id: 'segments', label: 'Segments' },
  { id: 'catalog',  label: 'Sectors & Categories' },
  { id: 'products', label: 'Products & Flows' },
  { id: 'mou',      label: 'MOU / Partners' },
  { id: 'org',      label: 'Committees & Branches' },
];

function PanelShell({
  title, hint, onSave, saving, children, group,
}: {
  title: string;
  hint?: string;
  onSave?: () => void;
  saving?: boolean;
  children: ReactNode;
  group?: string;
}) {
  const active = useContext(SubTabCtx);
  if (group && active && group !== active) return null;
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
  const [subTab, setSubTab] = useState('lines');

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
  const [dealCategories, setDealCategories] = useState<DealCategoryConfig[]>([]);
  const [clientTypes, setClientTypes] = useState<ClientType[]>([]);
  // Product flows: the authored map + which product is being edited + a draft.
  const [productFlows, setProductFlows] = useState<Record<string, ProductFlow>>({});
  const [flowProduct, setFlowProduct] = useState<string>('');
  const [flowDraft, setFlowDraft] = useState<ProductFlow>({ client_types: [], stages: [] });
  const [docCatalog, setDocCatalog] = useState<string[]>([]);
  const [newDocType, setNewDocType] = useState<string>('');
  const [addingDoc, setAddingDoc] = useState<boolean>(false);
  const [committeePalette, setCommitteePalette] = useState<CommitteeDef[]>([]);
  useEffect(() => {
    fetchCommitteePalette().then((d) => setCommitteePalette(d.committees)).catch(() => setCommitteePalette([]));
  }, []);
  function addJourneyGate(code: string) {
    setFlowDraft((f) => {
      const cur = f.committee_journey ?? [];
      return cur.includes(code) ? f : { ...f, committee_journey: [...cur, code] };
    });
  }
  function removeJourneyGate(idx: number) {
    setFlowDraft((f) => ({ ...f, committee_journey: (f.committee_journey ?? []).filter((_, i) => i !== idx) }));
  }
  function moveJourneyGate(idx: number, dir: -1 | 1) {
    setFlowDraft((f) => {
      const arr = [...(f.committee_journey ?? [])];
      const j = idx + dir;
      if (j < 0 || j >= arr.length) return f;
      [arr[idx], arr[j]] = [arr[j], arr[idx]];
      return { ...f, committee_journey: arr };
    });
  }
  useEffect(() => {
    fetchDocumentCatalog().then(setDocCatalog).catch(() => setDocCatalog([]));
  }, []);
  // WHO ATTACHES (ruling 2026-08-12). A required document used to be a bare
  // name, which silently meant "the deal owner produces this" - including for
  // papers only an analyst can write. These helpers read BOTH shapes, because
  // every existing product is configured as a list of strings and breaking
  // those to add a field would take the pilot down for no gain.
  type DocReq = string | { name: string; attached_by?: string; mandatory?: boolean };
  const docName = (d: DocReq) => (typeof d === 'string' ? d : d.name);
  const docBy = (d: DocReq) => (typeof d === 'string' ? 'owner' : (d.attached_by || 'owner'));
  const docMand = (d: DocReq) => (typeof d === 'string' ? false : Boolean(d.mandatory));

  const ATTACHERS = [
    { key: 'owner', label: 'Deal owner / RM' },
    { key: 'department_analyst', label: 'Department analyst' },
    { key: 'credit_analyst', label: 'Credit analyst' },
    { key: 'credit_admin', label: 'Credit admin' },
    { key: 'customer', label: 'Customer' },
  ];

  function toggleFlowDoc(doc: string) {
    setFlowDraft((f) => {
      const cur = (f.required_documents ?? []) as DocReq[];
      const has = cur.some((d) => docName(d) === doc);
      return {
        ...f,
        required_documents: has
          ? cur.filter((d) => docName(d) !== doc)
          // New documents default to the owner, which is what a bare string
          // always meant - so ticking one behaves exactly as it did before.
          : [...cur, { name: doc, attached_by: 'owner', mandatory: false }],
      } as typeof f;
    });
  }

  function setDocField(doc: string, patch: { attached_by?: string; mandatory?: boolean }) {
    setFlowDraft((f) => ({
      ...f,
      required_documents: ((f.required_documents ?? []) as DocReq[]).map((d) =>
        docName(d) === doc
          ? { name: docName(d), attached_by: patch.attached_by ?? docBy(d),
              mandatory: patch.mandatory ?? docMand(d) }
          : d),
    } as typeof f));
  }
  const [flowBusy, setFlowBusy] = useState(false);
  // SLA config (the single source of truth for product_promise — the overall
  // per-product end-to-end SLA budget). Loaded so the flow editor can show the
  // product's promise against the running sum of its stage target_days and flag
  // over-allocation, and let the admin adjust the promise inline. Writing here
  // saves to the SAME sla_config the SLA page + violation engine use.
  const [slaConfig, setSlaConfig] = useState<SlaConfig | null>(null);
  // Draft budget for the selected product (business days), seeded from
  // product_promise[product]; '' means no promise set (falls back to step sum).
  const [flowBudget, setFlowBudget] = useState<string>('');

  const hydrate = (c: PipelineConfig) => {
    setCfg(c);
    setRequired(c.required_fields ?? []);
    setLabels({ ...(c.segment_labels ?? {}) });
    setCustSeg({ ...(c.customer_segments ?? {}) });
    setProducts({ ...(c.product_catalogue ?? {}) });
    setMous((c.individual_mous ?? []).map((m) => ({ active: true, ...m })));
    setSectors([...(c.business_sectors ?? [])]);
    setDealCategories([...(c.deal_categories ?? [])]);
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
    // SLA config carries product_promise (the overall per-product SLA budget).
    fetchSlaConfig()
      .then((r) => { if (active) setSlaConfig(r.sla_config); })
      .catch(() => { /* non-fatal — flow editor just won't show a budget */ });
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
      if (res.config.deal_categories) setDealCategories([...res.config.deal_categories]);
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
      ? { client_types: [...existing.client_types], stages: existing.stages.map((s) => ({ ...s })), required_documents: [...(existing.required_documents ?? [])], documents_required_at_stage: existing.documents_required_at_stage ?? '', committee_journey: [...(existing.committee_journey ?? [])] }
      : { client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }], required_documents: [], documents_required_at_stage: '', committee_journey: [] });
    // Seed the overall SLA budget from the existing product_promise (if any).
    const promised = slaConfig?.product_promise?.[product];
    setFlowBudget(typeof promised === 'number' && promised > 0 ? String(promised) : '');
  };
  // Running sum of the flow's per-stage target_days, vs the overall SLA budget.
  // Over-allocation = the stages promise more days than the product's end-to-end
  // SLA, which would mean a deal can blow the product promise before it even
  // reaches the last stage. Surfaced live as the admin distributes the days.
  const flowDaysSum = useMemo(
    () => flowDraft.stages.reduce((acc, s) => {
      const t = Number(s.target_days);
      return acc + (Number.isFinite(t) && t > 0 ? t : 0);
    }, 0),
    [flowDraft.stages],
  );
  const flowBudgetNum = useMemo(() => {
    const n = Number(flowBudget);
    return flowBudget.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null;
  }, [flowBudget]);
  const flowOverBudget = flowBudgetNum !== null && flowDaysSum > flowBudgetNum;

  const saveFlow = async () => {
    if (!flowProduct) return;
    const stages = flowDraft.stages
      .map((s) => {
        const wp = s.win_probability;
        const wpNum = wp === null || wp === undefined || String(wp).trim() === ''
          ? null : Number(wp);
        return {
          stage: s.stage.trim(),
          target_days: Number(s.target_days),
          // Only send a win_probability when set to a valid 0–100 number;
          // otherwise omit (the stage simply carries no derived probability).
          ...(wpNum !== null && Number.isFinite(wpNum) && wpNum >= 0 && wpNum <= 100
            ? { win_probability: wpNum } : {}),
        };
      })
      .filter((s) => s.stage && Number.isFinite(s.target_days) && s.target_days > 0);
    if (stages.length === 0) {
      toast({ tone: 'danger', message: 'Add at least one stage with a positive target.' });
      return;
    }
    setFlowBusy(true);
    try {
      await upsertProductFlow({ product: flowProduct, stages, client_types: flowDraft.client_types, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] });
      setProductFlows((p) => ({ ...p, [flowProduct]: { client_types: flowDraft.client_types, stages, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] } }));

      // Persist the overall SLA budget to product_promise (the SAME sla_config
      // the SLA page + violation engine use), so the two stay reconciled. A
      // blank/zero budget removes the promise (product falls back to step-sum).
      if (slaConfig) {
        const budgetNum = flowBudget.trim() === '' ? 0 : Number(flowBudget);
        const promise = { ...(slaConfig.product_promise ?? {}) };
        const had = flowProduct in promise;
        let changed = false;
        if (Number.isFinite(budgetNum) && budgetNum > 0) {
          if (promise[flowProduct] !== budgetNum) { promise[flowProduct] = budgetNum; changed = true; }
        } else if (had) {
          delete promise[flowProduct]; changed = true;
        }
        if (changed) {
          const nextSla = { ...slaConfig, product_promise: promise };
          await saveSlaConfig(nextSla);
          setSlaConfig(nextSla);
        }
      }

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
      setFlowDraft({ client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }] });
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
      <AdminTabs subtitle="Reference data that drives the pipeline and credit factory. Changes apply on the next refresh." />

      <main className="max-w-6xl mx-auto px-6 py-6">
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-500">Loading configuration…</div>
        ) : !cfg ? (
          <div className="py-16 text-center text-sm text-gray-500">Configuration unavailable.</div>
        ) : (
          <>
            <div className="mb-5 flex gap-1 overflow-x-auto border-b border-gray-200">
              {SUBTABS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSubTab(s.id)}
                  className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors ${
                    subTab === s.id
                      ? 'border-[#0082BB] font-medium text-[#0082BB]'
                      : 'border-transparent text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <SubTabCtx.Provider value={subTab}>
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            {/* Client business lines */}
            <PanelShell
              group="lines"
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
              group="lines"
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
              group="catalog"
              title="CBK economic sectors"
              hint="Sector classification offered for business clients."
              onSave={() => save('sectors', { business_sectors: sectors }, 'Sectors')}
              saving={savingKey === 'sectors'}
            >
              <StringListEditor items={sectors} onChange={setSectors} placeholder="Add a sector…" />
            </PanelShell>

            {/* Pipeline categories (A2b) — balance-sheet class the bank tracks */}
            <PanelShell
              group="catalog"
              title="Pipeline categories"
              hint="Balance-sheet classes shown on the create-deal form (Loan/Asset, Deposit/Liability, Insurance). Add a new pipeline class here. Dormant categories are kept but hidden."
              onSave={() => save('deal_categories', { deal_categories: dealCategories }, 'Pipeline categories')}
              saving={savingKey === 'deal_categories'}
            >
              <CategoryEditor categories={dealCategories} onChange={setDealCategories} />
            </PanelShell>

            {/* Segment display names */}
            <PanelShell
              group="segments"
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
              group="segments"
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
              group="products"
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
              group="mou"
              title="Partnership / MOU register"
              hint="Partners offered on consumer deals. Add a partner here and it's selectable immediately."
            >
              <div className="space-y-3">
                {/* Add a partner */}
                <div className="space-y-2">
                  <Input
                    value={newMouName}
                    placeholder="Partner name"
                    onChange={(e) => setNewMouName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') addMou(); }}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      containerClassName="flex-1 min-w-[7rem]"
                      value={newMouType}
                      placeholder="Type (optional)"
                      onChange={(e) => setNewMouType(e.target.value)}
                    />
                    <Input
                      containerClassName="flex-1 min-w-[7rem]"
                      value={newMouDept}
                      placeholder="Department (optional)"
                      onChange={(e) => setNewMouDept(e.target.value)}
                    />
                    <Button size="sm" onClick={addMou} disabled={mouBusy || !newMouName.trim()}>
                      Add partner
                    </Button>
                  </div>
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
              group="products"
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
                  {allProducts.some((p) => productFlows[p]) && (
                    <optgroup label="Products with a custom flow">
                      {allProducts.filter((p) => productFlows[p]).map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="Using their class default">
                    {allProducts.filter((p) => !productFlows[p]).map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </optgroup>
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

                    {/* Overall product SLA budget (product_promise) — the
                        single source of truth used by the SLA module + violation
                        engine. Distribute the per-stage days under this ceiling. */}
                    <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs font-medium text-gray-700">Overall SLA (create → closed)</p>
                          <p className="text-[11px] text-gray-400">
                            Business days. This is the product promise the violation engine references.
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <Input
                            value={flowBudget}
                            type="number"
                            placeholder="—"
                            min={0}
                            className="w-20"
                            onChange={(e) => setFlowBudget(e.target.value)}
                          />
                          <span className="text-xs text-gray-500">bd</span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">
                          Distributed across stages: <span className="font-semibold text-gray-900">{flowDaysSum} bd</span>
                        </span>
                        {flowBudgetNum !== null && (
                          flowOverBudget ? (
                            <Badge tone="danger" size="sm">
                              Over by {flowDaysSum - flowBudgetNum} bd
                            </Badge>
                          ) : (
                            <Badge tone="success" size="sm">
                              {flowBudgetNum - flowDaysSum} bd to spare
                            </Badge>
                          )
                        )}
                      </div>
                      {flowOverBudget && (
                        <p className="text-[11px] text-red-600">
                          The stage days exceed the overall SLA — a deal would breach the product
                          promise before reaching the final stage. Reduce stage targets or raise the SLA.
                        </p>
                      )}
                    </div>

                    {/* Stage sequence with per-stage target_days + win probability */}
                    <div className="space-y-2">
                      <div className="grid grid-cols-[1fr_5rem_5rem_auto] items-center gap-2">
                        <p className="text-xs font-medium text-gray-600">Stage</p>
                        <p className="text-xs font-medium text-gray-600 text-center">Days</p>
                        <p className="text-xs font-medium text-gray-600 text-center">Win&nbsp;%</p>
                        <span />
                      </div>
                      {flowDraft.stages.map((s, i) => (
                        <div key={i} className="grid grid-cols-[1fr_5rem_5rem_auto] items-center gap-2">
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
                            type="number" step="any"
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i ? { ...x, target_days: Number(e.target.value) } : x)),
                            }))}
                          />
                          <Input
                            value={s.win_probability === null || s.win_probability === undefined
                              ? '' : String(s.win_probability)}
                            type="number"
                            placeholder="—"
                            min={0}
                            max={100}
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i
                                ? { ...x, win_probability: e.target.value === '' ? null : Number(e.target.value) }
                                : x)),
                            }))}
                          />
                          <div className="flex items-center gap-0.5">
                            <button
                              type="button"
                              onClick={() => setFlowDraft((d) => ({
                                ...d,
                                stages: [
                                  ...d.stages.slice(0, i),
                                  { stage: '', target_days: 3, win_probability: null },
                                  ...d.stages.slice(i),
                                ],
                              }))}
                              className="px-1 text-sm text-gray-400 hover:text-[#0082BB]"
                              aria-label="Insert a stage above this one"
                              title="Insert a stage above this one"
                            >
                              +↑
                            </button>
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
                        </div>
                      ))}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFlowDraft((d) => ({
                          ...d, stages: [...d.stages, { stage: '', target_days: 3, win_probability: null }],
                        }))}
                      >
                        + Add stage
                      </Button>
                      <p className="text-[11px] text-gray-400">
                        Win&nbsp;% is the likelihood of closing a deal sitting at that stage. A deal
                        inherits its current stage&apos;s value automatically — leave blank for none.
                        Use <span className="font-medium">+↑</span> on a row to insert a stage above it; <span className="font-medium">+ Add stage</span> appends to the end.
                      </p>
                    </div>

                    <div className="space-y-3 pt-1">
                      <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Required documents (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Tick documents this product requires. Choose the stage they must be attached at.</p>
                <div className="mb-2 grid max-h-40 grid-cols-2 gap-x-4 gap-y-1 overflow-auto rounded border p-2">
                  {docCatalog.map((doc) => (
                    <label key={doc} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={((flowDraft.required_documents ?? []) as DocReq[]).some((d) => docName(d) === doc)} onChange={() => toggleFlowDoc(doc)} />
                      {doc}
                    </label>
                  ))}
                </div>
                {/* WHO ATTACHES EACH ONE, and whether it blocks. Two settings per
                    document, shown only for the ones actually ticked - a
                    dropdown beside all sixty catalogue entries would be noise. */}
                {((flowDraft.required_documents ?? []) as DocReq[]).length > 0 && (
                  <div className="mb-3 overflow-hidden rounded border">
                    {/* The name column was 1fr against two fixed columns, so a
                        long document title was cut off mid-word - and these are
                        the names somebody has to recognise to set the attacher
                        correctly. Narrower controls, and the name wraps rather
                        than truncating. */}
                    <div className="grid grid-cols-[1fr_150px_92px] gap-2 border-b bg-gray-50 px-2 py-1 text-[11px] font-medium text-gray-600">
                      <span>Document</span>
                      <span>Attached by</span>
                      <span>Blocks submission</span>
                    </div>
                    {((flowDraft.required_documents ?? []) as DocReq[]).map((d) => (
                      <div key={docName(d)}
                           className="grid grid-cols-[1fr_150px_92px] items-start gap-2 border-b px-2 py-1.5 text-sm last:border-b-0">
                        <span className="break-words text-gray-800" title={docName(d)}>
                          {docName(d)}
                        </span>
                        <select
                          className="h-8 rounded border border-gray-300 px-1 text-xs"
                          value={docBy(d)}
                          onChange={(e) => setDocField(docName(d), { attached_by: e.target.value })}>
                          {ATTACHERS.map((a) => (
                            <option key={a.key} value={a.key}>{a.label}</option>
                          ))}
                        </select>
                        <label className="flex items-center gap-1.5 text-xs text-gray-600">
                          <input type="checkbox" checked={docMand(d)}
                                 onChange={(e) => setDocField(docName(d), { mandatory: e.target.checked })} />
                          mandatory
                        </label>
                      </div>
                    ))}
                    <p className="px-2 py-1.5 text-[11px] text-gray-500">
                      Only <strong>mandatory</strong> documents block submission. Everything
                      else can be submitted pending and attached as the analysis
                      progresses — and a document assigned to an analyst never blocks
                      the deal owner, who has no way of producing it.
                    </p>
                  </div>
                )}

                {/* Admin: introduce a NEW document type into the global master list.
                    Once added it appears above as a tickable checkbox for any product. */}
                <div className="mb-2 flex items-center gap-2">
                  <input
                    type="text"
                    className="flex-1 rounded border px-2 py-1.5 text-sm"
                    placeholder="Add a new document type (e.g. Board Resolution)…"
                    value={newDocType}
                    onChange={(e) => setNewDocType(e.target.value)}
                  />
                  <button
                    type="button"
                    className="rounded border px-3 py-1.5 text-sm text-brand-primary hover:bg-gray-50 disabled:opacity-50"
                    disabled={!newDocType.trim() || addingDoc}
                    onClick={async () => {
                      const nm = newDocType.trim();
                      if (!nm) return;
                      setAddingDoc(true);
                      try {
                        const docs = await addDocumentType(nm);
                        setDocCatalog(docs);
                        setNewDocType('');
                      } catch { /* surfaced via disabled state; keep input */ }
                      finally { setAddingDoc(false); }
                    }}
                  >
                    {addingDoc ? 'Adding…' : 'Add type'}
                  </button>
                </div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Documents required at stage</label>
                <select
                  className="w-full rounded border px-2 py-1.5 text-sm"
                  value={flowDraft.documents_required_at_stage ?? ''}
                  onChange={(e) => setFlowDraft((f) => ({ ...f, documents_required_at_stage: e.target.value }))}
                >
                  <option value="">— none —</option>
                  {flowDraft.stages.filter((s) => s.stage.trim()).map((s) => (
                    <option key={s.stage} value={s.stage}>{s.stage}</option>
                  ))}
                </select>
              </div>
              <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Credit committee journey (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Ordered committee gates this product opens before Credit Analysis. Empty = CR only. Amount-triggered committees are added automatically.</p>
                {(flowDraft.committee_journey ?? []).length === 0 && (
                  <p className="mb-2 text-xs text-gray-400">No committees — CR-only path.</p>
                )}
                <ol className="mb-2 space-y-1">
                  {(flowDraft.committee_journey ?? []).map((code, i) => {
                    const def = committeePalette.find((c) => c.code === code);
                    return (
                      <li key={code} className="flex items-center justify-between rounded border px-2 py-1 text-sm">
                        <span>{i + 1}. {def ? `${def.code} — ${def.name}` : code}</span>
                        <span className="flex gap-1">
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, -1)}>up</button>
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, 1)}>down</button>
                          <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeJourneyGate(i)}>remove</button>
                        </span>
                      </li>
                    );
                  })}
                </ol>
                <div className="flex items-center gap-2">
                  <select id="journeyAdd" className="rounded border px-2 py-1.5 text-sm"
                    onChange={(e) => { if (e.target.value) { addJourneyGate(e.target.value); e.target.value = ''; } }}
                    defaultValue="">
                    <option value="">+ Add committee gate…</option>
                    {committeePalette
                      .filter((c) => !(flowDraft.committee_journey ?? []).includes(c.code))
                      // THE SIXTEEN BRANCH COMMITTEES ARE NOT CHOICES HERE.
                      // A product routes through ONE branch gate and the system
                      // substitutes the deal's own branch at runtime - so
                      // listing all sixteen asks the admin to pick a branch for
                      // a product that serves every branch. Only the
                      // placeholder is offered; the specific ones remain
                      // editable on the committees page.
                      .filter((c) => (c as { kind?: string }).kind !== 'branch')
                      .map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
                  </select>
                </div>
              </div>
                      <div className="flex items-center gap-2">
                        <Button size="sm" onClick={saveFlow} disabled={flowBusy}>
                          Save flow
                        </Button>
                        {productFlows[flowProduct] && (
                          <Button variant="secondary" size="sm" onClick={resetFlowToClass} disabled={flowBusy}>
                            Reset to class flow
                          </Button>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </PanelShell>

            {/* Committee tiers — the multi-tier credit committee ladder. */}
            {subTab === 'org' && (
              <>
                <CommitteeTiersPanel />
                <BranchesPanel />
              </>
            )}
          </div>
            </SubTabCtx.Provider>
          </>
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


// ─── Branches & regions panel (SW-1) ───────────────────────────────────
// Self-contained: loads + saves branches via /api/admin/branches. org_config
// is the single source of truth for branch→region mapping; the server rebuilds
// the in-memory region maps on save so edits are live without a restart.
function BranchesPanel() {
  const { toast } = useToast();
  const [branches, setBranches] = useState<AdminBranch[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState<Record<string, AdminBranch>>({});

  const load = async () => {
    try {
      const r = await getAdminBranches();
      setBranches(r.branches || []);
    } catch {
      toast({ tone: 'danger', message: 'Could not load branches.' });
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const edit = (id: string, patch: Partial<AdminBranch>) => {
    setBranches((prev) => prev.map((b) => (b.id === id ? { ...b, ...patch } : b)));
    setDirty((d) => ({ ...d, [id]: { ...(d[id] || { id }), ...patch, id } as AdminBranch }));
  };

  const save = async () => {
    const edits = Object.values(dirty);
    if (edits.length === 0) { toast({ tone: 'info', message: 'No changes to save.' }); return; }
    setSaving(true);
    try {
      await saveAdminBranches(edits);
      setDirty({});
      toast({ tone: 'success', message: `Saved ${edits.length} branch change(s).` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save branches.' });
    } finally { setSaving(false); }
  };

  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Branches &amp; regions</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Edit a branch's region or area. Saved changes update the live region map immediately.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={loading}>Save</Button>
      </Card.Header>
      <Card.Body className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <div className="hidden md:grid grid-cols-[1fr_1fr_1fr_80px] gap-2 text-xs text-gray-500 px-1">
              <span>Branch</span><span>Region (DSA)</span><span>Area (mainstream)</span><span>Active</span>
            </div>
            {branches.map((b) => (
              <div key={b.id} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_80px] gap-2 items-center">
                <span className="text-sm font-medium text-gray-800">{b.name}</span>
                <Input value={b.region || ''} placeholder="Region"
                  onChange={(e) => edit(b.id!, { region: e.target.value })} disabled={saving} />
                <Input value={b.area_name || ''} placeholder="Area"
                  onChange={(e) => edit(b.id!, { area_name: e.target.value })} disabled={saving} />
                <label className="flex items-center gap-1.5 text-sm text-gray-700">
                  <input type="checkbox" checked={b.active !== false}
                    onChange={(e) => edit(b.id!, { active: e.target.checked })} disabled={saving} />
                </label>
              </div>
            ))}
          </>
        )}
      </Card.Body>
    </Card>
  );
}


// ── A2b: Pipeline category editor ──────────────────────────────────────
const PRODUCT_CLASSES = ['asset', 'liability', 'insurance', 'other'] as const;

function CategoryEditor({
  categories, onChange,
}: {
  categories: DealCategoryConfig[];
  onChange: (next: DealCategoryConfig[]) => void;
}) {
  const [newName, setNewName] = useState('');

  const update = (i: number, patch: Partial<DealCategoryConfig>) => {
    onChange(categories.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  };
  const remove = (i: number) => onChange(categories.filter((_, j) => j !== i));
  const add = () => {
    const name = newName.trim();
    if (!name || categories.some((c) => c.category === name)) return;
    onChange([...categories, {
      category: name, product_class: ['asset'], surface: 'pipeline',
      stages: ['Lead', 'Prospecting', 'Proposal', 'Negotiation', 'Closed Won', 'Closed Lost'],
    }]);
    setNewName('');
  };
  const toggleClass = (i: number, cls: string) => {
    const cur = categories[i].product_class ?? [];
    update(i, { product_class: cur.includes(cls) ? cur.filter((x) => x !== cls) : [...cur, cls] });
  };

  return (
    <div className="space-y-3">
      {categories.map((c, i) => {
        const dormant = (c.surface ?? 'pipeline') === 'dormant';
        return (
          <div key={c.category} className={`rounded border p-3 ${dormant ? 'bg-gray-50 opacity-70' : ''}`}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{c.category}</span>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-gray-600">
                  <input type="checkbox" checked={!dormant}
                    onChange={(e) => update(i, { surface: e.target.checked ? 'pipeline' : 'dormant' })} />
                  Shown on create-deal
                </label>
                <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => remove(i)}>remove</button>
              </div>
            </div>
            <div className="mb-2">
              <span className="mr-2 text-xs text-gray-500">Product classes:</span>
              {PRODUCT_CLASSES.map((cls) => (
                <label key={cls} className="mr-3 inline-flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={(c.product_class ?? []).includes(cls)}
                    onChange={() => toggleClass(i, cls)} />
                  {cls}
                </label>
              ))}
            </div>
            <div>
              <span className="mb-1 block text-xs text-gray-500">Stages (initial flow; a product's own flow overrides):</span>
              <StringListEditor
                items={c.stages ?? []}
                onChange={(items) => update(i, { stages: items })}
                placeholder="Add a stage…"
              />
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-2 pt-2">
        <input
          className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
          placeholder="New pipeline category name (e.g. Trade Finance)…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <Button size="sm" onClick={add} disabled={!newName.trim()}>Add category</Button>
      </div>
    </div>
  );
}
