#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
HIDE1 - hide modules per deployment, and a check that logins point at the
right person.

TWO ITEMS FROM THE PILOT (2026-08-12).

1. "A STAFF NAMED JOSHUA KYUMA WAS SEEING HIS PROFILE ON ALL THE PAGES, but on
   the balanced scorecard he was seeing that of Joshua Muthama. Probably the
   issue is on the staff payroll, which we might have guessed for Joshua
   sometime. Kyuma payroll is 1354 and Muthama is 1355."

   THE DIAGNOSIS IS RIGHT, and the reason it shows up only on the scorecard is
   worth recording: most pages display the name carried in the SESSION, which
   is correct. bsc_departments resolves the person by STAFF CODE and looks them
   up in the register. So a login carrying the wrong code shows the right name
   everywhere and the wrong scorecard in exactly one place.

   That is a bad class of bug - silent, and wrong in the direction of one
   person seeing another's performance.

   scripts/diag_identity.py checks every login against the register: does the
   code exist, does the name against that code match, do two logins share a
   code, and - the part that matters here - WHO SHARES A NAME, because that is
   where a guessed code goes unnoticed. It NAMES the correction and does not
   make it: rewriting identity records unattended is not something to run
   against a payroll.

   NO CODE FIX IS SHIPPED FOR THIS. If the register and the login disagree, the
   data is wrong, and changing the lookup would paper over it while leaving the
   next report wrong in some other way.

2. "THERE ARE PAGES I WANT US TO HIDE FOR NOW since they are confusing yet we
   have not fully detailed them out - Dashboard, Initiatives, Profitability,
   SLA Monitor. They can be left on my end but on the side of the bank they can
   be hidden."

   CONFIG, NOT CODE, and specifically config in org_config.json - a deployment
   delta file each side already owns. The pilot hides a module by listing its
   route in ITS config; this side keeps it. No divergent code, and nothing to
   remember at release time.

   A hardcoded hide list already existed and was empty; the same filter now
   also reads `hidden_modules` from branding, rather than adding a second
   mechanism beside the first.

   KEYED ON ROUTE, NOT LABEL. "EKE Sales Pro" and "A2Z Sales Pro" are the same
   module, and a list keyed on the words would stop matching after a rebrand.

   DEFAULT IS EMPTY, so absent config hides nothing - this can only ever take a
   module away deliberately, never by omission.

TO HIDE THEM ON THE PILOT, add to Alex's data/org_config.json:

    "hidden_modules": ["/", "/initiatives", "/profitability", "/sla"]

Note "/" is the Dashboard route. Nothing else needs to change, and the setting
travels with his config rather than with a release.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_hide1_module_visibility.py            # dry run
    python scripts\patch_hide1_module_visibility.py --apply
