// v10.495 — MD Cockpit shell (placeholder).
//
// First visible React page in the A2Z Blueprint. Uses useBranding()
// to render bank identity from /api/branding — NO hardcoded
// bank-name strings anywhere in this file (audit gate G381
// enforces this for the whole src/ directory).
//
// Three placeholder KPI stat cards establish the visual language
// for v10.499 when this becomes the real MD command center pulling
// live data from /api/dashboard/md.

import { useBranding } from '@/hooks/useBranding';

export function Dashboard() {
  const { branding, loading } = useBranding();

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh', color: '#6b7280',
      }}>
        Loading…
      </div>
    );
  }

  if (!branding) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh', color: '#b91c1c',
      }}>
        Branding unavailable.
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f7fa' }}>
      {/* Top bar — uses brand secondary (deep navy) */}
      <header
        style={{
          background: branding.brand.secondary,
          color: '#ffffff',
          padding: '20px 32px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        <div style={{
          maxWidth: 1280, margin: '0 auto',
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', flexWrap: 'wrap', gap: 16,
        }}>
          <div>
            <div style={{
              fontSize: 11, opacity: 0.7,
              textTransform: 'uppercase', letterSpacing: 2.5,
              fontWeight: 700,
            }}>
              {branding.bank_name}
            </div>
            <h1 style={{
              fontSize: 22, fontWeight: 700, marginTop: 4,
              marginBottom: 0,
            }}>
              {branding.app_name} MIS 360 — MD Command Centre
            </h1>
          </div>
          <div style={{
            textAlign: 'right', fontSize: 12, opacity: 0.7,
          }}>
            <div>{branding.regulator_full}</div>
            <div>{branding.core_banking_system}</div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main style={{
        maxWidth: 1280, margin: '0 auto', padding: '32px',
      }}>
        {/* KPI strip — placeholders, real data in v10.499 */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 24,
        }}>
          {[
            {
              label: 'Total Deposits',
              value: '—',
              sub: `${branding.currency_symbol} (placeholder)`,
            },
            {
              label: 'NPL Ratio',
              value: '—',
              sub: 'live in v10.499',
            },
            {
              label: 'Active RMs',
              value: '—',
              sub: '232 expected',
            },
          ].map((kpi) => (
            <div
              key={kpi.label}
              style={{
                background: '#ffffff',
                borderRadius: 8,
                padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                borderTop: `4px solid ${branding.brand.primary}`,
              }}
            >
              <div style={{
                fontSize: 12, color: '#6b7280',
                textTransform: 'uppercase', letterSpacing: 1,
                fontWeight: 600,
              }}>
                {kpi.label}
              </div>
              <div style={{
                fontSize: 32, fontWeight: 700, marginTop: 8,
                color: branding.brand.secondary,
              }}>
                {kpi.value}
              </div>
              <div style={{
                fontSize: 11, color: '#9ca3af', marginTop: 8,
              }}>
                {kpi.sub}
              </div>
            </div>
          ))}
        </div>

        {/* Status panel — explains what v10.495 is */}
        <div style={{
          marginTop: 32, background: '#ffffff', borderRadius: 8,
          padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        }}>
          <h2 style={{
            fontSize: 18, fontWeight: 600,
            color: branding.brand.secondary, marginTop: 0,
            marginBottom: 8,
          }}>
            v10.495 — React Foundations Live
          </h2>
          <p style={{
            fontSize: 14, color: '#4b5563', lineHeight: 1.6,
            marginTop: 0, marginBottom: 8,
          }}>
            This page is the v10.495 React MD cockpit shell. Branding
            is loaded from{' '}
            <code style={{
              background: '#f3f4f6', padding: '2px 6px',
              borderRadius: 3, fontSize: 13,
            }}>
              /api/branding
            </code>{' '}
            via your real FastAPI backend. Multi-tenant from day 1:
            change{' '}
            <code style={{
              background: '#f3f4f6', padding: '2px 6px',
              borderRadius: 3, fontSize: 13,
            }}>
              data/org_config.json
            </code>{' '}
            and this page reflects the new tenant with no code change.
          </p>
          <p style={{
            fontSize: 13, color: '#6b7280', marginTop: 8, marginBottom: 0,
          }}>
            Next: v10.496 design system · v10.497 JWT auth · v10.498
            enterprise shell · v10.499 live MD data · v10.500 testing
            + audit gates G381–G385.
          </p>
        </div>

        {/* IP notice footer — verbatim from /api/branding,
            which reads it from utils/config.py:_DEFAULT_IP_NOTICE
            (which mirrors pages/_login.py:318 exactly) */}
        <footer style={{
          marginTop: 48, paddingBottom: 24, textAlign: 'center',
          fontSize: 11, color: '#9ca3af', lineHeight: 1.8,
        }}>
          {branding.ip_notice}
        </footer>
      </main>
    </div>
  );
}
