// Live indicator for admin screens: which store is actually serving this
// data right now (Postgres vs the users.json fallback), and — for
// hierarchy — which of the two separate hierarchy systems (role-based
// org_config.json vs per-person Postgres reports_to) this page is showing.
// Includes a "Sync now" action that rebuilds the generated staff_register.xlsx
// projection from Postgres, the one safe direction to sync in.

import { useEffect, useState } from 'react';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { fetchDataSourceStatus, syncDataSource, type DataSourceStatus } from '@/lib/api';

interface DataSourceBadgeProps {
  domain: 'users' | 'hierarchy';
}

export function DataSourceBadge({ domain }: DataSourceBadgeProps) {
  const [status, setStatus] = useState<DataSourceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  async function load() {
    try {
      const d = await fetchDataSourceStatus();
      setStatus(d);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleSync() {
    if (syncing) return;
    setSyncing(true);
    try {
      await syncDataSource();
      await load();
    } catch {
      /* badge just keeps showing the last-known status */
    } finally {
      setSyncing(false);
    }
  }

  if (loading) return null;
  if (!status) {
    return <Badge tone="warning" size="sm">Data source unknown</Badge>;
  }

  if (domain === 'users') {
    const u = status.users;
    const live = u.postgres_ready;
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <Badge tone={live ? 'success' : 'danger'} size="sm">
          {live ? 'Live: PostgreSQL' : 'Fallback: users.json'}
        </Badge>
        {u.total_in_staff_register_xlsx !== null && (
          <Badge tone={u.in_sync ? 'neutral' : 'warning'} size="sm">
            Register: {u.total_in_staff_register_xlsx} / DB: {u.total_registrable_in_postgres}
            {u.in_sync === false ? ' — out of sync' : ''}
          </Badge>
        )}
        <Button variant="ghost" size="sm" loading={syncing} onClick={handleSync}>
          Sync register from DB
        </Button>
      </div>
    );
  }

  const rh = status.hierarchy.role_hierarchy;
  const ph = status.hierarchy.person_hierarchy;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Badge tone="info" size="sm">
        This page edits: role hierarchy ({rh.source}) — {rh.roles_with_parents_set} roles
      </Badge>
      <Badge tone="neutral" size="sm">
        Not shown here: per-person reports_to (Postgres) — {ph.staff_with_reports_to} / {ph.total_staff} staff
      </Badge>
      <Button variant="ghost" size="sm" loading={syncing} onClick={handleSync}>
        Sync staff register from DB
      </Button>
    </div>
  );
}
