// v10.497 Phase 0 — Badge (shadcn + A2Z extensions).
// ─────────────────────────────────────────────────────────────────
// Base: shadcn/ui Badge.
//
// A2Z extension: semantic `tone` variants in addition to the
// shadcn `variant` system. shadcn's defaults (default/secondary/
// destructive/outline) are visually generic — fine for a generic
// component library, not enough signal for banking dashboards
// where a Badge's color carries operational meaning:
//
//   success → "Closed Won", "Met", "Approved", "Live"
//   warning → "At Risk", "Behind", "Pending Review"
//   danger  → "Breach", "NPL", "Failed", "Closed Lost"
//   info    → "Read-only", "Archived", informational tags
//   brand   → brand-cyan, used sparingly for "Premium", "Featured"
//   neutral → default grey (same as shadcn default variant)
//
// Tones map to the same CSS variables from index.css that other
// shadcn components use — single color system, doctrine satisfied.
//
// Both `variant` (shadcn) and `tone` (A2Z) are supported. If both
// are passed, `tone` wins. Most consumer code should use `tone`.

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/cn"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
      },
      // A2Z extension: semantic tones.
      // These use tokens.ts color values (via Tailwind utility classes
      // that resolve to those values). They override `variant` when set.
      tone: {
        neutral: "border-transparent bg-muted text-muted-foreground",
        success: "border-transparent bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
        warning: "border-transparent bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/20",
        danger:  "border-transparent bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20",
        info:    "border-transparent bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-600/20",
        brand:   "border-transparent bg-brand-primary/10 text-brand-secondary ring-1 ring-inset ring-brand-primary/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, tone, ...props }: BadgeProps) {
  // If `tone` is provided, it takes precedence — don't apply both.
  // Pass undefined for variant when tone is set so cva doesn't emit
  // the variant classes alongside.
  return (
    <div
      className={cn(
        badgeVariants(tone ? { tone } : { variant }),
        className
      )}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
