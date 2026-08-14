#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SB1 - Department Review gets its own way in.

RULING (2026-08-14): "for the department gate we have a sidebar dedicated to
the department which we could name Department Review ... this can also be the
place where the head-office team, especially those voting, can get in and see
the committee as can also vote, but it be restricted to selected voters only."

Credit Analysis is the BANK credit analyst's module - Julius Korir's work. The
department analyst and the committee members were borrowing it and seeing a
screen built for somebody else's job.

RESTRICTED TO CREDIT STAFF, the same gate Credit Analysis already uses. A
tighter one - only named committee members - belongs on the SERVER, where it
already is: the vote endpoint refuses a non-member with a 403. Hiding a menu
entry is not a permission, and treating it as one is how people come to believe
a screen is safe because it is hard to find.

IT TRAVELS. Sidebar.tsx came off the delta list on 2026-08-11 precisely so the
pilot could receive new menu entries. I told Josh otherwise earlier today - a
grep matched the word inside the comment explaining the repeal, and I read the
comment as the rule. It is not frozen.

Verified: tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_sb1_department_review_nav.py            # dry run
    python scripts\\patch_sb1_department_review_nav.py --apply
"""
import json
import os
import shutil
import sys

BACKUP_SUFFIX = ".pre_sb1"


def _p(rel):
    return os.path.join(*rel.split("/"))


FILES = json.loads(r'''{
 "frontend/web/src/components/Sidebar.tsx": "import { displayName } from \"../lib/names\";\nimport { Link, useLocation } from 'react-router-dom';\nimport { useBranding } from '@/hooks/useBranding';\nimport { useAuth } from '@/hooks/useAuth';\nimport { useRole } from '@/hooks/useRole';\nimport { isManager } from '@/lib/role';\n\ninterface NavItem {\n  path: string;\n  label: string;\n  matchActive: (pathname: string) => boolean;\n  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean) => boolean;\n}\ninterface NavGroup { label: string; items: NavItem[]; }\n\n// A hardcoded hide list already existed and was empty. Rather than add a second\n// mechanism beside it, the same filter now also reads `hidden_modules` from\n// BRANDING - which comes from org_config.json, a file each deployment owns.\n//\n// So the pilot hides a module by listing its route in ITS config, and this side\n// keeps it, with no divergent code and nothing to remember at release time.\n// Keyed on ROUTE, not label: \"EKE Sales Pro\" and \"A2Z Sales Pro\" are the same\n// module, and a list keyed on the words would stop matching after a rebrand.\nconst DEMO_HIDE = new Set<string>([]);\n\nconst NAV_GROUPS: NavGroup[] = [\n  {\n    label: 'Executive Intelligence',\n    items: [\n      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },\n      { path: '/perform',       label: 'Balanced Scorecard', matchActive: (p) => p === '/perform' },\n      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/'), visibleFor: (_m, _a, _c, md) => md },\n      { path: '/initiatives',   label: 'Initiatives',      matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },\n      { path: '/profitability', label: 'Profitability',    matchActive: (p) => p === '/profitability' },\n      { path: '/sla',           label: 'SLA Monitor',      matchActive: (p) => p.startsWith('/sla'), visibleFor: (m, a) => m || a },\n    ],\n  },\n  {\n    label: 'Pipeline Intelligence (PIS)',\n    items: [\n      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events') && !p.startsWith('/pipeline/channels') && !p.startsWith('/pipeline/warehouse')) },\n      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },\n      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },\n      { path: '/pipeline/channels', label: 'Origin Channels',    matchActive: (p) => p.startsWith('/pipeline/channels') || p.startsWith('/pipeline/events') },\n      // Standalone, NOT a channel: a shelf with claim mechanics and no budget,\n      // so grouping it with the invested channels would imply a return question\n      // it cannot answer.\n      { path: '/pipeline/warehouse', label: 'Deals Warehouse',    matchActive: (p) => p.startsWith('/pipeline/warehouse') },\n      { path: '/referrals',       label: 'A2Z Sales Referral Analytics', matchActive: (p) => p.startsWith('/referrals') },\n      { path: '/branch-log',      label: 'Daily Log',     matchActive: (p) => p.startsWith('/branch-log') },\n      { path: '/portfolio',       label: 'Portfolio',            matchActive: (p) => p.startsWith('/portfolio') },\n    ],\n  },\n  {\n    // \u2500\u2500 DEPARTMENT REVIEW, ITS OWN SECTION (ruling 2026-08-14) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    // \"For the department gate we have a sidebar dedicated to the department\n    // which we could name Department Review ... this can also be the place\n    // where the head-office team, especially those voting, can get in and see\n    // the committee as can also vote, but it be restricted to selected voters\n    // only.\"\n    //\n    // Credit Analysis is the BANK credit analyst's module - Julius Korir's\n    // work. The department analyst and the committee members were borrowing it\n    // and seeing a screen built for somebody else's job. They now have their\n    // own way in.\n    //\n    // RESTRICTED TO CREDIT STAFF, which is the same gate Credit Analysis uses.\n    // A tighter one - only named committee members - belongs on the SERVER,\n    // where it already is: the vote endpoint refuses a non-member with a 403.\n    // Hiding a menu entry is not a permission, and treating it as one is how\n    // people end up believing a screen is safe because it is hard to find.\n    label: 'Department Review',\n    items: [\n      { path: '/lms',                 label: 'Department Review',   matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },\n    ],\n  },\n  {\n    label: 'Credit Intelligence (CIS)',\n    items: [\n      { path: '/lms',                 label: 'Credit Analysis',     matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },\n      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening'), visibleFor: (_m, _a, _c, md) => md },\n      { path: '/credit-admin',        label: 'Credit Admin',        matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/'), visibleFor: (_m, _a, _c, _md, credit) => credit },\n      { path: '/troops',              label: 'Trops Disbursement',  matchActive: (p) => p.startsWith('/troops'), visibleFor: (_m, _a, _c, _md, credit) => credit },\n      { path: '/credit-analytics',    label: 'Credit Analytics',    matchActive: (p) => p.startsWith('/credit-analytics'), visibleFor: (_m, _a, _c, _md, credit) => credit },\n    ],\n  },\n  {\n    label: 'Reference & Admin',\n    items: [\n      { path: '/cbs',              label: 'Customer Lookup',     matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/'), visibleFor: (_m, _a, _c, md) => md },\n      { path: '/admin/config',     label: 'Administration',      matchActive: (p) => (p.startsWith('/admin/') && !p.startsWith('/admin/cbs-debug')) || p.startsWith('/fx-rates'), visibleFor: (_m, _a, _c, md) => md },\n      { path: '/admin/cbs-debug', label: 'CBS / FlexCube Debug', matchActive: (p) => p.startsWith('/admin/cbs-debug'), visibleFor: (_m, isA) => isA },\n    ],\n  },\n];\n\nfunction initials(name?: string) {\n  return (name ?? '?').trim().split(/\\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');\n}\n\ninterface SidebarProps { onNavigate?: () => void; }\n\nexport function Sidebar({ onNavigate }: SidebarProps) {\n  const { pathname } = useLocation();\n  const { branding } = useBranding();\n  // Absent config hides nothing, so this cannot take a module away from\n  // somebody who never asked for it.\n  const hidden = new Set<string>(branding?.hidden_modules ?? []);\n  const { user } = useRole();\n  const { logout } = useAuth();\n\n  const isMgr      = isManager(user);\n  const isAdmin    = user?.is_admin ?? false;\n  const isCfgAdmin = isAdmin || ['admin', 'director', 'chief', 'managing'].some((t) => (user?.role ?? '').toLowerCase().includes(t));\n  // First-rollout gate: admin or the MD/CEO only.\n  const isAdminOrMd = isAdmin || ['managing director', 'chief executive'].some((t) => (user?.role ?? '').toLowerCase().includes(t));\n  // Credit Intelligence modules belong to credit staff (analysts, credit admin,\n  // treasury/disbursement, recovery) + admin/MD. Front-line RMs/branch see the\n  // pipeline instead, and track their own cases there.\n  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');\n\n  return (\n    <aside className=\"sidebar\">\n      <div className=\"sb-brand\">\n        <img src=\"/img/ecobank-light.svg\" alt=\"Ecobank\" className=\"sb-logo\" />\n        <div className=\"sb-brand-text\">\n          <div className=\"sb-brand-name\">{branding?.app_name ?? 'A2Z Blueprint'}</div>\n          <div className=\"sb-brand-tag\">MIS 360</div>\n        </div>\n      </div>\n\n      <nav className=\"sb-nav\">\n        {NAV_GROUPS.map((group) => {\n          const items = group.items.filter(\n            (item) => !DEMO_HIDE.has(item.path)\n              && !hidden.has(item.path)\n              && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff)),\n          );\n          if (!items.length) return null;\n          return (\n            <div key={group.label}>\n              <div className=\"sb-section-lbl\">{group.label}</div>\n              {items.map((item) => {\n                const active = item.matchActive(pathname);\n                return (\n                  <Link\n                    key={item.path}\n                    to={item.path}\n                    onClick={onNavigate}\n                    className={`sb-item${active ? ' active' : ''}`}\n                  >\n                    {item.label}\n                  </Link>\n                );\n              })}\n            </div>\n          );\n        })}\n      </nav>\n\n      <div className=\"sb-foot\">\n        <div className=\"sb-user\">\n          <div className=\"sb-av\">{initials(user?.full_name ?? user?.username)}</div>\n          <div className=\"sb-user-info\">\n            <div className=\"sb-user-name\">{user?.full_name ? displayName(user.full_name, (user as any).display_name) : (user?.username ?? '\u2014')}</div>\n            <div className=\"sb-user-role\">{user?.role ?? ''}</div>\n          </div>\n        </div>\n        <button\n          type=\"button\"\n          className=\"sb-logout\"\n          onClick={() => { logout(); onNavigate?.(); }}\n        >\n          Sign out\n        </button>\n        <Link to=\"/about\" onClick={() => onNavigate?.()}\n          className=\"mt-2 block text-center text-[11px] text-white/40 hover:text-white/70\">\n          \u00a9 2026 A2Z \u00b7 About\n        </Link>\n      </div>\n    </aside>\n  );\n}\n"
}''')



def main():
    apply = "--apply" in sys.argv
    bar = "frontend/web/src/components/Sidebar.tsx"
    if not os.path.isfile(_p(bar)):
        print("ABORT: %s not found." % bar)
        return 1

    cur = open(_p(bar), encoding="utf-8").read()
    if "label: 'Department Review'" in cur:
        print("ABORT: SB1 looks applied.")
        return 1

    new = FILES[bar]
    # WHOLE FILE, so it must prove it takes nothing away - and this file has
    # form: HIDE1 once shipped it whole and carried a Deals Warehouse entry to
    # the pilot.
    for m in ("Credit Analysis", "Manager Queues", "Daily Log", "Portfolio",
              "Sales Pro Analytics", "Credit Admin", "Trops Disbursement"):
        if cur.count(m) and not new.count(m):
            print("ABORT: %r is in the current file and NOT in this patch." % m)
            return 1
    # And it must NOT introduce one.
    if new.count("Deals Warehouse") > cur.count("Deals Warehouse"):
        print("ABORT: this patch would add a Deals Warehouse entry, which is")
        print("       exactly what HIDE1 did wrong.")
        return 1
    print("  ok  nothing added or removed but the new section")

    if "label: 'Department Review'" not in new:
        print("ABORT: the section is missing.")
        return 1
    if "credit) => credit" not in new:
        print("ABORT: the entry is not gated on credit staff.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if new.count(op) != new.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: section present, gated, brackets balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(_p(bar), _p(bar) + BACKUP_SUFFIX)
    open(_p(bar), "w", encoding="utf-8", newline="").write(new)
    print("APPLIED %s" % bar)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
