// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
// v10.500 Phase 1 Batch 3a:
//   - /login route added (public, no ProtectedRoute wrapper).
//   - /perform and /profitability now wrapped in ProtectedRoute.
//   - /components remains public per Batch 3a doctrine — design-system
//     showcase, must be reachable for frontend governance inspection.
//   - AuthProvider is now the real provider (no longer a stub).
// v10.500 Phase 1 Batch 3b:
//   - /change-password route added, wrapped in ProtectedRoute. The
//     route is reachable for both 'must_rotate' (forced rotation) and
//     'authenticated' (future voluntary rotation) auth states.
//     ProtectedRoute's path-aware must_rotate gate confines users with
//     must_rotate tokens to this route specifically.
// v10.510 Phase 4 Batch β1:
//   - /pipeline route added (protected, requireAuth).
//   - Pipeline route element is wrapped in PipelineProvider so the
//     deal list state lives only where it's consumed — not hoisted to
//     app-level. Keeps the G381-protected provider chain unchanged.
// v10.511 Phase 4 Batch β2:
//   - /pipeline/:dealId route added (protected, requireAuth).
//   - Detail page is page-local — no PipelineProvider wrap.
// v10.512 Phase 4 Batch β3:
//   - /pipeline/new route added BEFORE /pipeline/:dealId. RR6 ranks
//     static routes above dynamic ones automatically, but explicit
//     ordering documents intent for future maintainers.
// v10.513 Phase 4 Batch β4:
//   - /pipeline/queues route added (manager-only via page guard).
//   - AppShell layout route introduced wrapping all protected routes
//     EXCEPT /change-password. The shell renders the persistent
//     Sidebar; pages render via React Router 6's <Outlet />.
//   - /change-password deliberately stays OUTSIDE AppShell — user
//     in must_rotate status would see a mocking sidebar of nav
//     links they can't use otherwise.
//   - /login and /components stay outside AppShell as before
//     (public, no auth needed).
//   - G381 byte-for-byte chain still unchanged:
//     QueryClient → Branding → Toast → Auth → Role → WebSocket → BrowserRouter
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>` — chain order
//   - Existing route paths `/`, `/perform`, `/profitability`, `/components`,
//     `/login`, `/change-password`, `/pipeline`, `/pipeline/new`,
//     `/pipeline/:dealId`

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { RoleProvider } from './providers/RoleProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { PipelineProvider } from './providers/PipelineProvider';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './components/AppShell';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';
import { Login } from './pages/Login';
import { ChangePassword } from './pages/ChangePassword';
import { Pipeline } from './pages/Pipeline';
import { PipelineDealDetail } from './pages/PipelineDealDetail';
import { PipelineCreate } from './pages/PipelineCreate';
import { PipelineManagerQueues } from './pages/PipelineManagerQueues';
import { Lms } from './pages/Lms';
import { LmsApplicationDetail } from './pages/LmsApplicationDetail';
import { CreditAdmin } from './pages/CreditAdmin';
import { CreditAdminCaseDetail } from './pages/CreditAdminCaseDetail';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <ToastProvider>
        <AuthProvider><RoleProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                {/* Public — login surface */}
                <Route path="/login" element={<Login />} />

                {/* Public — design-system showcase (Batch 3a) */}
                <Route path="/components" element={<Showcase />} />

                {/* Protected (no shell) — password rotation must be
                    standalone so must_rotate users don't see a sidebar
                    of nav links they can't use until rotation completes. */}
                <Route path="/change-password" element={
                    <ProtectedRoute requireAuth><ChangePassword /></ProtectedRoute>
                } />

                {/* Protected (with shell) — all operational surfaces
                    share the AppShell layout with persistent Sidebar.
                    Pages render via <Outlet /> inside AppShell. */}
                <Route element={
                    <ProtectedRoute requireAuth>
                        <AppShell />
                    </ProtectedRoute>
                }>
                    {/* Dashboard at root */}
                    <Route path="/" element={<Dashboard />} />

                    {/* BSC + Profitability */}
                    <Route path="/perform" element={<Perform />} />
                    <Route path="/profitability" element={<Profitability />} />

                    {/* Pipeline list — wrapped in PipelineProvider for the
                        cascade-scoped deal list state. */}
                    <Route path="/pipeline" element={
                        <PipelineProvider>
                            <Pipeline />
                        </PipelineProvider>
                    } />

                    {/* Pipeline subroutes — order: static before dynamic.
                        RR6 ranks these automatically but explicit ordering
                        documents intent. */}
                    <Route path="/pipeline/new"     element={<PipelineCreate />} />
                    <Route path="/pipeline/queues"  element={<PipelineManagerQueues />} />
                    <Route path="/pipeline/:dealId" element={<PipelineDealDetail />} />

                    {/* LMS subroutes — β5. Same static-before-dynamic ordering. */}
                    <Route path="/lms"         element={<Lms />} />
                    <Route path="/lms/:appId"  element={<LmsApplicationDetail />} />

                    {/* Credit Admin subroutes — β6. */}
                    <Route path="/credit-admin"          element={<CreditAdmin />} />
                    <Route path="/credit-admin/:caseId"  element={<CreditAdminCaseDetail />} />
                </Route>
            </Routes>
        </BrowserRouter></WebSocketProvider></RoleProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
