## Validation Concurrency
- Max concurrent validators: 3
- The application uses a single backend instance on port 8000 and frontend on port 3001.

## Flow Validator Guidance: Analytics
- Use agent-browser.
- URL for analytics: http://localhost:3001/analytics
- Keep test data isolated if possible by using unique trade descriptions or assets.
- Do not modify or delete existing trade data in the journal/backend if not necessary for the test case.
- Clean up any test trades created during testing.
