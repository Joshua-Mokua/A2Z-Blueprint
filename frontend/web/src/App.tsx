// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>`
//   - Route paths `/`, `/perform`, `/profitability`
//
// AMENDED CHAIN (v10.496):
//   QueryClient → Branding → Toast → Auth → WebSocket → BrowserRouter
//
// Toast is placed BELOW Branding so toasts can read brand colors,
// but ABOVE Auth so unauthenticated pages (future login) can fire
// toasts too. Same reasoning as Branding's placement.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { ToastProvider } from './components/Toast';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <ToastProvider>
        <AuthProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/perform" element={<Perform />} />
                <Route path="/profitability" element={<Profitability />} />
                <Route path="/components" element={<Showcase />} />
            </Routes>
        </BrowserRouter></WebSocketProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
