# TradeLab - Market and Architecture Research (2026-03-18)

Snapshot date: 2026-03-18

## 1) Perp Venue Snapshot (Decision-Oriented)

| Venue | Focus Chain | Notes for routing | Integration maturity |
|---|---|---|---|
| Drift | Solana | Strong Solana perp venue with useful market stats and API surface for routing signals | High |
| GMX v2 | Arbitrum | Strong liquidity ecosystem and mature API/data endpoints for market state | High |
| Gains | Arbitrum/Polygon | Useful API/event surface; Arbitrum side stronger than Polygon in current snapshot | Medium-High |
| Hyperliquid | HL chain | Very deep perp liquidity benchmark and robust API; should remain strategic route where permitted | High |
| Sei candidates (e.g., Vortex) | Sei | Production-grade integration surface less clear in current documentation | Unclear |

## 2) Chain Direction Snapshot

- **Solana:** strong candidate for first-chain UX and cost profile
- **Arbitrum:** best near-term EVM expansion target
- **Cross-chain from day 1:** not recommended due to bridge/risk complexity

## 3) Compliance / Geo Reality

Across major perp interfaces, geo restrictions and anti-circumvention terms are common.  
Implication: routing availability must support jurisdiction-aware controls at product level.

## 4) Native Token Assessment

Potential benefits exist (incentives, ecosystem control), but early launch creates major legal and operational overhead.  
Recommendation at this stage: **defer token**, prioritize core route quality and PMF.

## 5) Browser Architecture Direction

- Move from desktop-local assumptions to browser wallet-first flow
- Support Solana wallet standards + EVM wallet standards cleanly
- Keep custody simple initially (non-custodial signatures), add deeper wallet abstraction later if needed

## 6) What We Know vs Unknown

## Known with reasonable confidence

- Current app can execute and journal Hyperliquid trades end-to-end
- Existing architecture is good for prototyping but not sufficient for robust multi-venue routing
- One-chain-first approach is the right complexity management move

## Unknown / needs follow-up

- Final launch jurisdiction policy
- Exact venue list allowed per jurisdiction
- Normalized cross-venue depth/slippage methodology for production ranking
- Whether Sei venues should be near-term scope or deferred

## 7) Operating Conclusion

Best next step is **not** “build ML now.”  
Best next step is to build a **deterministic routing platform + data pipeline** so ML can later be evidence-driven.

## 8) Source References

- DefiLlama derivatives chain overview: https://defillama.com/derivatives/chains
- Drift data API docs: https://docs.drift.trade/developers/data-api
- Drift data API playground: https://data.api.drift.trade/playground/json
- GMX API overview: https://docs.gmx.io/docs/api/overview/
- GMX markets API docs: https://docs.gmx.io/docs/api/rest-api/markets/
- Gains integrator backend docs: https://docs.gains.trade/developer/integrators/backend.md
- Solana fees docs: https://solana.com/docs/core/fees
- Arbitrum gas/fees docs: https://docs.arbitrum.io/how-arbitrum-works/deep-dives/gas-and-fees
- L2BEAT scaling costs: https://l2beat.com/scaling/costs
- Hyperliquid terms: https://app.hyperliquid.xyz/terms
- dYdX terms: https://www.dydx.xyz/legal/terms-of-use
- Jupiter terms: https://dev.jup.ag/legal/terms-of-use
