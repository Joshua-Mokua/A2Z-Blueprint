// v10.496 — Skeleton primitive.
//
// Placeholder shown while data is loading. Tan tradition: use
// shaped skeletons that match the final layout's geometry. A
// loading Stat shows a skeleton bar where the value will go;
// a loading Table shows skeleton rows; a loading Card shows
// skeleton lines of text.
//
// Default is a pulsing grey block; pass shape="line" for text-line
// proportions, shape="circle" for avatars.
//
// API:
//   <Skeleton />                              ← default rectangle
//   <Skeleton shape="line" className="w-32" />
//   <Skeleton shape="circle" className="h-10 w-10" />
//
// Compose multiple skeletons inside a Card to stub out an entire
// loading panel. Animation respects prefers-reduced-motion.

import { cn } from '@/lib/cn';

export interface SkeletonProps {
  shape?: 'block' | 'line' | 'circle';
  className?: string;
}

const SHAPE_CLASSES = {
  block:  'h-6 w-full rounded',
  line:   'h-4 w-full rounded',
  circle: 'h-10 w-10 rounded-full',
} as const;

export function Skeleton({ shape = 'block', className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block bg-gray-200 animate-pulse',
        'motion-reduce:animate-none',
        SHAPE_CLASSES[shape],
        className,
      )}
    />
  );
}
