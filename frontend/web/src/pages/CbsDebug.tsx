// Admin → CBS / FlexCube debug panel.
//
// Config-admin only (/admin/cbs-debug). Lets an admin confirm the FlexCube
// script API is reachable, see what's configured, and run a live probe
// with a loader + retry on timeout. Also documents the available scripts
// so any admin can understand what data each one returns.

import { useState, useCallback } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useRole } from '@/hooks/useRole';
import { useNavigate } from 'react-router-dom';
import { getJson, AuthExpiredError } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────

interface ScriptDef {
  name:        string;
  params:      Record<string, string>;
  description: string;
}

interface ProbeResult {
  status:        'ok' | 'error' | 'skipped';
  rows_returned: number;
  response_ms:   number | null;
  note?:         string;
  error?:        string | null;
}

interface DebugPayload {
  configured:  boolean;
  url_hint:    string | null;
  timeout_s:   number;
  max_retries: number;
  scripts:     ScriptDef[];
  probe:       ProbeResult | null;
}

// ── API call ──────────────────────────────────────────────────────────────

async function fetchDebugStatus(probe: boolean): Promise<DebugPayload> {
  return getJson<DebugPayload>(`/cbs/debug/flexcube?probe=${probe}`);
}

// ── Helpers ───────────────────────────────────────────────────────────────

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full mr-2"
      style={{ background: ok ? 'var(--lime, #BED600)' : '#e53e3e' }}
    />
  );
}

