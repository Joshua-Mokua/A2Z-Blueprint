// v10.495 — AuthProvider placeholder.
//
// Required by the original App.tsx contract (frontend/web/README.md
// G46 / G381). Currently a no-op stub; real JWT auth integration
// with FastAPI /api/auth/login lands in v10.497.
//
// This stub exists so App.tsx compiles. Do not add real auth
// logic here without bumping to the v10.497 milestone — that
// batch builds the auth context properly with token storage,
// refresh handling, and protected route guards.

import type { ReactNode } from 'react';

export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
