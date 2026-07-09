// Staff Administration (admin) — Postgres users-table CRUD.
//
// Lists the authoritative staff roster from the PostgreSQL `users` table
// (~1,438 staff) via GET /api/admin/staff — NOT the legacy users.json shadow.
// Supports create / edit / deactivate / reactivate against the matching
// write endpoints. Reporting-line (who-reports-to-whom) editing is a separate,
// later surface — deliberately not here.
//
// NOTE: accounts created here live in PostgreSQL. Until the login path is
// migrated off users.json, a newly-created account cannot authenticate yet;
// existing logins are unaffected.
import { useEffect, useMemo, useState } from 'react';
import { AdminTabs } from '@/components/AdminTabs';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { Input } from '@/components/Input';
import { Table, type Column } from '@/components/Table';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchAdminStaff,
  createAdminStaff,
  updateAdminStaff,
  deactivateAdminStaff,
  reactivateAdminStaff,
  fetchAccessModules,
  type AccessModule,
  previewStaffUpload,
  applyStaffUpload,
  type StaffUploadPreview,
  type StaffRow,
  type StaffCreateInput,
  type StaffPatchInput,
} from '@/lib/api';

function isConfigAdminRole(role: string | undefined, isAdmin: boolean): boolean {
  if (isAdmin) return true;
  const r = (role ?? '').toLowerCase();
  return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
}

type ModalMode = 'create' | 'edit' | null;

interface FormState {
  username: string;
  staff_code: string;
  password: string;
  full_name: string;
  email: string;
  role: string;
  department: string;
  unit: string;
  can_view_all: boolean;
  is_admin: boolean;
  accessible_modules: string[];
}

const EMPTY_FORM: FormState = {
  username: '', staff_code: '', password: '', full_name: '', email: '',
  role: 'Staff', department: '', unit: '', can_view_all: false, is_admin: false, accessible_modules: [],
};

