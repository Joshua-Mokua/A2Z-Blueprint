import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/Button';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Catches render-time crashes in the page content area so a bug in one
// page (e.g. calling .toLocaleString() on a null API field) shows a
// recoverable error card instead of taking down the whole app to a
// blank white screen. Placed around AppShell's <Outlet/> — the sidebar
// and nav stay usable so the user can navigate away without reloading.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught a render error:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 p-10 text-center">
          <h2 className="text-lg font-semibold text-gray-900">Something went wrong loading this page.</h2>
          <p className="text-sm text-gray-500 max-w-md">
            {this.state.error.message || 'An unexpected error occurred.'}
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button variant="primary" size="sm" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
