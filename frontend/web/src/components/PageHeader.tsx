// PageHeader — the per-page context + action strip beneath the global TopBar.
//
// The TopBar now owns the visible page title (domain eyebrow + title), so this
// header deliberately does NOT repeat it. It provides: breadcrumbs (you-are-here
// navigation), an optional subtitle (one line of context), and a right-aligned
// action slot (page-level buttons / filters). The title prop is kept for an
// accessible (screen-reader) heading only, so we never show it twice.

import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

export interface Crumb {
  label: string;
  to?: string;
}

interface PageHeaderProps {
  /** Used as an accessible (sr-only) heading; the TopBar shows the visible title. */
  title:        string;
  subtitle?:    string;
  /** Reserved for compatibility; not rendered (TopBar shows the domain). */
  eyebrow?:     string;
  breadcrumbs?: Crumb[];
  actions?:     ReactNode;
  /** Opt-in Ecobank-blue ribbon (matches the credit WorkbenchShell) for
   *  visual consistency across the app. Defaults to the white header. */
  ribbon?:      boolean;
  /** Opt-in: pin the header to the top of the scrolling area (AppShell's <main>)
   *  so it stays put as the page scrolls. Off by default — every other page
   *  keeps its existing scroll-away behaviour. */
  sticky?:      boolean;
}

export function PageHeader({ title, subtitle, breadcrumbs, actions, ribbon, sticky }: PageHeaderProps) {
  const navigate = useNavigate();
  const hasRow = Boolean(subtitle) || Boolean(actions);
  const headerCls = (ribbon
    ? 'bg-gradient-to-r from-[#0082BB] to-[#005B82] shadow-sm'
    : 'bg-white border-b border-gray-200')
    + (sticky ? ' sticky top-0 z-30' : '');
  const crumbNav    = ribbon ? 'text-white/70' : 'text-gray-400';
  const crumbSep    = ribbon ? 'text-white/40' : 'text-gray-300';
  const crumbLink   = ribbon ? 'hover:text-white transition-colors' : 'hover:text-gray-600 transition-colors';
  const crumbCur    = ribbon ? 'text-white font-medium' : 'text-gray-600 font-medium';
  const subtitleCls = ribbon ? 'text-sm text-white/90 min-w-0 truncate' : 'text-sm text-gray-500 min-w-0 truncate';

  return (
    <header className={headerCls}>
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-3.5">
        <h1 className="sr-only">{title}</h1>

        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className={`flex items-center gap-1.5 text-xs ${crumbNav}`}>
            {breadcrumbs.map((c, i) => (
              <span key={`${c.label}-${i}`} className="flex items-center gap-1.5">
                {i > 0 && <span className={crumbSep}>/</span>}
                {c.to
                  ? (
                    <button
                      type="button"
                      onClick={() => navigate(c.to!)}
                      className={crumbLink}
                    >
                      {c.label}
                    </button>
                  )
                  : <span className={crumbCur}>{c.label}</span>}
              </span>
            ))}
          </nav>
        )}

        {hasRow && (
          <div className="flex items-center justify-between gap-4 mt-1.5">
            {subtitle
              ? <p className={subtitleCls}>{subtitle}</p>
              : <span />}
            {actions && (
              <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
