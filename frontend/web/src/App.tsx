// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
// v10.500 Phase 1 Batch 3a:
//   - /login route added (public, no ProtectedRoute wrapper).
//   - /perform and /profitability now wrapped in ProtectedRoute.
//   - /components remains public per Batch 3a doctrine (#4) — it is the
//     design-system showcase and must be reachable for frontend
//     governance inspection without authentication.
//   - AuthProvider is now the real provider (no longer a stub).
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>` — chain order
//   - Existing route paths `/`, `/perform`, `/profitability`, `/components`
//
// AMENDED CHAIN (v10.496, unchanged in Batch 3a):
//   QueryClient → Branding → Toast → Auth → Role → WebSocket → BrowserRouter
//
// Toast is placed BELOW Branding so toasts can read brand colors,
// but ABOVE Auth so unauthenticated pages (login) can fire toasts too.
// RoleProvider sits BELOW Auth — it reads auth.status to gate its
// fetches per Batch 3a wiring.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { RoleProvider } from './providers/RoleProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';
import { Login } from './pages/Login';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <ToastProvider>
        <AuthProvider><RoleProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                {/* Public — login surface */}
                <Route path="/login" element={<Login />} />

                {/* Public — design-system showcase (Batch 3a #4) */}
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
            </Routes>
        </BrowserRouter></WebSocketProvider></RoleProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
