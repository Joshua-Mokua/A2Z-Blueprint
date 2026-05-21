# A2Z MIS 360 — React Native scaffolding

## Status

This subtree contains the **architectural skeleton** for the React
Native mobile app specified in **Standard #38** of the master spec.
It is NOT a runnable build. Same status and design rationale as
`frontend/web/` — see that README for context.

## What's here

```
frontend/mobile/services/
  offlineSync.ts       offline operation queue + cached reads via AsyncStorage
```

## What needs to be added

### 1. Initialize the project

Recommended: Expo (faster bootstrap, OTA updates).

```bash
cd frontend/mobile
npx create-expo-app@latest .
npm install @react-native-async-storage/async-storage
npm install @tanstack/react-query
```

### 2. Wire offlineSync into the data layer

The service is shipped as a singleton (default export). Use it from
React Query mutations:

```typescript
import offlineSync from './services/offlineSync';

const submitMutation = useMutation({
  mutationFn: async (payload) => {
    if (!isOnline) {
      await offlineSync.queueOperation({
        id: `${Date.now()}`,
        type: 'bsc_submit',
        payload,
      });
      return { queued: true };
    }
    return await api.submitBsc(payload);
  },
});
```

### 3. Audit gate G46

Verifies this file exists with the spec literals:

  - `class OfflineSyncService`
  - `async queueOperation(operation)` / `this.queue.push(operation)`
  - `await this.saveQueue()` / `this.processQueue()`
  - `async getOfflineData(key)` / `AsyncStorage.getItem(\`offline_${key}\`)`

## Honesty discipline (offline-first failure modes)

This service is shipped with three honesty rules baked in:

  1. Failed operations are **never silently dropped** — retryCount and
     lastError stay on the queue entry so the UI can surface them.
  2. Corrupt offline queue (parse failure) does **not** auto-clear —
     it logs an error and requires manual recovery, because silently
     clearing user data is the worst possible failure mode for a bank
     app.
  3. Cached reads should be **timestamped** so stale data is shown as
     stale, not pretending to be current. (TODO when the cache wrapper
     lands.)

Mirror the Mandatory Standard #11 pattern from the Python backend:
never silently corrupt user data; surface uncertainty instead.
