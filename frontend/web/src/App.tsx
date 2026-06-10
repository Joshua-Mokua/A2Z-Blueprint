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
//   - PipelineProvider sits INSIDE ProtectedRoute so it doesn't attempt
//     to fetch when the caller isn't authenticated yet (ProtectedRoute
//     renders null while auth.status === 'initializing'; PipelineProvider
//     never mounts in that window).
// v10.511 Phase 4 Batch β2:
//   - /pipeline/:dealId route added (protected, requireAuth).
//   - Detail page is NOT wrapped in PipelineProvider — the page fetches
//     its own deal data via GET /api/pipeline/deals/{id} and refetches
//     after each successful mutation. The list page's provider will
//     re-fetch on its next mount when user navigates back.
//   - G381 chain still byte-for-byte unchanged.
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>` — chain order
//   - Existing route paths `/`, `/perform`, `/profitability`, `/components`,
//     `/login`, `/change-password`
//
// AMENDED CHAIN (v10.496, unchanged in Batch 3a/3b/β1):
//   QueryClient → Branding → Toast → Auth → Role → WebSocket → BrowserRouter

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { RoleProvider } from './providers/RoleProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { PipelineProvider } from './providers/PipelineProvider';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';
import { Login } from './pages/Login';
import { ChangePassword } from './pages/ChangePassword';
import { Pipeline } from './pages/Pipeline';
import { PipelineDealDetail } from './pages/PipelineDealDetail';

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

                {/* Protected — operational surfaces */}
                <Route path="/" element={
                    <ProtectedRoute requireAuth><Dashboard /></ProtectedRoute>
                } />
                <Route path="/perform" element={
                    <ProtectedRoute requireAuth><Perform /></ProtectedRoute>
                } />
                <Route path="/profitability" element={
                    <ProtectedRoute requireAuth><Profitability /></ProtectedRoute>
                } />

                {/* Protected — pipeline read surface (β1) */}
                {/* PipelineProvider scoped to this route only — avoids
                    fetching deal data on pages that don't render it. */}
                <Route path="/pipeline" element={
                    <ProtectedRoute requireAuth>
                        <PipelineProvider>
                            <Pipeline />
                        </PipelineProvider>
                    </ProtectedRoute>
                } />

                {/* Protected — pipeline deal detail + owner actions (β2) */}
                {/* No PipelineProvider wrap — the detail page fetches
                    its own deal directly via GET /api/pipeline/deals/{id}.
                    Mutations refetch the same page-local state. The
                    list view will re-fetch on its next mount when
                    user navigates back to /pipeline. */}
                <Route path="/pipeline/:dealId" element={
                    <ProtectedRoute requireAuth>
                        <PipelineDealDetail />
                    </ProtectedRoute>
                } />

                {/* Protected — password rotation (Batch 3b) */}
                {/* Reachable for both must_rotate and authenticated states. */}
                <Route path="/change-password" element={
                    <ProtectedRoute requireAuth><ChangePassword /></ProtectedRoute>
                } />
            </Routes>
        </BrowserRouter></WebSocketProvider></RoleProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
