// v10.510 Phase 4 Batch β1 — PermissionBadges component.
//
// Renders the 6 caller-specific permission flags from α7 as compact
// inline badges. Used initially as a diagnostic indicator on the
// pipeline list (so it's visible that α7 is wired correctly), and
// later as the substrate for conditional button rendering across
// the pipeline UI surface.
//
// Visual contract:
//   - One badge per TRUE permission (skip false ones to reduce clutter)
//   - Compact size (sm) — 6 of these per row need to fit
//   - Tone reflects the action's character:
//       view, edit          → neutral (read/modify)
//       advance, validate   → info (forward movement)
//       request_cancel,
//       approve_cancel      → warning (cancellation flow)
//   - Short labels (5-8 chars) for inline display
//
// Why this exists as a distinct component:
//   - DealCard and a future DealDetail page both need this rendering
//   - Centralizing the permission → badge mapping prevents drift
//   - Future polish (tooltips on hover explaining each permission)
//     lands here once, benefits both consumers
//
// Composition only — no hooks, no fetching. Pure presentation.

import { Badge } from '@/components/Badge';
import type { BadgeTone } from '@/components/Badge';
import type { DealPermissions } from '@/types/pipeline';


type PermKey = keyof DealPermissions;

interface BadgeDef {
  key:   PermKey;
  label: string;
  tone:  BadgeTone;
}

const BADGE_DEFS: BadgeDef[] = [
  { key: 'can_view',           label: 'View',     tone: 'neutral' },
  { key: 'can_edit',           label: 'Edit',     tone: 'neutral' },
  { key: 'can_advance_stage',  label: 'Advance',  tone: 'info'    },
  { key: 'can_validate',       label: 'Validate', tone: 'info'    },
  { key: 'can_request_cancel', label: 'Cancel',   tone: 'warning' },
  { key: 'can_approve_cancel', label: 'Approve',  tone: 'warning' },
];


interface PermissionBadgesProps {
  permissions: DealPermissions | undefined;
  /**
   * When true, render all 6 badges with disabled styling for false ones.
   * Default false — only render TRUE badges (cleaner inline display).
   */
  showAll?: boolean;
}

export function PermissionBadges({
  permissions,
  showAll = false,
}: PermissionBadgesProps) {
  // Defensive: if the API didn't return permissions (shouldn't happen
  // post-α7 but possible for stale fixtures), render nothing.
  if (!permissions) return null;

  const visible = showAll
    ? BADGE_DEFS
    : BADGE_DEFS.filter((d) => permissions[d.key]);

  if (visible.length === 0) {
    return (
      <span className="text-xs text-gray-400 italic">
        Read-only
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((d) => {
        const enabled = permissions[d.key];
        return (
          <Badge
            key={d.key}
            tone={enabled ? d.tone : 'neutral'}
            size="sm"
            className={enabled ? '' : 'opacity-40'}
          >
            {d.label}
          </Badge>
        );
      })}
    </div>
  );
}
