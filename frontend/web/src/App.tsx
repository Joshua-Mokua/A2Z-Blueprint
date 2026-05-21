// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// Original v5.51 scaffolding preserved; v10.495 amendment adds
// BrandingProvider for multi-tenant branding from /api/branding.
//
// CONTRACT NOTES (G381 - replaces phantom G46):
//
// The following literals are preserved byte-for-byte and enforced
// by audit gate G381:
//
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>`
//   - Route paths `/`, `/perform`, `/profitability`
//
// AMENDMENT (v10.495): BrandingProvider added BETWEEN
// QueryClientProvider and AuthProvider. This places branding-from-API
// inside the TanStack Query scope but before auth, so the
// (future) login page can render bank identity without being
// authenticated yet.
//
// New provider chain:
//   QueryClient → Branding → Auth → WebSocket → BrowserRouter

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <AuthProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/perform" element={<Perform />} />
                <Route path="/profitability" element={<Profitability />} />
            </Routes>
        </BrowserRouter></WebSocketProvider></AuthProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
