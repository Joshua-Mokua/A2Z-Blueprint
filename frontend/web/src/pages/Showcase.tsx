// v10.496 — Showcase / kitchen-sink page.
//
// Renders every component primitive in every state on one page.
// Mounted at /components route — bookmarkable reference for the
// React design system. When v10.497+ developers (Joshua) wonder
// "how does a Button look in danger variant", they open this page.
//
// Also serves as a smoke test: if this page renders without console
// errors, every primitive imports correctly, the brand colors are
// loading from /api/branding, and Tailwind is processing classes.

import { useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Input } from '@/components/Input';
import { Stat } from '@/components/Stat';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { Table, type Column } from '@/components/Table';
import { useToast } from '@/components/Toast';
import { useBranding } from '@/hooks/useBranding';
// Phase P Batch P3a — intelligence-display primitives.
import { RagChip } from '@/components/RagChip';
import { VarianceBadge } from '@/components/VarianceBadge';
import { KpiTile } from '@/components/KpiTile';
import { EmptyState } from '@/components/EmptyState';
import { ConfirmDialog } from '@/components/ConfirmDialog';

interface DemoRow {
  id: number;
  client: string;
  amount: number;
  stage: string;
  tone: 'success' | 'warning' | 'danger' | 'neutral';
}

const DEMO_ROWS: DemoRow[] = [
  { id: 1, client: 'Acme Holdings',  amount: 12_500_000,
    stage: 'Proposal',     tone: 'warning' },
  { id: 2, client: 'Bidco Africa',   amount: 48_300_000,
    stage: 'Credit Review', tone: 'warning' },
  { id: 3, client: 'Brookside Dairy', amount: 5_000_000,
    stage: 'Closed Won',   tone: 'success' },
  { id: 4, client: 'EABL',           amount: 220_000_000,
    stage: 'Approval',     tone: 'success' },
  { id: 5, client: 'KCB Group',      amount: 0,
    stage: 'Closed Lost',  tone: 'danger' },
];

const DEMO_COLUMNS: Column<DemoRow>[] = [
  { key: 'client', header: 'Client' },
  {
    key: 'amount', header: 'Amount', align: 'right',
    render: (r) => r.amount === 0
      ? '—'
      : `KES ${r.amount.toLocaleString()}`,
  },
  {
    key: 'stage', header: 'Stage',
    render: (r) => <Badge tone={r.tone}>{r.stage}</Badge>,
  },
];

