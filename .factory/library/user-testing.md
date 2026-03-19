# User Testing

Testing surface and validation concurrency for user testing validation.

## Validation Surface

**Browser Testing (agent-browser)**
- URL: `http://localhost:3001`
- Tool: agent-browser skill
- Navigation: Click tabs, interact with forms, verify page content

**API Testing (curl)**
- URL: `http://localhost:8000`
- Tool: curl commands
- Endpoints: All /api/* endpoints

## Validation Concurrency

**Max Concurrent Validators: 5**

**Rationale:**
- agent-browser instances are lightweight (~300-500 MB each)
- Frontend dev server: ~200 MB
- Available memory: 10 GB headroom
- 5 concurrent × 500 MB = 2.5 GB (well within budget)

**Resource Profile:**
- Memory: 5 GB used / 15 GB total (10 GB available)
- CPU: 16 cores, low load (< 1.0)
- Each agent-browser instance: ~300-500 MB

## Testing Notes

**Mode Switching:**
1. Check current mode: `curl localhost:8000/api/mode`
2. Switch to live: `curl -X POST localhost:8000/api/mode -H "Content-Type: application/json" -d '{"mode":"live"}'`
3. Switch to planning: Same with `{"mode":"planning"}`

**Test Data:**
- Trades stored in `backend/trades.csv`
- Portfolio/mode in `backend/portfolio_config.json`
- Can manually edit files to reset state

**Screenshots:**
- agent-browser saves screenshots to `/tmp/`
- Use for evidence in validation reports
