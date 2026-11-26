// Coin prices span from fractions of a cent to six figures, so a fixed number of decimals either
// shows a sub-$1 coin as "$0" or BTC as "$100,000.00000". Show 5 significant figures, the way
// Hyperliquid quotes prices, but never drop digits before the decimal point: BTC stays whole dollars.
const PRICE_SIG_FIGS = 5
const MAX_PRICE_DECIMALS = 8

export function formatPrice(value?: number | null, empty = '-'): string {
  if (value == null || !Number.isFinite(value)) return empty
  if (value === 0) return '$0'
  const magnitude = Math.floor(Math.log10(Math.abs(value)))
  const decimals = Math.min(Math.max(PRICE_SIG_FIGS - 1 - magnitude, 0), MAX_PRICE_DECIMALS)
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: decimals })}`
}
