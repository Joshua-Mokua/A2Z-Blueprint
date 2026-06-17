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
}

export function PageHeader({ title, subtitle, breadcrumbs, actions }: PageHeaderProps) {
  const navigate = useNavigate();
  const hasRow = Boolean(subtitle) || Boolean(actions);

  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-3.5">
        <h1 className="sr-only">{title}</h1>

        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-gray-400">
            {breadcrumbs.map((c, i) => (
              <span key={`${c.label}-${i}`} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-gray-300">/</span>}
                {c.to
                  ? (
                    <button
                      type="button"
                      onClick={() => navigate(c.to!)}
                      className="hover:text-gray-600 transition-colors"
                    >
                      {c.label}
                    </button>
                  )
                  : <span className="text-gray-600 font-medium">{c.label}</span>}
              </span>
            ))}
          </nav>
        )}

        {hasRow && (
          <div className="flex items-center justify-between gap-4 mt-1.5">
            {subtitle
              ? <p className="text-sm text-gray-500 min-w-0 truncate">{subtitle}</p>
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
