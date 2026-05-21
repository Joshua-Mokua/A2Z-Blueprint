// v10.495 — WebSocketProvider placeholder.
//
// Required by the original App.tsx contract (frontend/web/README.md
// G46 / G381). Currently a no-op stub; real WebSocket connection
// to FastAPI /ws/{user_id} (utils/websocket_manager.py, Std #40)
// lands in v10.498+.
//
// This stub exists so App.tsx compiles. Real WS handling needs
// auth (which lands in v10.497 first), so this stays empty until
// v10.498.

import type { ReactNode } from 'react';

export function WebSocketProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
