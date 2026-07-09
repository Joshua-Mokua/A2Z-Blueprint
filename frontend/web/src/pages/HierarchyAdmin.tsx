import { useEffect, useMemo, useState } from 'react';
import { AdminTabs } from '@/components/AdminTabs';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchHierarchy,
  saveHierarchy,
  type HierarchyResponse,
} from '@/lib/api';

interface HierRow {
  role: string;
  reportsTo: string;
}

export default function HierarchyAdmin() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const canAdmin = useMemo(() => {
    if (isAdmin) return true;
    const r = (user?.role ?? '').toLowerCase();
    return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
  }, [user, isAdmin]);

  const [data, setData] = useState<HierarchyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // edit-reporting-line form
  const [selRole, setSelRole] = useState<string>('');
  const [selParents, setSelParents] = useState<string[]>([]);

  // add-role form
  const [newRole, setNewRole] = useState('');
  const [newParents, setNewParents] = useState<string[]>([]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchHierarchy();
      setData(d);
      if (d.roles.length && !selRole) {
        setSelRole(d.roles[0]);
        setSelParents(d.hierarchy[d.roles[0]] ?? []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load hierarchy');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows: HierRow[] = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.hierarchy)
      .map(([r, parents]) => ({
        role: r,
        reportsTo: parents && parents.length ? parents.join(', ') : '— (top of hierarchy)',
      }))
      .sort((a, b) => a.role.localeCompare(b.role));
  }, [data]);

  const columns: Column<HierRow>[] = [
    { key: 'role', header: 'Role' },
    { key: 'reportsTo', header: 'Reports to' },
  ];

  function onSelectRole(r: string) {
    setSelRole(r);
    setSelParents(data?.hierarchy[r] ?? []);
  }

  function toggleParent(list: string[], setter: (v: string[]) => void, p: string) {
    setter(list.includes(p) ? list.filter((x) => x !== p) : [...list, p]);
  }

  async function saveReportingLine() {
    if (!selRole) return;
    setSaving(true);
    try {
      await saveHierarchy({ action: 'set_parents', role: selRole, parents: selParents });
      toast({ tone: 'success', message: `${selRole} now reports to: ${selParents.join(', ') || 'nobody (top)'}` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' });
    } finally {
      setSaving(false);
    }
  }

  async function addRole() {
    const name = newRole.trim();
    if (!name) return;
    setSaving(true);
    try {
      await saveHierarchy({ action: 'add_role', role: name, parents: newParents });
      toast({ tone: 'success', message: `Added role: ${name}` });
      setNewRole('');
      setNewParents([]);
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Add failed' });
    } finally {
      setSaving(false);
    }
  }

  async function removeRole(r: string) {
    setSaving(true);
    try {
      await saveHierarchy({ action: 'remove_role', role: r });
      toast({ tone: 'success', message: `Removed role: ${r}` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Remove failed' });
    } finally {
      setSaving(false);
    }
  }

  if (!canAdmin) {
    return (
      <Card><Card.Body>
        <div className="text-sm text-gray-600">You do not have access to hierarchy configuration.</div>
      </Card.Body></Card>
    );
  }

  return (
    <div className="space-y-4">
      <AdminTabs subtitle="Configure who reports to whom (role → parent role). Drives the cascade and scope. Changes are live." />

      {error && (
        <Card><Card.Body>
          <div className="text-sm text-red-600">{error}</div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>Retry</Button>
        </Card.Body></Card>
      )}

      <Card><Card.Body>
        <Table columns={columns} rows={rows} rowKey="role" loading={loading} empty="No roles configured." />
      </Card.Body></Card>

      {data && (
        <div className="grid gap-4 md:grid-cols-2">
          {/* Edit a role's reporting line */}
          <Card><Card.Body>
            <h3 className="mb-2 text-sm font-semibold">Edit a role's reporting line</h3>
            <label className="mb-1 block text-xs font-medium text-gray-600">Role to configure</label>
            <select
              className="mb-3 w-full rounded border px-2 py-1.5 text-sm"
              value={selRole}
              onChange={(e) => onSelectRole(e.target.value)}
            >
              {data.roles.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Reports to (tick one or more — a role may have multiple parents, e.g. DSA → Branch Manager + DSA Team Lead)
            </label>
            <div className="mb-3 grid max-h-56 grid-cols-1 gap-1 overflow-auto rounded border p-2">
              {data.roles.filter((r) => r !== selRole).map((r) => (
                <label key={r} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selParents.includes(r)}
                    onChange={() => toggleParent(selParents, setSelParents, r)}
                  />
                  {r}
                </label>
              ))}
            </div>
            <Button onClick={() => void saveReportingLine()} disabled={saving || !selRole}>
              {saving ? 'Saving…' : 'Save reporting line'}
            </Button>
          </Card.Body></Card>

          {/* Add / remove role */}
          <Card><Card.Body>
            <h3 className="mb-2 text-sm font-semibold">Add a role</h3>
            <input
              className="mb-2 w-full rounded border px-2 py-1.5 text-sm"
              placeholder="New role name (e.g. Digital Banking Manager)"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
            />
            <label className="mb-1 block text-xs font-medium text-gray-600">Reports to</label>
            <div className="mb-3 grid max-h-40 grid-cols-1 gap-1 overflow-auto rounded border p-2">
              {data.roles.map((r) => (
                <label key={r} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={newParents.includes(r)}
                    onChange={() => toggleParent(newParents, setNewParents, r)}
                  />
                  {r}
                </label>
              ))}
            </div>
            <Button onClick={() => void addRole()} disabled={saving || !newRole.trim()}>
              {saving ? 'Adding…' : 'Add role'}
            </Button>

            <h3 className="mb-2 mt-5 text-sm font-semibold">Remove a role</h3>
            <p className="mb-2 text-xs text-gray-500">A role with reports under it cannot be removed.</p>
            <div className="grid max-h-40 grid-cols-1 gap-1 overflow-auto rounded border p-2">
              {data.roles.map((r) => (
                <div key={r} className="flex items-center justify-between text-sm">
                  <span>{r}</span>
                  <Button variant="ghost" size="sm" onClick={() => void removeRole(r)} disabled={saving}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          </Card.Body></Card>
        </div>
      )}
    </div>
  );
}
