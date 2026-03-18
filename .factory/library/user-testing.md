# User Testing

Testing surface, resource cost classification, and validation notes.

**What belongs here:** Testing surface definitions, resource constraints, isolation strategies, gotchas discovered during validation.
**What does NOT belong here:** Service commands (use `services.yaml`), general architecture (use `architecture.md`).

---

## Testing Surface

| Surface | Resource Cost | Notes |
|---------|---------------|-------|
| Browser app | Low | Frontend only; fast to load |
| Backend API | Low | FastAPI; quick startup |
| Hyperliquid execution | High | Requires live credentials; use planning mode for most tests |
| Full trading flow | Medium | Backend + frontend + mode interactions |

## Isolation Strategy

- **Planning mode tests**: Safe to run without Hyperliquid credentials; no live orders.
- **Live mode tests**: Require Hyperliquid testnet or mainnet credentials; use sparingly.
- **Cross-area flows**: Test planning mode first; live mode only for critical paths.

## Testing Constraints

- Browser automation required for UI validation.
- Backend must be running for API calls.
- Frontend dev server must be running for browser tests.

## Gotchas

- Hyperliquid API has rate limits; avoid rapid repeated calls in tests.
- Mode state persists across backend restarts; reset to planning before tests if needed.
