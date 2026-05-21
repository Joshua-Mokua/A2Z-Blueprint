// v10.496 — cn() utility for joining conditional Tailwind classes.
//
// React idiom: components conditionally apply Tailwind classes based
// on props (variant, size, disabled, loading, etc). Writing
// `className={loading ? 'opacity-60 cursor-wait' : ''}` everywhere
// is ugly. cn() takes any number of class-name expressions —
// strings, conditionals, arrays — and joins the truthy ones with
// spaces. Falsy values (false, null, undefined, '') drop out.
//
// Usage:
//   cn('px-4 py-2', 'rounded-md', isPrimary && 'bg-brand-primary')
//   → 'px-4 py-2 rounded-md bg-brand-primary' (when isPrimary)
//   → 'px-4 py-2 rounded-md'                  (when !isPrimary)
//
// This is the minimal-deps version of the popular `clsx` package.
// 10 lines. Zero dependencies. Used by every component in
// src/components/.

type ClassValue =
  | string
  | number
  | null
  | undefined
  | false
  | ClassValue[];

export function cn(...inputs: ClassValue[]): string {
  const out: string[] = [];
  const walk = (item: ClassValue): void => {
    if (!item) return;
    if (typeof item === 'string' || typeof item === 'number') {
      out.push(String(item));
      return;
    }
    if (Array.isArray(item)) {
      for (const sub of item) walk(sub);
    }
  };
  for (const i of inputs) walk(i);
  return out.join(' ');
}
