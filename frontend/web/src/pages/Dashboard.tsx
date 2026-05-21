// v10.495 -> v10.496 — MD Cockpit shell, refactored to use design
// system primitives (Stat, Card, Badge). Visual output identical;
// the code is now composed instead of hand-rolled with inline styles.
//
// All bank identity continues to come from useBranding() — no hard-
// coded strings anywhere. Audit gates G381 and G382 both enforce
// this.
//
// Note: this Dashboard is still a SHELL. Real /api/dashboard/md
// integration lands in v10.499.

import { useBranding } from '@/hooks/useBranding';
import { Card } from '@/components/Card';
import { Stat } from '@/components/Stat';
import { Badge } from '@/components/Badge';

export function Dashboard() {
  const { branding, loading } = useBranding();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen
                       text-gray-500">
        Loading…
      </div>
    );
  }

  if (!branding) {
    return (
      <div className="flex items-center justify-center min-h-screen
                       text-red-700">
        Branding unavailable.
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar — uses brand secondary (deep navy) */}
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: branding.brand.secondary }}
      >
        <div className="max-w-7xl mx-auto flex items-center
                         justify-between flex-wrap gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[2.5px]
                             font-bold opacity-70">
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

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* KPI strip — three placeholder Stat tiles. Real values
            arrive in v10.499 once /api/dashboard/md is wired up. */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Stat
            label="Total Deposits"
            value="—"
            sub={`${branding.currency_symbol} (placeholder)`}
          />
          <Stat
            label="NPL Ratio"
            value="—"
            sub="live in v10.499"
          />
          <Stat
            label="Active RMs"
            value="—"
            sub="232 expected"
          />
        </div>

        {/* Status panel — explains what v10.495 / v10.496 are */}
        <Card className="mt-8">
          <Card.Header>
            <h2 className="text-lg font-semibold text-brand-secondary">
              v10.496 — Design System Live
            </h2>
            <Badge tone="success">Active</Badge>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-gray-600 leading-relaxed">
              This page is now composed from the v10.496 design
              system primitives (Stat, Card, Badge). Branding is
              loaded from{' '}
              <code className="bg-gray-100 px-1 rounded text-xs">
                /api/branding
              </code>{' '}
              via your real FastAPI backend. Multi-tenant from day
              1: change{' '}
              <code className="bg-gray-100 px-1 rounded text-xs">
                data/org_config.json
              </code>{' '}
              and this page reflects the new tenant with no code
              change.
            </p>
            <p className="text-sm text-gray-500 mt-3">
              Tour the component library at{' '}
              <a href="/components"
                  className="text-brand-primary hover:underline
                             font-medium">
                /components
              </a>
              .
            </p>
            <p className="text-xs text-gray-400 mt-3">
              Next: v10.497 JWT auth · v10.498 enterprise shell ·
              v10.499 live MD data · v10.500 testing + audit gates
              G383–G385.
            </p>
          </Card.Body>
        </Card>

        {/* IP notice footer — verbatim from /api/branding */}
        <footer className="mt-12 pb-6 text-center text-[11px]
                            text-gray-400 leading-relaxed">
          {branding.ip_notice}
        </footer>
      </main>
    </div>
  );
}
