// v10.497 Phase 0 — Showcase / kitchen-sink page.
// ─────────────────────────────────────────────────────────────────
// Renders every shadcn primitive (extended where doctrine warrants)
// in every state on one page. Mounted at /components — bookmarkable
// reference for the React design system.
//
// Migrated from v10.496's bespoke primitives to shadcn/ui foundation:
//   - Button:  shadcn + A2Z `loading` prop
//   - Badge:   shadcn + A2Z semantic `tone` variants
//   - Card:    shadcn CardHeader/CardContent/CardFooter composition
//   - Input:   shadcn Input + Label composition (no built-in label)
//   - Skeleton: shadcn Skeleton with className-driven shapes
//   - Table:   shadcn Table primitives (manual row mapping)
//   - StatCard: A2Z composition over shadcn Card
//   - Toast:   sonner via `toast.success()` / `toast.error()` etc.

import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Card, CardContent, CardFooter, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { StatCard } from '@/components/StatCard';
import { useBranding } from '@/hooks/useBranding';

interface DemoRow {
  id: number;
  client: string;
  amount: number;
  stage: string;
  tone: 'success' | 'warning' | 'danger' | 'neutral';
}

const DEMO_ROWS: DemoRow[] = [
  { id: 1, client: 'Acme Holdings',   amount: 12_500_000,  stage: 'Proposal',     tone: 'warning' },
  { id: 2, client: 'Bidco Africa',    amount: 48_300_000,  stage: 'Credit Review',tone: 'warning' },
  { id: 3, client: 'Brookside Dairy', amount: 5_000_000,   stage: 'Closed Won',   tone: 'success' },
  { id: 4, client: 'EABL',            amount: 220_000_000, stage: 'Approval',     tone: 'success' },
  { id: 5, client: 'KCB Group',       amount: 0,           stage: 'Closed Lost',  tone: 'danger'  },
];

