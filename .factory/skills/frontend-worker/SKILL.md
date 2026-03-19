---
name: frontend-worker
description: Implements frontend UI components and routing changes
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for frontend-only features:
- Navigation/routing changes
- UI component modifications
- Styling updates
- Adding new dependencies (package.json)

## Work Procedure

### 1. Understand the Feature
- Read the feature description carefully
- Identify affected files (router, pages, components)
- Check existing patterns in the codebase

### 2. Implement Changes
- Update routes in `router.tsx` first
- Create or modify page components
- Update navigation components
- Add any new dependencies: `cd frontend && npm install <package>`

### 3. Verify Locally
```bash
cd frontend
npm run typecheck
npm run lint
```

### 4. Manual Browser Verification
- Use agent-browser to verify the UI changes
- Take screenshots showing the changes
- Test all user interactions mentioned in the feature

### 5. Commit Changes
```bash
git add -A
git commit -m "feat(feature-id): description"
```

## Example Handoff

```json
{
  "salientSummary": "Reduced navigation to 2 tabs (Trade, Analytics), created combined Trade page with OpenTrades section, styled execute button prominently with green background.",
  "whatWasImplemented": "Modified router.tsx to remove old routes and add /trade route. Created TradePage.tsx combining PlanTrade and OpenTrades components. Updated PrimaryNav to show only 2 tabs. Changed execute button styling to bg-green-600 font-semibold py-3 rounded-lg.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "cd frontend && npm run typecheck", "exitCode": 0, "observation": "No TypeScript errors" },
      { "command": "cd frontend && npm run lint", "exitCode": 0, "observation": "No lint errors" }
    ],
    "interactiveChecks": [
      { "action": "Navigate to localhost:3001, verify 2 tabs visible", "observed": "Trade and Analytics tabs visible, no other tabs" },
      { "action": "Click Trade tab, verify planner + open trades visible", "observed": "Both sections visible on single page" },
      { "action": "Verify execute button styling", "observed": "Green background, bold text, prominent appearance" }
    ]
  },
  "tests": {
    "added": []
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature requires backend changes not yet implemented
- Cannot achieve feature within mission boundaries
- Existing bugs block the feature
