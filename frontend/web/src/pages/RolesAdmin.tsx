// Role Registry (admin) — Batch C2b-1 frontend.
//
// Lists every role in the registry (kpi_library.json -> role_kpis) with its KPI
// count, resolved pillar mix, and the disbursement capability (toggle, wired to
// pipeline_settings -> disbursement_roles). Clicking a role loads its resolved
// KPI breakdown into a side panel. Reading the hierarchy parent / editing KPI
// weights is deliberately NOT here — those are the guarded C2b-2 pieces.
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { Table, type Column } from '@/components/Table';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchAdminRoles,
  fetchAdminRoleDetail,
  setRoleCapability,
  type AdminRoleRow,
  type AdminRoleDetailResponse,
} from '@/lib/api';

function isConfigAdminRole(role: string | undefined, isAdmin: boolean): boolean {
  if (isAdmin) return true;
  const r = (role ?? '').toLowerCase();
  return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
}

function pillarSummary(pillars: Record<string, number>): string {
  const entries = Object.entries(pillars).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return '—';
  return entries.map(([p, n]) => `${p} ${n}`).join(' · ');
}

export default function RolesAdmin() {
  const navigate = useNavigate();
  const { user, isAdmin } = useRole();
  const { toast } = useToast();
  const canAdmin = useMemo(() => isConfigAdminRole(user?.role, isAdmin), [user, isAdmin]);

  const [rows, setRows] = useState<AdminRoleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingRole, setTogglingRole] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminRoleDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!canAdmin) return;
    fetchAdminRoles()
      .then((res) => setRows(res.roles))
      .catch(() => toast({ tone: 'danger', message: 'Could not load the role registry.' }))
      .finally(() => setLoading(false));
  }, [canAdmin, toast]);

  function openDetail(role: string) {
    setSelected(role);
    setDetail(null);
    setDetailLoading(true);
    fetchAdminRoleDetail(role)
      .then(setDetail)
      .catch(() => toast({ tone: 'danger', message: `Could not load KPIs for ${role}.` }))
      .finally(() => setDetailLoading(false));
  }

  async function toggleDisburse(row: AdminRoleRow) {
    const next = !row.can_disburse;
    setTogglingRole(row.role);
    try {
      await setRoleCapability(row.role, next);
      setRows((prev) =>
        prev.map((r) => (r.role === row.role ? { ...r, can_disburse: next } : r)));
      if (detail && detail.role === row.role) setDetail({ ...detail, can_disburse: next });
      toast({
        tone: 'success',
        message: `${row.role}: disbursement ${next ? 'granted' : 'revoked'}.`,
      });
    } catch (e) {
      toast({
        tone: 'danger',
        message: e instanceof Error ? e.message : 'Could not update capability.',
      });
    } finally {
      setTogglingRole(null);
    }
  }

  const disburseCount = useMemo(() => rows.filter((r) => r.can_disburse).length, [rows]);

  const columns: Column<AdminRoleRow>[] = [
    {
      key: 'role', header: 'Role', sortable: true,
      render: (r) => (
        <button
          onClick={() => openDetail(r.role)}
          className="text-left font-medium text-brand-secondary hover:text-brand-primary hover:underline"
        >
          {r.role}
        </button>
      ),
    },
    {
      key: 'kpi_count', header: 'KPIs', align: 'right', sortable: true,
      render: (r) => <span className="tabular-nums text-gray-700">{r.kpi_count}</span>,
    },
    {
      key: 'pillars', header: 'Pillar mix',
      sortAccessor: (r) => Object.keys(r.pillars).length,
      render: (r) => (
        <span className="text-xs text-gray-500">{pillarSummary(r.pillars)}</span>
      ),
    },
    {
      key: 'can_disburse', header: 'Disbursement', align: 'center',
      sortAccessor: (r) => (r.can_disburse ? 1 : 0),
      render: (r) => (
        <div className="flex items-center justify-center gap-2">
          {r.can_disburse
            ? <Badge tone="success" size="sm">Granted</Badge>
            : <span className="text-xs text-gray-400">—</span>}
          <Button
            variant="ghost" size="sm"
            loading={togglingRole === r.role}
            onClick={() => toggleDisburse(r)}
          >
            {r.can_disburse ? 'Revoke' : 'Grant'}
          </Button>
        </div>
      ),
      exportValue: (r) => (r.can_disburse ? 'granted' : ''),
    },
  ];

  if (!canAdmin) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Role Registry"
          breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Role Registry' }]}
        />
        <main className="max-w-3xl mx-auto px-6 py-10">
          <Card>
            <Card.Body>
              <h2 className="text-base font-semibold text-gray-900">Restricted</h2>
              <p className="mt-1 text-sm text-gray-600">
                The role registry is available to configuration administrators only.
              </p>
              <div className="mt-4">
                <Button variant="secondary" onClick={() => navigate('/')}>Back to dashboard</Button>
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
        title="Role Registry"
        subtitle="Every role, its KPI footprint, and the disbursement capability."
        breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Role Registry' }]}
      />
      <main className="max-w-[1680px] mx-auto px-6 py-6">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_360px] gap-5 items-start">
          <Card>
            <Card.Body>
              <div className="mb-3 flex items-center gap-3 text-sm text-gray-500">
                <span><span className="font-semibold text-gray-900">{rows.length}</span> roles</span>
                <span className="text-gray-300">|</span>
                <span><span className="font-semibold text-gray-900">{disburseCount}</span> with disbursement</span>
              </div>
              <Table
                columns={columns}
                rows={rows}
                rowKey="role"
                loading={loading}
                empty="No roles in the registry."
                searchable
                searchPlaceholder="Search roles…"
                paginated
                pageSize={25}
                exportable
                exportFilename="role-registry.csv"
              />
            </Card.Body>
          </Card>

          <Card className="lg:sticky lg:top-6">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                {selected ?? 'Role detail'}
              </h2>
              {selected && (
                <p className="text-xs text-gray-400 mt-0.5">Resolved KPI footprint</p>
              )}
            </Card.Header>
            <Card.Body>
              {!selected && (
                <p className="text-sm text-gray-400">Select a role to see its KPIs.</p>
              )}
              {selected && detailLoading && (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              {selected && detail && !detailLoading && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm">
                    {detail.can_disburse
                      ? <Badge tone="success" size="sm">Disbursement</Badge>
                      : null}
                    <span className="text-gray-500">
                      {detail.kpi_count} KPIs
                      {detail.unmapped > 0 && (
                        <span className="text-amber-600"> · {detail.unmapped} unmapped</span>
                      )}
                    </span>
                  </div>
                  <ul className="divide-y divide-gray-100">
                    {detail.kpis.map((k, i) => (
                      <li key={`${String(k.ref)}-${i}`} className="py-2">
                        {k.mapped ? (
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-sm text-gray-800 truncate">{k.name ?? String(k.ref)}</div>
                              <div className="text-xs text-gray-400">
                                {k.pillar ?? 'Unmapped'}{k.id ? ` · ${k.id}` : ''}
                              </div>
                            </div>
                            {typeof k.weight === 'number' && (
                              <span className="text-xs tabular-nums text-gray-500 shrink-0">
                                {(k.weight * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-gray-500">{String(k.ref)}</span>
                            <Badge tone="warning" size="sm">unmapped</Badge>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs text-gray-400">
                    KPI weights and reporting line are managed elsewhere; this view is read-only.
                  </p>
                </div>
              )}
            </Card.Body>
          </Card>
        </div>
      </main>
    </div>
  );
}