function Section({
  title, children,
}: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="text-base font-semibold text-brand-secondary
                     uppercase tracking-wider mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function Showcase() {
  const { branding } = useBranding();
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [tableLoading, setTableLoading] = useState(false);
  // Phase P Batch P3a — ConfirmDialog demo state.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fireDemoToast = (
    tone: 'success' | 'warning' | 'danger' | 'info',
  ) => () => {
    toast({
      tone,
      message: `This is a ${tone} toast — dismisses in 4s.`,
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header — mirrors Dashboard.tsx for consistency */}
      <header className="bg-brand-secondary text-white px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-xs uppercase tracking-widest opacity-70 font-bold">
            {branding?.bank_name ?? 'Loading…'} · Design System
          </div>
          <h1 className="text-xl font-bold mt-1">
            v10.496 Component Showcase
          </h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">

        {/* ── Buttons ────────────────────────────────────── */}
        <Section title="Buttons — variants">
          <div className="flex flex-wrap gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="primary" disabled>Disabled</Button>
            <Button variant="primary" loading>Loading</Button>
          </div>
        </Section>

        <Section title="Buttons — sizes">
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large</Button>
            <Button fullWidth variant="secondary">Full width</Button>
          </div>
        </Section>

        {/* ── Inputs ─────────────────────────────────────── */}
        <Section title="Inputs">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Full name"
              placeholder="e.g. Joshua Mokua"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Input
              label="Email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              helper="We'll never share your address."
            />
            <Input
              label="Amount"
              type="number"
              prefix={branding?.currency_symbol ?? 'KES'}
              suffix=".00"
              placeholder="1,000,000"
            />
            <Input
              label="Invalid example"
              defaultValue="not an email"
              error="Please enter a valid email address"
            />
          </div>
        </Section>

        {/* ── Stat tiles ─────────────────────────────────── */}
        <Section title="Stat tiles — KPI primitives">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Stat label="Total Deposits"
                   value="KES 1.42T"
                   sub="11 branches reporting"
                   delta={2.1} />
            <Stat label="NPL Ratio"
                   value="11.1%"
                   delta={-0.4}
                   invertDelta />
            <Stat label="Active RMs"
                   value={232}
                   sub="Target: 250" />
            <Stat label="Pipeline"
                   value="—"
                   loading />
          </div>
        </Section>

        {/* ── Badges ─────────────────────────────────────── */}
        <Section title="Badges">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>Neutral</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="warning">Warning</Badge>
            <Badge tone="danger">Danger</Badge>
            <Badge tone="info">Info</Badge>
            <Badge tone="brand">Brand</Badge>
            <Badge tone="success" size="sm">Small</Badge>
            <Badge tone="info" shape="rect">Rect</Badge>
          </div>
        </Section>

        {/* ── Toasts ─────────────────────────────────────── */}
        <Section title="Toasts — click to fire">
          <div className="flex flex-wrap gap-3">
            <Button variant="ghost"
                     onClick={fireDemoToast('success')}>
              Fire success toast
            </Button>
            <Button variant="ghost"
                     onClick={fireDemoToast('warning')}>
              Fire warning toast
            </Button>
            <Button variant="ghost"
                     onClick={fireDemoToast('danger')}>
              Fire danger toast
            </Button>
            <Button variant="ghost"
                     onClick={fireDemoToast('info')}>
              Fire info toast
            </Button>
          </div>
        </Section>

        {/* ── Skeletons ──────────────────────────────────── */}
        <Section title="Skeletons">
          <Card>
            <div className="flex items-center gap-3">
              <Skeleton shape="circle" />
              <div className="flex-1 space-y-2">
                <Skeleton shape="line" className="w-1/2" />
                <Skeleton shape="line" className="w-3/4" />
              </div>
            </div>
          </Card>
        </Section>

        {/* ── Cards with composition ─────────────────────── */}
        <Section title="Card — composition">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <Card.Header>
                <span className="font-semibold">Pipeline Activity</span>
                <Badge tone="success">Live</Badge>
              </Card.Header>
              <Card.Body>
                Composed cards combine Header, Body, and Footer
                slots for richer layouts.
              </Card.Body>
              <Card.Footer>
                <Button variant="ghost" size="sm">Refresh</Button>
                <Button variant="primary" size="sm">View All</Button>
              </Card.Footer>
            </Card>
            <Card stripe="accent" title="Yellow stripe">
              <p className="text-sm text-gray-600">
                Cards can also take a simple <code>title</code> prop
                instead of full header composition.
              </p>
            </Card>
          </div>
        </Section>

        {/* ── Table ──────────────────────────────────────── */}
        <Section title="Table">
          <div className="mb-3 flex gap-2">
            <Button variant="ghost" size="sm"
                     onClick={() => setTableLoading((b) => !b)}>
              Toggle loading
            </Button>
          </div>
          <Table
            columns={DEMO_COLUMNS}
            rows={DEMO_ROWS}
            rowKey="id"
            loading={tableLoading}
            onRowClick={(row) => toast({
              tone: 'info',
              message: `Clicked: ${row.client}`,
            })}
          />
        </Section>

        {/* ── P3a: Intelligence-display primitives ───────── */}
        <Section title="RAG Chips (P3a)">
          <div className="flex flex-wrap items-center gap-2">
            <RagChip status="on_track" dot />
            <RagChip status="at_risk" dot />
            <RagChip status="off_track" dot />
            <RagChip status="no_data" dot />
            <RagChip status="at_risk" label="Behind" size="sm" />
          </div>
        </Section>

        <Section title="Variance Badges (P3a)">
          <div className="flex flex-wrap items-center gap-4">
            <VarianceBadge actual={108} target={100} />
            <VarianceBadge actual={92} target={100} />
            <span className="text-xs text-gray-400">NPL (invert):</span>
            <VarianceBadge actual={9.5} target={11} invert />
            <VarianceBadge actual={12.4} target={11} invert />
            <VarianceBadge actual={5} target={0} />
          </div>
        </Section>

        <Section title="KPI Tiles (P3a)">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiTile label="Profit Before Tax" actual="KES 4.2B"
                     target="KES 5.0B" variancePct={-16} status="at_risk" />
            <KpiTile label="Retail Deposit Growth" actual="KES 1.42T"
                     target="KES 1.30T" variancePct={9.2} status="on_track" />
            <KpiTile label="NPL Ratio" actual="9.5%" target="11.0%"
                     variancePct={-13.6} invert status="on_track" />
            <KpiTile label="New Accounts" actual={1820} loading />
          </div>
        </Section>

        <Section title="Empty State (P3a)">
          <Card padding="none">
            <EmptyState
              title="No customers found"
              message="Try a different name, or check the CIF and search again."
              action={
                <Button variant="ghost" size="sm"
                        onClick={() => toast({ tone: 'info', message: 'Reset search' })}>
                  Clear search
                </Button>
              }
            />
          </Card>
        </Section>

        <Section title="Confirm Dialog (P3a)">
          <Button variant="danger" onClick={() => setConfirmOpen(true)}>
            Clear case for disbursement…
          </Button>
          <ConfirmDialog
            open={confirmOpen}
            title="Clear case for disbursement?"
            message="This marks the case ready for the finance system. This action is audited."
            confirmLabel="Disburse"
            tone="danger"
            loading={confirmLoading}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={() => {
              setConfirmLoading(true);
              // Simulate an async mutation for the demo.
              setTimeout(() => {
                setConfirmLoading(false);
                setConfirmOpen(false);
                toast({ tone: 'success', message: 'Case cleared (demo)' });
              }, 900);
            }}
          />
        </Section>

        <footer className="mt-12 text-center text-xs text-gray-400">
          v10.496 Design System · {branding?.app_name} ·{' '}
          Every primitive listed here is available from{' '}
          <code>@/components/*</code>.
        </footer>
      </main>
    </div>
  );
}
