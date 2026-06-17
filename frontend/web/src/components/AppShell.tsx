// Application shell — the persistent frame.
//
//   ┌──────────┬─────────────────────────────────────────────┐
//   │          │  TopBar (fixed, never scrolls)               │
//   │ Sidebar  ├─────────────────────────────────────────────┤
//   │ (fixed,  │                                             ▲ │
//   │  full    │  <Outlet /> — ONLY this area scrolls        │ │
//   │  height) │                                             ▼ │
//   └──────────┴─────────────────────────────────────────────┘
//
// h-screen + overflow-hidden on the outer container means the browser page
// never scrolls; the sidebar and top bar stay put; only <main> scrolls.
// Presentation only — no routes, logic, or page content changed.

import { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { TopBar } from '@/components/TopBar';

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Close the mobile drawer on any navigation.
  useEffect(() => { setMobileNavOpen(false); }, [pathname]);

  return (
    <div className="h-screen flex overflow-hidden bg-gray-50">
      {/* Desktop sidebar — full height, fixed */}
      <div className="hidden md:block flex-shrink-0 h-full">
        <Sidebar />
      </div>

      {/* Mobile sidebar drawer */}
      {mobileNavOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/40"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden="true"
          />
          <div className="md:hidden fixed inset-y-0 left-0 z-50 h-full">
            <Sidebar onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </>
      )}

      {/* Right column: fixed top bar + the single scroll area */}
      <div className="flex-1 min-w-0 flex flex-col h-full">
        <TopBar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
