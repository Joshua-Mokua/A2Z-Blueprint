// v10.513 Phase 4 Batch β4 — AppShell layout.
//
// Wraps protected routes with the persistent Sidebar + mobile toggle.
// Mounted in App.tsx as a layout route; child routes render via
// React Router 6's <Outlet />.
//
// Layout decisions:
//
//   Desktop (md+):
//     ┌──────────┬─────────────────────────────────────────────┐
//     │          │                                             │
//     │ Sidebar  │   <Outlet /> — current page                 │
//     │  (240px) │                                             │
//     │          │                                             │
//     └──────────┴─────────────────────────────────────────────┘
//
//   Mobile (< md):
//     Top hamburger bar (40px) overlays the Outlet; tapping it slides
//     in the Sidebar as a full-height overlay. Tapping outside closes.
//
// What this shell INTENTIONALLY does not do:
//   - It doesn't render a page header — each page provides its own.
//     Pipeline pages have brand-navy header strips that look fine
//     under the sidebar. Dashboard / Perform / Profitability also
//     have their own headers (authored pre-React-shell era) — those
//     keep working unchanged. Future "shell migration" batch can
//     unify the page chrome, but β4's principle is: introduce the
//     shell without breaking pages I haven't audited.
//   - It doesn't touch /login or /components — those are public
//     routes outside ProtectedRoute and outside the shell.
//
// Why the shell is the wrapper, not Dashboard:
//   React Router 6 layout routes are the canonical way to share UI
//   across multiple sibling routes. Putting <Sidebar /> in App.tsx
//   above the <Routes> would mean it'd render on /login too. Wrapping
//   each individual route in <Sidebar><Page /></Sidebar> would mean
//   re-renders on every navigation. The Outlet pattern gives us
//   neither problem.

import { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';


export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Auto-close mobile nav on route change. Tracked by pathname so
  // any kind of navigation (link, programmatic, browser back) closes it.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile hamburger header — only visible below md */}
      <div
        className="md:hidden sticky top-0 z-30 flex items-center justify-between px-4 py-3 text-white shadow"
        style={{ background: 'var(--brand-secondary)' }}
      >
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation"
          className="px-3 py-1.5 rounded-md text-sm font-medium bg-white/15 hover:bg-white/25 transition-colors"
        >
          ☰ Menu
        </button>
        <div className="text-xs font-semibold opacity-80">
          A2Z MIS 360
        </div>
      </div>

      <div className="flex">
        {/* Desktop sidebar — always rendered, hidden below md */}
        <div className="hidden md:block flex-shrink-0">
          <Sidebar />
        </div>

        {/* Mobile sidebar overlay — only when open */}
        {mobileNavOpen && (
          <>
            {/* Scrim — tap outside to close */}
            <div
              className="md:hidden fixed inset-0 z-40 bg-black/40"
              onClick={() => setMobileNavOpen(false)}
              aria-hidden="true"
            />
            {/* Sliding sidebar */}
            <div className="md:hidden fixed inset-y-0 left-0 z-50">
              <Sidebar onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </>
        )}

        {/* Main content */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