function msLabel(ms: number | null) {
  if (ms === null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

// ── Main component ────────────────────────────────────────────────────────

export default function CbsDebug() {
  const navigate               = useNavigate();
  const { user, isAdmin }      = useRole();
  const [data,    setData]     = useState<DebugPayload | null>(null);
  const [loading, setLoading]  = useState(false);
  const [error,   setError]    = useState<string | null>(null);
  const [probing, setProbing]  = useState(false);

  // Role gate (UX-side; server enforces require_config_admin)
  const role = (user?.role ?? '').toLowerCase();
  const canAccess = isAdmin || ['admin', 'director', 'chief', 'managing'].some(t => role.includes(t));
  if (!canAccess) {
    return (
      <div className="pg">
        <div className="card p-6 text-center">
          <p className="text-sm" style={{ color: 'var(--danger)' }}>
            Access restricted to system administrators.
          </p>
          <Button variant="ghost" size="sm" className="mt-3" onClick={() => navigate(-1)}>
            Go back
          </Button>
        </div>
      </div>
    );
  }

  const load = useCallback(async (withProbe: boolean) => {
    if (withProbe) setProbing(true);
    else setLoading(true);
    setError(null);
    try {
      const result = await fetchDebugStatus(withProbe);
      setData(result);
    } catch (e) {
      if (e instanceof AuthExpiredError) return;
      setError(e instanceof Error ? e.message : 'Request failed.');
    } finally {
      setLoading(false);
      setProbing(false);
    }
  }, []);

  const probe = data?.probe;
  const probeOk = probe?.status === 'ok';
  const probeErr = probe?.status === 'error';

  return (
    <div className="pg">
      <PageHeader
        title="FlexCube Connection Debug"
        breadcrumbs={[
          { label: 'Reference & Admin' },
          { label: 'CBS Debug' },
        ]}
        subtitle="Verify FlexCube script API connectivity and configuration."
      />

      {/* ── Action row ── */}
      <div className="flex gap-3 mb-5">
        <Button
          variant="secondary"
          onClick={() => load(false)}
          disabled={loading || probing}
        >
          {loading ? 'Loading…' : 'Check config'}
        </Button>
        <Button
          variant="primary"
          onClick={() => load(true)}
          disabled={loading || probing}
        >
          {probing ? (
            <span className="flex items-center gap-2">
              <span className="cbs-probe-spinner" />
              Probing FlexCube…
            </span>
          ) : 'Run live probe'}
        </Button>
        {(data || error) && (
          <Button variant="ghost" onClick={() => { setData(null); setError(null); }}>
            Clear
          </Button>
        )}
      </div>

      {error && (
        <div className="card p-4 mb-4" style={{ borderLeft: '4px solid var(--danger)' }}>
          <p className="text-sm font-semibold" style={{ color: 'var(--danger)' }}>Request failed</p>
          <p className="text-sm mt-1 text-gray-600">{error}</p>
          <Button variant="ghost" size="sm" className="mt-2" onClick={() => load(false)}>
            Retry
          </Button>
        </div>
      )}

      {/* ── Config panel (shown once loaded) ── */}
      {data && (
        <>
          <Card className="mb-4">
            <Card.Header>
              <h2 className="text-sm font-semibold">Configuration</h2>
            </Card.Header>
            <Card.Body>
              <dl className="cbs-dl">
                <div className="cbs-dl-row">
                  <dt>FLEXCUBE_SCRIPTS_URL</dt>
                  <dd>
                    <StatusDot ok={data.configured} />
                    {data.configured
                      ? <><code className="text-xs">{data.url_hint}</code> <span className="text-gray-400 text-xs">(masked)</span></>
                      : <span style={{ color: 'var(--danger)' }}>Not set — add to .env and restart</span>
                    }
                  </dd>
                </div>
                <div className="cbs-dl-row">
                  <dt>FLEXCUBE_TIMEOUT_SECONDS</dt>
                  <dd>{data.timeout_s}s</dd>
                </div>
                <div className="cbs-dl-row">
                  <dt>FLEXCUBE_MAX_RETRIES</dt>
                  <dd>{data.max_retries} attempts</dd>
                </div>
                <div className="cbs-dl-row">
                  <dt>Data source</dt>
                  <dd>
                    {data.configured
                      ? <Badge tone="success">FlexCube live</Badge>
                      : <Badge tone="warning">CSV fallback</Badge>
                    }
                  </dd>
                </div>
              </dl>

              {!data.configured && (
                <div className="cbs-guide-box mt-4">
                  <p className="text-xs font-semibold mb-1">How to activate FlexCube</p>
                  <pre className="cbs-code">{`# Add to /var/www/a2z-blueprint/A2Z-Blueprint/.env
FLEXCUBE_SCRIPTS_URL=http://<host>:<port>/api/scripts/execute
FLEXCUBE_TIMEOUT_SECONDS=15
FLEXCUBE_MAX_RETRIES=3

# Then restart (important — .env is not auto-loaded):
pkill -f "uvicorn utils.api"
cd /var/www/a2z-blueprint/A2Z-Blueprint
source venv/bin/activate
set -a && source .env && set +a
nohup uvicorn utils.api:app --host 0.0.0.0 --port 8502 > /tmp/api.log 2>&1 &`}</pre>
                </div>
              )}
            </Card.Body>
          </Card>

          {/* ── Probe result ── */}
          {probe && (
            <Card className="mb-4">
              <Card.Header>
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  Live probe result
                  {probeOk  && <Badge tone="success">Connected</Badge>}
                  {probeErr && <Badge tone="danger">Failed</Badge>}
                  {probe.status === 'skipped' && <Badge tone="neutral">Skipped</Badge>}
                </h2>
              </Card.Header>
              <Card.Body>
                <dl className="cbs-dl">
                  <div className="cbs-dl-row">
                    <dt>Status</dt>
                    <dd>
                      <StatusDot ok={probeOk} />
                      {probe.status}
                    </dd>
                  </div>
                  <div className="cbs-dl-row">
                    <dt>Response time</dt>
                    <dd className={probe.response_ms && probe.response_ms > 10000 ? 'text-orange-600' : ''}>
                      {msLabel(probe.response_ms)}
                      {probe.response_ms && probe.response_ms > 10000 && (
                        <span className="ml-2 text-xs text-orange-500">
                          Slow — consider increasing FLEXCUBE_TIMEOUT_SECONDS
                        </span>
                      )}
                    </dd>
                  </div>
                  {probeOk && (
                    <div className="cbs-dl-row">
                      <dt>Rows returned</dt>
                      <dd>{probe.rows_returned} {probe.rows_returned === 0 && <span className="text-gray-400 text-xs ml-1">(normal for probe account)</span>}</dd>
                    </div>
                  )}
                  {probe.note && (
                    <div className="cbs-dl-row">
                      <dt>Note</dt>
                      <dd className="text-gray-500 text-xs">{probe.note}</dd>
                    </div>
                  )}
                  {probeErr && (
                    <div className="cbs-dl-row">
                      <dt>Error</dt>
                      <dd style={{ color: 'var(--danger)' }}>{probe.error}</dd>
                    </div>
                  )}
                </dl>

                {probeErr && (
                  <div className="mt-3 flex gap-2">
                    <Button variant="primary" size="sm" onClick={() => load(true)} disabled={probing}>
                      {probing ? 'Retrying…' : 'Retry probe'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => load(false)}>
                      Re-check config only
                    </Button>
                  </div>
                )}

                {probeErr && (
                  <div className="cbs-guide-box mt-4">
                    <p className="text-xs font-semibold mb-1">Common causes</p>
                    <ul className="cbs-guide-list">
                      <li>FlexCube script API server is down or restarting</li>
                      <li>Server cannot reach the host — check firewall / VPN</li>
                      <li>Wrong URL in FLEXCUBE_SCRIPTS_URL (verify host/port)</li>
                      <li>Timeout too short — increase FLEXCUBE_TIMEOUT_SECONDS</li>
                      <li>uvicorn was restarted without re-sourcing .env</li>
                    </ul>
                  </div>
                )}
              </Card.Body>
            </Card>
          )}

          {/* ── Script catalogue ── */}
          <Card className="mb-4">
            <Card.Header>
              <h2 className="text-sm font-semibold">Available FlexCube scripts</h2>
            </Card.Header>
            <Card.Body>
              <div className="overflow-x-auto">
                <table className="data-table w-full text-sm">
                  <thead>
                    <tr>
                      <th>Script name</th>
                      <th>Parameters</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scripts.map((s) => (
                      <tr key={s.name}>
                        <td><code className="text-xs font-mono">{s.name}</code></td>
                        <td>
                          {Object.entries(s.params).map(([k]) => (
                            <code key={k} className="text-xs font-mono mr-1 px-1 py-0.5 bg-gray-100 rounded">{k}</code>
                          ))}
                        </td>
                        <td className="text-gray-600">{s.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="cbs-guide-box mt-4">
                <p className="text-xs font-semibold mb-2">How account lookup flows</p>
                <ol className="cbs-guide-list cbs-guide-list-ordered">
                  <li>User types account number in any CBS lookup input (min 7 chars triggers fetch)</li>
                  <li>Frontend calls <code>GET /api/cbs/accounts/{'{'}{'}'}account_number{'}'}/360</code></li>
                  <li>Backend calls <strong>CUSTOMERACCOUNTDETAILS</strong> → returns account + F7 CIF</li>
                  <li>Backend calls <strong>CUSTOMERACTIVELOANS</strong> using that F7 CIF</li>
                  <li>Combined payload returned: account details + customer flags + active loans</li>
                </ol>
                <p className="text-xs text-gray-500 mt-2">
                  If FlexCube is unreachable the response falls back to the local CSV snapshot.
                  The <code>source</code> field in the API response tells you which path was used
                  (<code>"flexcube"</code> vs <code>"cbs_manager"</code>).
                </p>
              </div>
            </Card.Body>
          </Card>
        </>
      )}

      {/* ── Empty state ── */}
      {!data && !error && !loading && (
        <div className="card p-8 text-center text-gray-400 text-sm">
          Click <strong>Check config</strong> to see the current FlexCube settings,
          or <strong>Run live probe</strong> to test the connection now.
        </div>
      )}
    </div>
  );
}
