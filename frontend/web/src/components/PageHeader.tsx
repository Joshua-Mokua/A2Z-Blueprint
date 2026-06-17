// PageHeader — the one page-title framework. Sits directly under the global
// TopBar and gives every interior page the same chrome: optional breadcrumbs,
// an optional domain eyebrow, the page title, an optional subtitle, and a
// right-aligned action slot. White to match the TopBar (no navy-on-navy).
//
//   <PageHeader
//     breadcrumbs={[{ label: 'Credit Factory' }, { label: 'Credit Analytics' }]}
//     title="Credit Analytics"
//     subtitle="Loan book within your scope."
//     actions={<Button>New</Button>}
//   />

import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

export interface Crumb {
  label: string;
  /** If set, the crumb is a link to this route. */
  to?: string;
}

interface PageHeaderProps {
  title:        string;
  subtitle?:    string;
  /** Small uppercase domain label above the title (used when no breadcrumbs). */
  eyebrow?:     string;
  breadcrumbs?: Crumb[];
  /** Right-aligned actions (buttons, filters). */
  actions?:     ReactNode;
}

export function PageHeader({
  title, subtitle, eyebrow, breadcrumbs, actions,
}: PageHeaderProps) {
  const navigate = useNavigate();

  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-5">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-gray-400 mb-2">
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

        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {eyebrow && (
              <div className="text-[11px] uppercase tracking-wider font-semibold text-brand-primary mb-1">
                {eyebrow}
              </div>
            )}
            <h1 className="text-xl font-semibold text-gray-900 truncate">{title}</h1>
            {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
          </div>
          {actions && (
            <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>
          )}
        </div>
      </div>
    </header>
  );
}