"""
import os
import shutil
import sys

BRANDING = os.path.join("utils", "api_branding.py")
SIDEBAR = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
TYPES = os.path.join("frontend", "web", "src", "types", "branding.ts")
DIAG = os.path.join("scripts", "diag_identity.py")
BACKUP_SUFFIX = ".pre_hide1"

PAYLOAD_OLD = '''        "ip_notice": ip_notice(),
    }'''
PAYLOAD_NEW = '''        "ip_notice": ip_notice(),
        # HIDDEN MODULES (ruling 2026-08-12). Config, not code - and config in
        # org_config.json, a deployment delta file each side owns, so the pilot
        # hides them by listing them in ITS config while this side keeps them.
        # Default empty: absent config hides nothing.
        "hidden_modules": hidden_modules(),
    }'''

ACCESSOR = r'''def hidden_modules() -> list:
    """Module paths this deployment should not show.

    Listed by ROUTE, not by label, because a label can be renamed - "EKE Sales
    Pro" is the same module as "A2Z Sales Pro" and a list keyed on the words
    would stop matching the moment somebody rebranded.
    """
    try:
        from utils.config import load_org_config
        v = (load_org_config() or {}).get("hidden_modules")
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return []

'''

SIDEBAR_SRC = r'''import { displayName } from "../lib/names";
import { Link, useLocation } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useAuth } from '@/hooks/useAuth';
import { useRole } from '@/hooks/useRole';
import { isManager } from '@/lib/role';

interface NavItem {
  path: string;
  label: string;
  matchActive: (pathname: string) => boolean;
  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean) => boolean;
}
interface NavGroup { label: string; items: NavItem[]; }

// A hardcoded hide list already existed and was empty. Rather than add a second
// mechanism beside it, the same filter now also reads `hidden_modules` from
// BRANDING - which comes from org_config.json, a file each deployment owns.
//
// So the pilot hides a module by listing its route in ITS config, and this side
// keeps it, with no divergent code and nothing to remember at release time.
// Keyed on ROUTE, not label: "EKE Sales Pro" and "A2Z Sales Pro" are the same
// module, and a list keyed on the words would stop matching after a rebrand.
const DEMO_HIDE = new Set<string>([]);

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },
      { path: '/perform',       label: 'Balanced Scorecard', matchActive: (p) => p === '/perform' },
      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/initiatives',   label: 'Initiatives',      matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability',    matchActive: (p) => p === '/profitability' },
      { path: '/sla',           label: 'SLA Monitor',      matchActive: (p) => p.startsWith('/sla'), visibleFor: (m, a) => m || a },
    ],
  },
  {
    label: 'Pipeline Intelligence (PIS)',
    items: [
      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events') && !p.startsWith('/pipeline/channels') && !p.startsWith('/pipeline/warehouse')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/pipeline/channels', label: 'Origin Channels',    matchActive: (p) => p.startsWith('/pipeline/channels') || p.startsWith('/pipeline/events') },
      // Standalone, NOT a channel: a shelf with claim mechanics and no budget,
      // so grouping it with the invested channels would imply a return question
      // it cannot answer.
      { path: '/pipeline/warehouse', label: 'Deals Warehouse',    matchActive: (p) => p.startsWith('/pipeline/warehouse') },
      { path: '/referrals',       label: 'A2Z Sales Referral Analytics', matchActive: (p) => p.startsWith('/referrals') },
      { path: '/branch-log',      label: 'Daily Log',     matchActive: (p) => p.startsWith('/branch-log') },
      { path: '/portfolio',       label: 'Portfolio',            matchActive: (p) => p.startsWith('/portfolio') },
    ],
  },
  {
    label: 'Credit Intelligence (CIS)',
    items: [
      { path: '/lms',                 label: 'Credit Analysis',     matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/credit-admin',        label: 'Credit Admin',        matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/troops',              label: 'Trops Disbursement',  matchActive: (p) => p.startsWith('/troops'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/credit-analytics',    label: 'Credit Analytics',    matchActive: (p) => p.startsWith('/credit-analytics'), visibleFor: (_m, _a, _c, _md, credit) => credit },
    ],
  },
  {
    label: 'Reference & Admin',
    items: [
      { path: '/cbs',              label: 'Customer Lookup',     matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/config',     label: 'Administration',      matchActive: (p) => (p.startsWith('/admin/') && !p.startsWith('/admin/cbs-debug')) || p.startsWith('/fx-rates'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/cbs-debug', label: 'CBS / FlexCube Debug', matchActive: (p) => p.startsWith('/admin/cbs-debug'), visibleFor: (_m, isA) => isA },
    ],
  },
];

function initials(name?: string) {
  return (name ?? '?').trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');
}

interface SidebarProps { onNavigate?: () => void; }

export function Sidebar({ onNavigate }: SidebarProps) {
  const { pathname } = useLocation();
  const { branding } = useBranding();
  // Absent config hides nothing, so this cannot take a module away from
  // somebody who never asked for it.
  const hidden = new Set<string>(branding?.hidden_modules ?? []);
  const { user } = useRole();
  const { logout } = useAuth();

  const isMgr      = isManager(user);
  const isAdmin    = user?.is_admin ?? false;
  const isCfgAdmin = isAdmin || ['admin', 'director', 'chief', 'managing'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // First-rollout gate: admin or the MD/CEO only.
  const isAdminOrMd = isAdmin || ['managing director', 'chief executive'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // Credit Intelligence modules belong to credit staff (analysts, credit admin,
  // treasury/disbursement, recovery) + admin/MD. Front-line RMs/branch see the
  // pipeline instead, and track their own cases there.
  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <img src="/img/ecobank-light.svg" alt="Ecobank" className="sb-logo" />
        <div className="sb-brand-text">
          <div className="sb-brand-name">{branding?.app_name ?? 'A2Z Blueprint'}</div>
          <div className="sb-brand-tag">MIS 360</div>
        </div>
      </div>

      <nav className="sb-nav">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !DEMO_HIDE.has(item.path)
              && !hidden.has(item.path)
              && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff)),
          );
          if (!items.length) return null;
          return (
            <div key={group.label}>
              <div className="sb-section-lbl">{group.label}</div>
              {items.map((item) => {
                const active = item.matchActive(pathname);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={onNavigate}
                    className={`sb-item${active ? ' active' : ''}`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="sb-foot">
        <div className="sb-user">
          <div className="sb-av">{initials(user?.full_name ?? user?.username)}</div>
          <div className="sb-user-info">
            <div className="sb-user-name">{user?.full_name ? displayName(user.full_name, (user as any).display_name) : (user?.username ?? '—')}</div>
            <div className="sb-user-role">{user?.role ?? ''}</div>
          </div>
        </div>
        <button
          type="button"
          className="sb-logout"
          onClick={() => { logout(); onNavigate?.(); }}
        >
          Sign out
        </button>
        <Link to="/about" onClick={() => onNavigate?.()}
          className="mt-2 block text-center text-[11px] text-white/40 hover:text-white/70">
          © 2026 A2Z · About
        </Link>
      </div>
    </aside>
  );
}
'''

TYPES_SRC = r'''// v10.495 — TypeScript types for the /api/branding response.
//
// This is the contract between the FastAPI backend
// (utils/api_branding.py) and the React frontend. Backend Python
// returns a dict matching this shape. If you change one side,
// change both.
//
// Audit gate G381 enforces that this type matches utils/api_branding.py's
// response shape.

export interface BrandColors {
  primary: string;
  secondary: string;
  accent: string;
}

export interface Branding {
  /** Routes this deployment should not show in the sidebar. Empty or absent
   *  means show everything - config can only ever take a module away
   *  deliberately, never by omission. */
  hidden_modules?: string[];
  bank_name: string;
  app_name: string;
  currency: string;
  currency_symbol: string;
  country: string;
  regulator: string;
  regulator_full: string;
  core_banking_system: string;
  tax_authority: string;
  brand: BrandColors;
  ip_notice: string;
}
'''

DIAG_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does every login point at the right person? READ ONLY. Exit 1 on a mismatch.

RULING (2026-08-12): "a staff named Joshua Kyuma was seeing his profile on all
the pages, but on the balanced scorecard he was seeing that of Joshua Muthama.
Probably the issue is on the staff payroll, which we might have guessed for
Joshua sometime."

WHY THIS SHOWS UP ONLY ON THE SCORECARD. Most pages display the name carried in
the SESSION, which is right. The scorecard resolves the person by STAFF CODE and
looks them up in the register - so a user record carrying the wrong code shows
the correct name everywhere and the wrong scorecard in one place. The
inconsistency is invisible until somebody opens their own scorecard and does not
recognise the numbers.

That makes it a bad class of bug: silent, and wrong in the direction of somebody
seeing another person's performance.

WHAT THIS CHECKS, for every login:

    the staff code on the user record exists in the register
    the name on the user record matches the name against that code
    no two logins share a staff code
    no two register rows share a staff code
    people who share a SURNAME or a FIRST NAME are listed, because that is
        where a guessed code does its damage and nobody notices

IT NAMES THE CORRECTION rather than making it - a script that rewrites identity
records unattended is not something to run on a payroll.

    python scripts\\diag_identity.py
    python scripts\\diag_identity.py --name Joshua
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())


def main():
    focus = ""
    if "--name" in sys.argv:
        i = sys.argv.index("--name")
        if i + 1 < len(sys.argv):
            focus = sys.argv[i + 1].strip().lower()

    try:
        from utils.core import UserManager
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    try:
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unavailable: %s" % exc)
        return 1

    reg = {}
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if code:
            reg[code] = {"name": str(r.get("Staff Name") or "").strip(),
                         "role": str(r.get("Role") or "").strip(),
                         "unit": str(r.get("Unit") or "").strip()}

    users = UserManager().users or {}

    print("=" * 78)
    print("IDENTITY CHECK")
    print("=" * 78)
    print("  register  %d staff" % len(reg))
    print("  logins    %d" % len(users))

    problems = []

    # 1. Duplicate codes in the register itself.
    dupes = [c for c, n in Counter(
        str(r.get("Staff Code") or "").strip()
        for _i, r in df.iterrows()).items() if c and n > 1]
    if dupes:
        problems.append("register has duplicate staff codes: %s" % ", ".join(dupes[:6]))

    # 2. Two logins claiming one staff code. This is the shape that puts one
    #    person on another's scorecard.
    by_code = defaultdict(list)
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        if code:
            by_code[code].append(uname)
    shared = {c: names for c, names in by_code.items() if len(names) > 1}

    # 3. Name on the login vs name against its code.
    mismatches = []
    orphans = []
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        uname_full = str(u.get("full_name") or u.get("name") or "").strip()
        if not code:
            continue
        row = reg.get(code)
        if not row:
            orphans.append((uname, code, uname_full))
            continue
        a = " ".join(uname_full.lower().split())
        b = " ".join(row["name"].lower().split())
        if a and b and a != b:
            # Same person written two ways is not a mismatch worth shouting
            # about; a DIFFERENT SURNAME is.
            if set(a.split()) & set(b.split()):
                mismatches.append((uname, code, uname_full, row["name"], "partial"))
            else:
                mismatches.append((uname, code, uname_full, row["name"], "different"))

    print("\n" + "-" * 78)
    print("LOGINS WHOSE NAME DOES NOT MATCH THEIR STAFF CODE")
    print("-" * 78)
    if not mismatches:
        print("  none")
    for uname, code, shown, actual, kind in mismatches:
        flag = "***" if kind == "different" else "   "
        print("  %s %-16s code %-8s login says %-28s register says %s"
              % (flag, uname, code, shown[:28], actual[:28]))
        if kind == "different":
            problems.append("%s (code %s) is named %r but that code belongs to %r"
                            % (uname, code, shown, actual))

    if shared:
        print("\n" + "-" * 78)
        print("STAFF CODES CLAIMED BY MORE THAN ONE LOGIN")
        print("-" * 78)
        for code, names in shared.items():
            print("  *** %-8s %s   -> %s"
                  % (code, ", ".join(names), reg.get(code, {}).get("name", "not in register")))
            problems.append("code %s is claimed by %d logins" % (code, len(names)))

    if orphans:
        print("\n" + "-" * 78)
        print("LOGINS POINTING AT A CODE THAT IS NOT IN THE REGISTER")
        print("-" * 78)
        for uname, code, shown in orphans[:10]:
            print("      %-16s code %-8s %s" % (uname, code, shown[:30]))
        problems.append("%d login(s) point at a code not in the register" % len(orphans))

    # 4. WHERE A GUESS DOES ITS DAMAGE: people who share a name fragment.
    print("\n" + "-" * 78)
    print("PEOPLE SHARING A NAME - where a guessed code goes unnoticed")
    print("-" * 78)
    parts = defaultdict(list)
    for code, r in reg.items():
        for p in r["name"].split():
            if len(p) > 2:
                parts[p.lower()].append((code, r["name"], r["role"]))
    shown_any = False
    for part, people in sorted(parts.items()):
        if len(people) < 2:
            continue
        if focus and part != focus:
            continue
        if not focus and len(people) < 3:
            continue
        shown_any = True
        print("  %s (%d)" % (part.title(), len(people)))
        for code, nm, role in sorted(people)[:8]:
            login = ", ".join(by_code.get(code, [])) or "no login"
            print("      %-8s %-30s %-26s [%s]" % (code, nm[:30], role[:26], login))
    if not shown_any:
        print("  none to show")

    print("\n" + "=" * 78)
    if not problems:
        print("Every login resolves to the person it claims.")
        return 0
    print("%d PROBLEM(S):\n" % len(problems))
    for p in problems:
        print("   * %s" % p)
    print("")
    print("NOT corrected automatically. Rewriting identity records unattended is")
    print("not something to run against a payroll - fix the staff_code on the")
    print("login in users.json, or the row in the register, whichever is wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    for p in (BRANDING, SIDEBAR, TYPES):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    br = open(BRANDING, encoding="utf-8").read()
    if "def hidden_modules(" in br:
        print("ABORT: HIDE1 looks applied.")
        return 1
    if br.count(PAYLOAD_OLD) != 1:
        print("ABORT: the branding payload matched %d times." % br.count(PAYLOAD_OLD))
        return 1

    i = br.index("    return {\n        \"bank_name\"")
    i = br.rindex("\ndef ", 0, i)
    br = br[:i] + "\n" + ACCESSOR + br[i:]
    br = br.replace(PAYLOAD_OLD, PAYLOAD_NEW, 1)
    print("  ok  branding serves hidden_modules")

    # Config can only ever hide deliberately.
    if "return []" not in ACCESSOR:
        print("ABORT: the default is not empty - absent config could hide a")
        print("       module from somebody who never asked.")
        return 1
    if "hidden.has(item.path)" not in SIDEBAR_SRC:
        print("ABORT: the sidebar does not apply the list.")
        return 1
    if "item.label" in SIDEBAR_SRC.split("hidden.has")[0][-200:]:
        print("ABORT: hiding appears keyed on label, which breaks on a rebrand.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if SIDEBAR_SRC.count(op) != SIDEBAR_SRC.count(cl):
            print("ABORT: sidebar unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: empty default, keyed on route")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((BRANDING, br), (SIDEBAR, SIDEBAR_SRC), (TYPES, TYPES_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if not os.path.exists(DIAG):
        open(DIAG, "w", encoding="utf-8", newline="").write(DIAG_SRC)
        print("CREATED %s" % DIAG)

    import py_compile
    try:
        py_compile.compile(BRANDING, doraise=True)
        print("  ok  api_branding.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Find the identity mismatch first - it names the correction:")
    print("  python scripts\\diag_identity.py --name Joshua")
    print("")
    print("To hide the four modules ON THE PILOT ONLY, add to Alex's")
    print("data/org_config.json (his file, not ours):")
    print('  "hidden_modules": ["/", "/initiatives", "/profitability", "/sla"]')
    return 0


if __name__ == "__main__":
    sys.exit(main())