export default function StaffAdmin() {
  const { user, isAdmin } = useRole();
  const { toast } = useToast();
  const canAdmin = useMemo(() => isConfigAdminRole(user?.role, isAdmin), [user, isAdmin]);

  const [rows, setRows] = useState<StaffRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [modal, setModal] = useState<ModalMode>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [allModules, setAllModules] = useState<AccessModule[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadB64, setUploadB64] = useState<string | null>(null);
  const [uploadName, setUploadName] = useState<string>('');
  const [uploadPreview, setUploadPreview] = useState<StaffUploadPreview | null>(null);

  function pickStaffFile() {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.xlsx';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setUploadName(f.name);
      const buf = await f.arrayBuffer();
      let bin = '';
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      const b64 = btoa(bin);
      setUploadB64(b64); setUploadBusy(true); setUploadOpen(true); setUploadPreview(null);
      try {
        const p = await previewStaffUpload(b64);
        setUploadPreview(p);
      } catch (e) {
        setUploadPreview({ ok: false, errors: [String((e as Error)?.message || e)], summary: null });
      } finally { setUploadBusy(false); }
    };
    inp.click();
  }

  async function confirmStaffUpload() {
    if (!uploadB64) return;
    setUploadBusy(true);
    try {
      const r = await applyStaffUpload(uploadB64, ['william001', 'admin']);
      toast({ tone: 'success', message: `Uploaded ${r.applied} staff (was ${r.before}, now ${r.after}).` });
      setUploadOpen(false); setUploadB64(null); setUploadPreview(null);
      void load();
    } catch (e) {
      toast({ tone: 'danger', message: `Upload failed: ${String((e as Error)?.message || e)}` });
    } finally { setUploadBusy(false); }
  }
  useEffect(() => {
    fetchAccessModules().then(setAllModules).catch(() => setAllModules([]));
  }, []);
  function toggleModule(key: string) {
    setForm((f) => ({
      ...f,
      accessible_modules: f.accessible_modules.includes(key)
        ? f.accessible_modules.filter((m) => m !== key)
        : [...f.accessible_modules, key],
    }));
  }
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [confirmTarget, setConfirmTarget] = useState<StaffRow | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminStaff();
      setRows(res.staff);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load staff');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function openCreate() {
    setForm(EMPTY_FORM);
    setEditingUser(null);
    setModal('create');
  }

  function openEdit(row: StaffRow) {
    setForm({
      username: row.username,
      staff_code: row.staff_code ?? '',
      password: '',
      full_name: row.full_name ?? '',
      email: row.email ?? '',
      role: row.role ?? 'Staff',
      department: row.department ?? '',
      unit: row.unit ?? '',
      can_view_all: row.can_view_all,
      is_admin: row.is_admin,
      accessible_modules: row.accessible_modules ?? [],
    });
    setEditingUser(row.username);
    setModal('edit');
  }

  function closeModal() {
    setModal(null);
    setForm(EMPTY_FORM);
    setEditingUser(null);
  }

  async function submitForm() {
    if (modal === 'create') {
      if (!form.password || !form.full_name.trim() || (!form.username.trim() && !form.staff_code.trim())) {
        toast({ tone: 'danger', message: 'Username (or staff code), password and full name are required' });
        return;
      }
    }
    setSaving(true);
    try {
      if (modal === 'create') {
        const input: StaffCreateInput = {
          username: form.username.trim() || undefined,
          staff_code: form.staff_code.trim() || undefined,
          password: form.password,
          full_name: form.full_name.trim(),
          email: form.email.trim() || undefined,
          role: form.role.trim() || 'Staff',
          department: form.department.trim() || undefined,
          unit: form.unit.trim() || undefined,
          can_view_all: form.can_view_all,
          is_admin: form.is_admin,
        };
        const res = await createAdminStaff(input);
        toast({ tone: 'success', message: `Created ${res.username}` });
      } else if (modal === 'edit' && editingUser) {
        const patch: StaffPatchInput = {
          full_name: form.full_name.trim(),
          email: form.email.trim(),
          role: form.role.trim(),
          department: form.department.trim(),
          unit: form.unit.trim(),
          staff_code: form.staff_code.trim(),
          can_view_all: form.can_view_all,
          is_admin: form.is_admin,
          accessible_modules: form.accessible_modules,
        };
        await updateAdminStaff(editingUser, patch);
        toast({ tone: 'success', message: `Updated ${editingUser}` });
      }
      closeModal();
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' });
    } finally {
      setSaving(false);
    }
  }

  async function confirmDeactivate() {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);
    try {
      if (target.active) {
        await deactivateAdminStaff(target.username);
        toast({ tone: 'success', message: `Deactivated ${target.username}` });
      } else {
        await reactivateAdminStaff(target.username);
        toast({ tone: 'success', message: `Reactivated ${target.username}` });
      }
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' });
    }
  }

  const columns: Column<StaffRow>[] = [
    { key: 'full_name', header: 'Name', render: (r) => r.full_name || r.username },
    { key: 'staff_code', header: 'Staff code' },
    { key: 'role', header: 'Role' },
    { key: 'unit', header: 'Unit' },
    {
      key: 'active', header: 'Status',
      render: (r) => (
        <Badge tone={r.active ? 'success' : 'neutral'}>
          {r.active ? 'Active' : 'Inactive'}
        </Badge>
      ),
      exportValue: (r) => (r.active ? 'Active' : 'Inactive'),
    },
    {
      key: 'is_admin', header: 'Admin',
      render: (r) => (r.is_admin ? <Badge tone="info">Admin</Badge> : <span className="text-gray-400">—</span>),
      exportValue: (r) => (r.is_admin ? 'Admin' : ''),
    },
    {
      key: 'username', header: 'Actions',
      render: (r) => (
        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
          {canAdmin && (
            <>
              <Button variant="ghost" size="sm" onClick={() => openEdit(r)}>Edit</Button>
              <Button
                variant="ghost" size="sm"
                onClick={() => setConfirmTarget(r)}
              >
                {r.active ? 'Deactivate' : 'Reactivate'}
              </Button>
            </>
          )}
        </div>
      ),
      exportValue: () => '',
    },
  ];

  return (
    <div className="space-y-4">
      <AdminTabs
        subtitle="Manage staff accounts in the system of record (PostgreSQL)."
        actions={
          canAdmin ? (
            <div className="flex gap-2">
              <Button variant="ghost" onClick={pickStaffFile}>Upload Excel</Button>
              <Button onClick={openCreate}>+ Add staff</Button>
            </div>
          ) : undefined
        }
      />

      {error && (
        <Card><Card.Body>
          <div className="text-sm text-red-600">{error}</div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>Retry</Button>
        </Card.Body></Card>
      )}

      <Card><Card.Body>
        <Table
          columns={columns}
          rows={rows}
          rowKey="username"
          searchable
          paginated
          pageSize={25}
          exportable
          exportFilename="staff.csv"
          loading={loading}
          empty="No staff found."
        />
      </Card.Body></Card>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
            <div className="border-b px-5 py-3 text-base font-semibold text-gray-900">
              {modal === 'create' ? 'Add staff member' : `Edit ${editingUser}`}
            </div>
            <div className="max-h-[70vh] space-y-3 overflow-y-auto px-5 py-4">
              {modal === 'create' && (
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Username"
                    value={form.username}
                    placeholder="Defaults to staff code"
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                  />
                  <Input
                    label="Password *"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                  />
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Full name *"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                />
                <Input
                  label="Staff code"
                  value={form.staff_code}
                  onChange={(e) => setForm({ ...form, staff_code: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Role"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                />
                <Input
                  label="Unit"
                  value={form.unit}
                  onChange={(e) => setForm({ ...form, unit: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Department"
                  value={form.department}
                  onChange={(e) => setForm({ ...form, department: e.target.value })}
                />
                <Input
                  label="Email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </div>
              {modal === 'edit' && allModules.length > 0 && (
                <div className="mb-3">
                  <p className="mb-1 text-sm font-medium">Module access</p>
                  <p className="mb-2 text-xs text-gray-500">
                    Tick modules this user can access. Empty = role default applies.
                  </p>
                  <div className="grid max-h-48 grid-cols-2 gap-x-4 gap-y-1 overflow-auto rounded border p-2">
                    {allModules.map((m) => (
                      <label key={m.key} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.accessible_modules.includes(m.key)}
                          onChange={() => toggleModule(m.key)}
                        />
                        {m.label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex gap-6 pt-1">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={form.can_view_all}
                    onChange={(e) => setForm({ ...form, can_view_all: e.target.checked })}
                  />
                  Can view all staff
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={form.is_admin}
                    onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
                  />
                  Admin privileges
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t px-5 py-3">
              <Button variant="ghost" onClick={closeModal} disabled={saving}>Cancel</Button>
              <Button onClick={() => void submitForm()} disabled={saving}>
                {saving ? 'Saving…' : modal === 'create' ? 'Create' : 'Save'}
              </Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmTarget !== null}
        title={confirmTarget?.active ? 'Deactivate staff member?' : 'Reactivate staff member?'}
        message={
          confirmTarget?.active
            ? `${confirmTarget?.full_name || confirmTarget?.username} will no longer be able to access the system.`
            : `${confirmTarget?.full_name || confirmTarget?.username} will regain access.`
        }
        confirmLabel={confirmTarget?.active ? 'Deactivate' : 'Reactivate'}
        onConfirm={() => void confirmDeactivate()}
        onCancel={() => setConfirmTarget(null)}
      />

      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => !uploadBusy && setUploadOpen(false)}>
          <div className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 shadow-xl"
               onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-lg font-semibold">Staff upload preview</h3>
            <p className="mb-4 text-sm text-gray-500">{uploadName}</p>
            {uploadBusy && !uploadPreview && <p className="text-sm">Validating…</p>}
            {uploadPreview && !uploadPreview.ok && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-red-600">
                  Validation failed — {uploadPreview.errors.length} error(s). Nothing was written.
                </p>
                <ul className="max-h-64 list-disc overflow-auto pl-5 text-sm text-red-600">
                  {uploadPreview.errors.map((er, i) => <li key={i}>{er}</li>)}
                </ul>
              </div>
            )}
            {uploadPreview && uploadPreview.ok && uploadPreview.summary && (
              <div className="space-y-3 text-sm">
                <p className="font-medium text-green-700">
                  ✓ Valid. {uploadPreview.summary.total} staff. Root:{' '}
                  {uploadPreview.summary.root?.name} ({uploadPreview.summary.root?.role}).
                </p>
                <div>
                  <p className="font-medium">Reporting directly to MD ({uploadPreview.summary.reporting_to_md.length}):</p>
                  <ul className="list-disc pl-5">
                    {uploadPreview.summary.reporting_to_md.map((m) => (
                      <li key={m.code}>{m.name} — {m.role}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium">Staff per branch:</p>
                  <div className="grid grid-cols-2 gap-x-4">
                    {Object.entries(uploadPreview.summary.staff_per_branch).map(([b, n]) => (
                      <div key={b} className="flex justify-between"><span>{b}</span><span>{n}</span></div>
                    ))}
                  </div>
                </div>
                <p className="rounded bg-amber-50 p-2 text-amber-800">
                  Applying will REPLACE the staff table (preserving william001 + admin) and
                  cannot be undone. Confirm only if the tree above is correct.
                </p>
              </div>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setUploadOpen(false)} disabled={uploadBusy}>Cancel</Button>
              <Button onClick={() => void confirmStaffUpload()} disabled={uploadBusy || !uploadPreview?.ok}>
                {uploadBusy ? 'Applying…' : 'Confirm & Apply'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
