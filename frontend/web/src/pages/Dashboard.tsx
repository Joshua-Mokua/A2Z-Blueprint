// v10.497 Phase 0 — MD Cockpit shell (shadcn migration).
// ─────────────────────────────────────────────────────────────────
// Visual output identical to v10.496. The bespoke primitives
// (Card, Stat, Badge from @/components/*) have been swapped for
// the shadcn foundation:
//
//   Card        → @/components/ui/card  (Card + CardHeader + CardTitle + CardContent)
//   Stat        → @/components/StatCard (composition over shadcn Card)
//   Badge       → @/components/ui/badge (with tone="success" extension)
//
// Body colors now flow through semantic tokens (bg-background,
// text-muted-foreground, etc.) sourced from index.css → tokens.ts.
// No hardcoded greys (G382 compliant).
//
// All bank identity continues to come from useBranding() — no hard-
// coded strings anywhere. Audit gates G381 + G382 both still enforce.
//
// Note: this Dashboard is still a SHELL. Real /api/dashboard/md
// integration lands in v10.499.

import { useBranding } from '@/hooks/useBranding';
import {
  Card, CardContent, CardHeader, CardTitle,
} from '@/components/ui/card';
import { StatCard } from '@/components/StatCard';
import { Badge } from '@/components/ui/badge';

export function Dashboard() {
  const { branding, loading } = useBranding();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!branding) {
    return (
      <div className="flex items-center justify-center min-h-screen text-destructive">
        Branding unavailable.
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar — uses brand secondary (deep navy) at runtime via
          inline style because branding.brand.secondary is tenant-
          fetched. The Tailwind class bg-brand-secondary would also
          work since tailwind.config.js maps it to --brand-secondary,
          but inline style keeps the source of truth explicit here. */}
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: branding.brand.secondary }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[2.5px] font-bold opacity-70">
              {branding.bank_name}
            </div>
            <h1 className="text-xl font-bold mt-1">
              {branding.app_name} MIS 360 — MD Command Centre
            </h1>
          </div>
          <div className="text-right text-xs opacity-70 leading-relaxed">
            <div>{branding.regulator_full}</div>
            <div>{branding.core_banking_system}</div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* KPI strip — three placeholder StatCard tiles. Real values
            arrive in v10.499 once /api/dashboard/md is wired up. */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <StatCard
            label="Total Deposits"
            value="—"
            sub={`${branding.currency_symbol} (placeholder)`}
          />
          <StatCard
            label="NPL Ratio"
            value="—"
            sub="live in v10.499"
            stripe="warning"
          />
          <StatCard
            label="Active RMs"
            value="—"
            sub="232 expected"
          />
        </div>

        {/* Status panel — explains what v10.497 Phase 0 is */}
        <Card className="mt-8">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-brand-secondary">
                v10.497 Phase 0 — shadcn Foundation Live
              </CardTitle>
              <Badge tone="success">Active</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground leading-relaxed">
              This page now uses the v10.497 shadcn-based design
              system. Primitives live under{' '}
              <code className="bg-muted px-1 rounded text-xs">
                @/components/ui/*
              </code>{' '}
              with banking-grade extensions (Button.loading,
              Badge.tone, StatCard composition).
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed mt-3">
              Branding is loaded from{' '}
              <code className="bg-muted px-1 rounded text-xs">
                /api/branding
              </code>{' '}
              via the FastAPI backend on port 8502. Multi-tenant from
              day 1: change{' '}
              <code className="bg-muted px-1 rounded text-xs">
                data/org_config.json
              </code>{' '}
              and this page reflects the new tenant with no code
              change.
            </p>
            <p className="text-sm text-muted-foreground mt-3">
              Tour the component library at{' '}
              <a href="/components"
                 className="text-brand-primary hover:underline font-medium">
                /components
              </a>.
            </p>
            <p className="text-xs text-muted-foreground/70 mt-3">
              Next: v10.497 Phase 1 backend auth · Phase 2 React auth
              surface · Phase 3 tests + docs · v10.498 enterprise
              shell · v10.499 live MD data.
            </p>
          </CardContent>
        </Card>

        {/* IP notice footer — verbatim from /api/branding */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-muted-foreground/70 leading-relaxed">
          {branding.ip_notice}
        </footer>
      </main>
    </div>
  );
}