function Section({
  title, children,
}: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="text-base font-semibold text-brand-secondary uppercase tracking-wider mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function Showcase() {
  const { branding } = useBranding();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [tableLoading, setTableLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const fireDemoToast = (
    tone: 'success' | 'warning' | 'error' | 'info',
  ) => () => {
    const msg = `This is a ${tone} toast — dismisses automatically.`;
    if (tone === 'success') toast.success(msg);
    else if (tone === 'warning') toast.warning(msg);
    else if (tone === 'error') toast.error(msg);
    else toast.info(msg);
  };

  // Demo the Button loading state. Releases after 1.2s.
  const simulateSubmit = () => {
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      toast.success('Submitted');
    }, 1200);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-brand-secondary text-white px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-xs uppercase tracking-widest opacity-70 font-bold">
            {branding?.bank_name ?? 'Loading…'} · Design System
          </div>
          <h1 className="text-xl font-bold mt-1">
            v10.497 Component Showcase (shadcn foundation)
          </h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">

        {/* ── Buttons ─────────────────────────────────────────── */}
        <Section title="Buttons — variants">
          <div className="flex flex-wrap gap-3">
            <Button>Primary (default)</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="link">Link</Button>
            <Button disabled>Disabled</Button>
            <Button loading onClick={simulateSubmit}>
              {submitting ? 'Submitting…' : 'Click to submit'}
            </Button>
          </div>
        </Section>

        <Section title="Buttons — sizes">
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm">Small</Button>
            <Button>Default</Button>
            <Button size="lg">Large</Button>
            <Button className="w-full" variant="secondary">
              Full width (via className)
            </Button>
          </div>
        </Section>

        {/* ── Inputs ──────────────────────────────────────────── */}
        <Section title="Inputs (with Label composition)">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full name</Label>
              <Input
                id="name"
                placeholder="e.g. Joshua Mokua"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                We'll never share your address.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="amount">Amount</Label>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {branding?.currency_symbol ?? 'KES'}
                </span>
                <Input id="amount" type="number" placeholder="1,000,000" />
                <span className="text-sm text-muted-foreground">.00</span>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="invalid">Invalid example</Label>
              <Input
                id="invalid"
                defaultValue="not an email"
                aria-invalid="true"
                className="border-destructive focus-visible:ring-destructive"
              />
              <p className="text-xs text-destructive">
                Please enter a valid email address.
              </p>
            </div>
          </div>
        </Section>

        {/* ── StatCard tiles ──────────────────────────────────── */}
        <Section title="StatCard tiles — KPI primitives">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard label="Total Deposits" value="KES 1.42T"
                      sub="11 branches reporting" delta={2.1} />
            <StatCard label="NPL Ratio" value="11.1%"
                      delta={-0.4} invertDelta stripe="warning" />
            <StatCard label="Active RMs" value={232}
                      sub="Target: 250" stripe="success" />
            <StatCard label="Pipeline" value="—" loading stripe="none" />
          </div>
        </Section>

        {/* ── Badges ──────────────────────────────────────────── */}
        <Section title="Badges (tone variants)">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">Neutral</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="warning">Warning</Badge>
            <Badge tone="danger">Danger</Badge>
            <Badge tone="info">Info</Badge>
            <Badge tone="brand">Brand</Badge>
            <Badge>shadcn default</Badge>
            <Badge variant="secondary">shadcn secondary</Badge>
            <Badge variant="destructive">shadcn destructive</Badge>
            <Badge variant="outline">shadcn outline</Badge>
          </div>
        </Section>

        {/* ── Toasts (sonner) ─────────────────────────────────── */}
        <Section title="Toasts — sonner (click to fire)">
          <div className="flex flex-wrap gap-3">
            <Button variant="ghost" onClick={fireDemoToast('success')}>
              Fire success
            </Button>
            <Button variant="ghost" onClick={fireDemoToast('warning')}>
              Fire warning
            </Button>
            <Button variant="ghost" onClick={fireDemoToast('error')}>
              Fire error
            </Button>
            <Button variant="ghost" onClick={fireDemoToast('info')}>
              Fire info
            </Button>
          </div>
        </Section>

        {/* ── Skeletons ───────────────────────────────────────── */}
        <Section title="Skeletons">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Skeleton className="h-12 w-12 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/2" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* ── Cards — composition ─────────────────────────────── */}
        <Section title="Card — composition">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Pipeline Activity</CardTitle>
                  <Badge tone="success">Live</Badge>
                </div>
              </CardHeader>
              <CardContent>
                Composed cards combine CardHeader, CardContent, and
                CardFooter slots for richer layouts.
              </CardContent>
              <CardFooter className="gap-2">
                <Button variant="ghost" size="sm">Refresh</Button>
                <Button size="sm">View all</Button>
              </CardFooter>
            </Card>

            <Card className="relative overflow-hidden before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 before:bg-brand-accent">
              <CardHeader>
                <CardTitle>Yellow stripe</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Cards can also carry a left-edge accent bar via
                  the same `relative + ::before` pattern as StatCard.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        {/* ── Table ───────────────────────────────────────────── */}
        <Section title="Table">
          <div className="mb-3 flex gap-2">
            <Button variant="ghost" size="sm"
                    onClick={() => setTableLoading((b) => !b)}>
              Toggle loading
            </Button>
          </div>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Stage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tableLoading
                  ? Array.from({ length: 5 }).map((_, i) => (
                      <TableRow key={`sk-${i}`}>
                        <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                        <TableCell className="text-right">
                          <Skeleton className="h-4 w-24 ml-auto" />
                        </TableCell>
                        <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      </TableRow>
                    ))
                  : DEMO_ROWS.map((row) => (
                      <TableRow
                        key={row.id}
                        className="cursor-pointer hover:bg-accent"
                        onClick={() => toast.info(`Clicked: ${row.client}`)}
                      >
                        <TableCell className="font-medium">{row.client}</TableCell>
                        <TableCell className="text-right">
                          {row.amount === 0
                            ? '—'
                            : `KES ${row.amount.toLocaleString()}`}
                        </TableCell>
                        <TableCell>
                          <Badge tone={row.tone}>{row.stage}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
          </div>
        </Section>

        <footer className="mt-12 text-center text-xs text-muted-foreground">
          v10.497 Phase 0 · {branding?.app_name ?? 'A2Z'} · Every
          primitive listed here is available from{' '}
          <code>@/components/ui/*</code> (shadcn) or{' '}
          <code>@/components/StatCard</code>.
        </footer>
      </main>
    </div>
  );
}
