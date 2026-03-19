# TradeLab - Plan Critique and Revised Roadmap

Last updated: 2026-03-18

## 1) Captured Intent From Your Draft

You want TradeLab to become a **smart perp routing app** where a user sets up a trade once, clicks execute, and the system chooses the best route/venue based on real execution quality (fees, liquidity depth, slippage, availability), eventually powered by ML.

## 2) Critique of Current Rough Plan

## Strong ideas to keep

- Start from existing foundation (already integrated with Hyperliquid)
- Research DEX quality by execution factors, not hype
- Move toward browser app for wallet-native UX
- Start with one chain to reduce complexity

## Areas that need revision

1. **ML too early**  
   If started now, it will be mostly guesswork due to limited labeled routing outcomes.  
   Better: deterministic scoring engine first, collect data, then ML in shadow mode.

2. **Native token too early**  
   This adds major legal/compliance/ops burden before PMF and can slow execution dramatically.

3. **Cross-chain + bridge too early**  
   Bridge/risk/swap path complexity can derail core routing quality if done before single-chain reliability.

4. **Compliance underweighted**  
   Perp UX must treat jurisdiction gating and policy controls as first-class, not optional.

## 3) Revised Plan (Practical Sequence)

## Phase 0 — Foundation Hardening (now)

- Normalize backend architecture (separate API/service/integration layers)
- Introduce venue adapter interface (`quote`, `fees`, `liquidity`, `execute`, `close`)
- Replace CSV/JSON with DB-backed event model for orders/fills/routes
- Add observability (structured logs, route decision traces)

## Phase 1 — Browser MVP, Single-Chain, Multi-Venue (deterministic)

- Browser app with wallet-based auth/signing
- Start with **one chain** and 2–3 venues
- Build deterministic routing score from:
  - expected fees
  - expected slippage
  - available liquidity / depth proxy
  - venue availability/policy gating
- Execute through best venue and store route rationale

## Phase 2 — Route Intelligence

- Add backtesting/simulation harness
- Reconcile predicted vs realized execution
- Improve scoring model with dynamic weighting per market regime

## Phase 3 — ML (shadow mode first)

- ML model proposes route while deterministic router still executes
- Compare outcomes and only promote after sustained improvement

## Phase 4 — Multi-chain expansion

- Add second chain only after single-chain reliability KPI is met
- Add bridge/swap paths with strict risk controls and failure handling

## 4) Chain + Venue Direction (Current Best Read)

- **Initial chain direction:** Solana-first is reasonable for UX/cost and your current direction.
- **Immediate venue shortlist for MVP:**
  1. Drift (Solana)
  2. GMX v2 (Arbitrum) as next expansion path
  3. Gains (Arbitrum) as optional secondary route
- Keep Hyperliquid as a benchmark/high-liquidity route where permitted.

## 5) Native Token Recommendation

Recommendation: **defer native token** until after PMF and legal architecture are clear.  
Use stable collateral-first UX initially (e.g., USDC path) to minimize user and compliance complexity.

## 6) Edge Cases That Must Be Designed Upfront

- Venue down/degraded or stale quotes
- Partial fills and re-route logic
- Funding-rate drift between quote and execution
- API latency spikes and timeout fallback behavior
- Jurisdiction-based venue disabling per user/session
- Journal/execution mismatch and idempotent recovery

## 7) Success Criteria for This Vision

1. User can create one intent and execute through best valid venue automatically.
2. Route decision is explainable and persisted.
3. Realized execution beats a simple baseline often enough to justify smart routing.
4. Browser flow works cleanly with wallet connection and policy gating.

## 8) Related Notes

- [[TradeLab - Mental Model]]
- [[TradeLab - Market and Architecture Research (2026-03-18)]]
