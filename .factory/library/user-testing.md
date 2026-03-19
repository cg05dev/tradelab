## Validation Concurrency

- **Surface: Web UI** (browser-based testing)
  - Max concurrent validators: 2

## Flow Validator Guidance: Web UI

- **Isolation Boundaries**:
  - Each validator should be assigned a distinct `portfolio_config.json` or equivalent if they need to test disparate portfolio states, or they should use consistent setup to reset the state between runs.
  - Avoid shared global state mutations that can't be isolated; serialize these tests.
  - Each validator should independently verify core shell stability, navigation, and API contract compliance.
  - The browser session must be closed by the validator at the end of its run.
  - Port 3001 is fixed for the frontend; ensure testers handle navigation and state cleanly.
