---
name: fullstack-worker
description: Implements features spanning backend and frontend
---

# Fullstack Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features requiring both backend and frontend changes:
- New API endpoints with frontend integration
- Analytics/metrics features
- Data filtering and pagination

## Work Procedure

### 1. Understand the Feature
- Read the feature description carefully
- Identify backend changes needed (endpoints, data models)
- Identify frontend changes needed (API calls, UI components)

### 2. Backend Implementation
- Add/update endpoints in `backend/main.py`
- Ensure endpoints return correct JSON structure
- Test endpoints with curl

```bash
curl http://localhost:8000/api/endpoint
```

### 3. Frontend Implementation
- Add/update API functions in `frontend/src/api/`
- Update or create page components
- Connect to TanStack Query for data fetching

### 4. Add Dependencies
```bash
cd frontend && npm install <package>  # If needed
```

### 5. Verify Locally
```bash
# Backend verification
curl http://localhost:8000/api/new-endpoint

# Frontend verification
cd frontend && npm run typecheck && npm run lint
```

### 6. Manual Browser Verification
- Use agent-browser to test the full flow
- Verify API calls in browser dev tools network tab
- Take screenshots showing the feature working

### 7. Commit Changes
```bash
git add -A
git commit -m "feat(feature-id): description"
```

## Example Handoff

```json
{
  "salientSummary": "Implemented analytics metrics endpoint with timeframe filtering, added frontend timeframe selector and P&L graph using Recharts.",
  "whatWasImplemented": "Backend: Added GET /api/analytics/metrics?timeframe=7d returning { total_pnl, win_rate, avg_win, avg_loss }. Added GET /api/analytics/pnl-series for chart data. Frontend: Added timeframe selector component, integrated Recharts LineChart, connected to API with TanStack Query.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "curl 'http://localhost:8000/api/analytics/metrics?timeframe=30d'", "exitCode": 0, "observation": "Returns { \"total_pnl\": 123.45, \"win_rate\": 0.67, \"avg_win\": 50, \"avg_loss\": 25 }" },
      { "command": "cd frontend && npm run typecheck", "exitCode": 0, "observation": "No TypeScript errors" }
    ],
    "interactiveChecks": [
      { "action": "Navigate to Analytics page, verify metrics display", "observed": "Total P&L $123.45, Win Rate 67%, Avg Win $50 / Avg Loss $25" },
      { "action": "Change timeframe to 7D", "observed": "Metrics update to reflect 7-day period" },
      { "action": "Verify P&L graph renders", "observed": "LineChart displays cumulative P&L over time" }
    ]
  },
  "tests": {
    "added": []
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Backend dependency missing (database, external API)
- Cannot achieve feature within mission boundaries
- Existing bugs block the feature
