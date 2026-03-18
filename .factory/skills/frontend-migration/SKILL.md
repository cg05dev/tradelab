# Frontend Migration Worker

## Purpose
Migrate frontend from JSX to TypeScript, add TanStack Router/Query, ensure API origin uses shared client, and preserve UI functionality.

## Procedure

1. **Baseline capture**
   - Run current frontend; capture screenshots of each primary view
   - Record current API client usage patterns (which files call `fetch` or use hardcoded origins)
   - Document current routing approach (if any)

2. **TypeScript migration**
   - Rename `.jsx` files to `.tsx` in order of dependency (leaves first)
   - Add TypeScript types for API responses and component props
   - Fix type errors; run `npm run build` after each batch
   - Commit after all files compile cleanly

3. **TanStack Router setup**
   - Add `@tanstack/react-router` dependency
   - Create router config with primary routes: `/` (Welcome or Planner based on portfolio), `/planner`, `/open-trades`, `/history`, `/analytics`
   - Mount `RouterProvider` in `main.tsx`
   - Convert current view switching to route-based navigation
   - Test SPA navigation (no full-page reload)
   - Test deep-link/refresh on each route

4. **TanStack Query setup**
   - Add `@tanstack/react-query` dependency
   - Mount `QueryClientProvider` in `main.tsx`
   - Convert API calls to use `useQuery`/`useMutation`
   - Ensure all API modules use shared client with `VITE_API_URL` support

5. **API origin consolidation**
   - Ensure `frontend/src/api/client.js` exports a configured fetch wrapper
   - Replace all hardcoded `localhost:8000` origins with shared client
   - Remove `frontend/src/api/hyperliquid.js` or refactor to use shared client
   - Test with `VITE_API_URL` override and without

6. **UI verification**
   - Run through primary user flows
   - Compare screenshots to baseline
   - Fix any regressions

7. **Handoff**
   - Return summary of TypeScript/Router/Query changes
   - Return verification that SPA navigation and API calls work
   - Note any UI changes or intentional differences from baseline
