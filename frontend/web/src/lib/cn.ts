// v10.497 Phase 0 — cn() utility, shadcn-standard version.
// ─────────────────────────────────────────────────────────────────
// Replaces v10.496's minimal bespoke cn() with the
// clsx + tailwind-merge composition that shadcn ships with.
//
// Why upgrade?
//   - clsx handles conditionals, arrays, objects, nullables uniformly
//     (more capable than v10.496's hand-rolled 10-liner).
//   - tailwind-merge resolves Tailwind class CONFLICTS:
//       cn('p-4', 'p-2')          → 'p-2'         (later wins)
//       cn('bg-red-500', isOK && 'bg-emerald-500') → 'bg-emerald-500'
//     This is critical for shadcn components: every consumer passes
//     a className prop that needs to OVERRIDE the component's
//     internal classes, not merge naively (which would leave both
//     bg-red-500 AND bg-emerald-500 in the final class list — last
//     one wins in CSS, but the cascade is harder to reason about).
//   - Every shadcn component in components/ui/* imports this file
//     via the @/lib/cn alias from components.json. Keeping the
//     export name `cn` and the call signature compatible (variadic)
//     means zero changes downstream.
//
// API:
//   cn('px-4 py-2', isPrimary && 'bg-primary')
//   cn(['class-a', 'class-b'], { 'class-c': condition })
//   cn('p-4', { 'p-8': isLarge })   // p-8 wins if isLarge
//
// Trade-off vs v10.496: adds 2 production dependencies
// (clsx ~600 bytes gzipped, tailwind-merge ~10KB gzipped).
// Both are industry standard. Bundle cost is real but tiny next to
// the conflict-resolution safety they buy across the design system.

import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
