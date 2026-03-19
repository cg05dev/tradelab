# Validation Concurrency

- **Web UI**: Concurrency limit is 1. (Browser automation is resource intensive; serial execution is stable for the UI flow validations).
- **Backend API**: Concurrency limit is 3.

## Flow Validator Guidance: Web UI
- Surface: Browser UI (Agent Browser)
- Isolation: Each flow validator subagent should be assigned a fresh browser session (via --session).
- Do not access global state unless it's for setup. Tests should assume the initial state (Welcome if portfolio unset, planner if set).
- Ensure services are healthy before starting individual subagent flow.
- Reset the state between tests if the flow makes changes (use API clear routes if available).

## Flow Validator Guidance: Backend API
- Surface: Backend API (cURL)
- Isolation: Tests can run concurrently if they do not depend on the exact trade history or if they use `clear_all_trades` endpoint for isolation at the start of the test.
- Coordinate with other validators to ensure they aren't working on the same global portfolio variable if testing mode toggle/persistence.
