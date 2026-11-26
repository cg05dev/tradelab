// Hyperliquid's maintenance margin for BTC: half the initial margin at its 40x maximum leverage.
// Other assets have their own, so for them the liquidation price is an estimate. The backend uses
// the same value (backend/risk.py).
const MAINTENANCE_MARGIN = 0.0125

// Where an isolated position opened at `entry` with `leverage` is liquidated
export function liquidationPrice(entry: number, leverage: number, direction?: string): number {
  const threshold = 1 / leverage - MAINTENANCE_MARGIN
  return direction?.toLowerCase() === 'short' ? entry * (1 + threshold) : entry * (1 - threshold)
}
