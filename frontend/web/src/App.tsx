// frontend/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
// v10.497 Phase 0 amendment:
//   - ToastProvider replaced with sonner <Toaster />.
//     sonner exposes `toast.success()`, `toast.error()`, etc. as
//     module-level functions callable from anywhere (no useToast
//     hook needed). The <Toaster /> is the render target — it
//     produces the floating UI that displays incoming toasts.
//   - Placed INSIDE BrandingProvider so brand CSS variables are
//     available to toast styles (same reasoning as v10.496's
//     ToastProvider position).
//   - Placed at the same nesting level as the router subtree —
//     not a wrapper around it. sonner toasts are a top-level
//     overlay; they don't need to wrap the app.
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
// AMENDED CHAIN (v10.497):
//   QueryClient → Branding → [Toaster sibling] → Auth → WebSocket → BrowserRouter
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';
import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
            <Toaster richColors closeButton position="top-right" />
            <AuthProvider><WebSocketProvider><BrowserRouter>
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/perform" element={<Perform />} />
                    <Route path="/profitability" element={<Profitability />} />
                    <Route path="/components" element={<Showcase />} />
                </Routes>
            </BrowserRouter></WebSocketProvider></AuthProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
