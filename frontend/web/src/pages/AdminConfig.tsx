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
  type AdminConfigPatch,
} from '@/lib/api';
import type { PipelineConfig } from '@/types/pipeline';

type Mou = { id: string; title: string; partner_name?: string; active?: boolean };

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
  onSave: () => void;
  saving: boolean;
  children: ReactNode;
}) {
  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
        </div>
        <Button variant="primary" size="sm" onClick={onSave} loading={saving}>
          Save
        </Button>
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
  const [sectors, setSectors] = useState<string[]>([]);

  const hydrate = (c: PipelineConfig) => {
    setCfg(c);
    setRequired(c.required_fields ?? []);
    setLabels({ ...(c.segment_labels ?? {}) });
    setCustSeg({ ...(c.customer_segments ?? {}) });
    setProducts({ ...(c.product_catalogue ?? {}) });
    setMous((c.individual_mous ?? []).map((m) => ({ active: true, ...m })));
    setSectors([...(c.business_sectors ?? [])]);
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
      toast({ tone: 'success', message: `${label} saved.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : `Could not save ${label.toLowerCase()}.` });
    } finally {
      setSavingKey(null);
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

            {/* Customer segments per client type */}
            <PanelShell
              title="Customer segment options"
              hint="The segment choices offered on the deal form, per client type."
              onSave={() => save('custseg', { customer_segments: custSeg }, 'Customer segments')}
              saving={savingKey === 'custseg'}
            >
              {Object.keys(custSeg).length === 0 ? (
                <p className="text-sm text-gray-400">No customer segments configured.</p>
              ) : (
                Object.entries(custSeg).map(([type, list]) => (
                  <div key={type}>
                    <div className="mb-1.5 text-sm font-medium text-gray-700">{type}</div>
                    <StringListEditor
                      items={list}
                      onChange={(next) => setCustSeg((p) => ({ ...p, [type]: next }))}
                      placeholder={`Add ${type} segment…`}
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

            {/* MOU register */}
            <PanelShell
              title="Partnership / MOU register"
              hint="Active partnerships offered on individual deals."
              onSave={() =>
                save('mous', { individual_mous: mous.filter((m) => m.id.trim() && m.title.trim()) }, 'MOU register')
              }
              saving={savingKey === 'mous'}
            >
              <div className="space-y-2">
                {mous.map((m, i) => (
                  <div key={`${m.id}-${i}`} className="grid grid-cols-[1fr_2fr_2fr_auto_auto] items-center gap-2">
                    <Input
                      value={m.id}
                      placeholder="ID"
                      onChange={(e) => setMous((p) => p.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))}
                    />
                    <Input
                      value={m.title}
                      placeholder="Title"
                      onChange={(e) => setMous((p) => p.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))}
                    />
                    <Input
                      value={m.partner_name ?? ''}
                      placeholder="Partner"
                      onChange={(e) => setMous((p) => p.map((x, j) => (j === i ? { ...x, partner_name: e.target.value } : x)))}
                    />
                    <label className="flex items-center gap-1 text-xs text-gray-600">
                      <input
                        type="checkbox"
                        checked={m.active !== false}
                        onChange={(e) => setMous((p) => p.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))}
                        className="h-4 w-4 rounded border-gray-300 text-brand-primary"
                      />
                      Active
                    </label>
                    <button
                      type="button"
                      onClick={() => setMous((p) => p.filter((_, j) => j !== i))}
                      className="text-gray-400 hover:text-red-600 px-1"
                      aria-label="Remove MOU"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setMous((p) => [...p, { id: '', title: '', partner_name: '', active: true }])}
                >
                  + Add MOU
                </Button>
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
          </div>
        )}
      </main>
    </div>
  );
}
