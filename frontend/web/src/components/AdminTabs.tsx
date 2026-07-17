// ──────────────────────────────────────────────────────────────────────────
// AdminTabs — the shared header for all Administration surfaces: the Ecobank
// blue ribbon + a tab bar that navigates between the admin modules. Replaces
// each admin page's individual PageHeader so the admin area reads as ONE place
// with tabs, instead of scattered pages.
//
// Pass an optional `subtitle` to show the current module's one-line description
// in the ribbon. The active tab is derived from the route (NavLink).
// ──────────────────────────────────────────────────────────────────────────
import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PageHeader } from '@/components/PageHeader';

const TABS: { to: string; label: string }[] = [
  { to: '/admin/config',     label: 'Configuration' },
  { to: '/admin/staff',      label: 'Staff' },
  { to: '/admin/roles',      label: 'Roles' },
  { to: '/admin/hierarchy',  label: 'Hierarchy' },
  { to: '/admin/committees', label: 'Committees' },
  { to: '/cascade',          label: 'Target Cascade' },
  { to: '/fx-rates',         label: 'FX Rates' },
];

export function AdminTabs({ subtitle, actions }: { subtitle?: string; actions?: ReactNode }) {
  return (
    <>
      <PageHeader
        ribbon
        title="Administration"
        breadcrumbs={[{ label: 'A2Z MIS 360' }, { label: 'Administration' }]}
        subtitle={subtitle}
        actions={actions}
      />
      <div className="border-b border-gray-200 bg-white">
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-6 2xl:max-w-[1680px]">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'border-[#0082BB] font-medium text-[#0082BB]'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </>
  );
}
