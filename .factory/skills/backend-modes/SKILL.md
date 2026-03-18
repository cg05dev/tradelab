# Backend Modes Worker

## Purpose
Add planning/live mode support to backend with mode API, execution blocking in planning mode, and persistence.

## Procedure

1. **Baseline verification**
   - Run current backend; verify all existing endpoints work
   - Document current execution flow (which endpoints call Hyperliquid)
   - Note current config persistence mechanism (`portfolio_config.json`)

2. **Mode data model**
   - Add `mode` field to `portfolio_config.json` (values: `planning`, `live`)
   - Default to `planning` if not present or invalid
   - Create helper functions: `get_mode()`, `set_mode(mode)`

3. **Mode API endpoints**
   - `GET /api/mode` → returns `{"mode": "planning"|"live"}`
   - `POST /api/mode` with body `{"mode": "planning"|"live"}` → updates mode, returns new mode
   - `POST /api/mode` with invalid mode → returns 400 `{"error": "invalid_mode", "valid_modes": ["planning", "live"]}`
   - Validate mode value with enum/constant list

4. **Execution blocking in planning mode**
   - Identify execution endpoints: `POST /api/hyperliquid/order`, `POST /api/hyperliquid/close/{coin}`
   - Add mode check at start of each execution endpoint
   - If mode is `planning`, return 403 with body:
     ```json
     {"error": "mode_blocked", "mode": "planning", "reason": "Execution requires live mode. Switch mode via POST /api/mode"}
     ```
   - Ensure no side effects (no Hyperliquid API call) when blocked

5. **Live mode preservation**
   - When mode is `live`, execution endpoints function as before
   - Ensure structured error responses on failure (not generic 500)

6. **Persistence verification**
   - Test mode change → backend restart → mode persists
   - Test corrupt/invalid persisted mode → defaults to planning with warning log

7. **Integration test**
   - In planning mode: attempt execute → 403 blocked
   - Switch to live mode: execute → succeeds (or fails with structured error)
   - Switch back to planning: execute → blocked again

8. **Handoff**
   - Return summary of mode API and blocking logic
   - Return verification that planning blocks execution, live permits it
   - Note any edge cases or error handling decisions
