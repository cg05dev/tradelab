// source "manual": paper mode's balance, entered by the user.
// source "hyperliquid": the live account's value (stale if Hyperliquid couldn't be reached; null
//   portfolio_size if it hasn't been fetched yet).
// source "none": live mode with no account connected (null portfolio_size).
export type PortfolioResponse = {
  portfolio_size?: number | null
  source?: 'hyperliquid' | 'manual' | 'none'
  stale?: boolean
  withdrawable?: number
  updated_at?: string
  sync_error?: string
}
export type AnalyticsOverview = { total_pnl?: number; win_rate?: number; avg_win?: number; avg_loss?: number; profit_factor?: number | null }
export type ApiError = { response?: { data?: { detail?: string } } }
export type HyperliquidAsset = { symbol: string; max_leverage: number }
export type TakeProfit = { price: number; allocation: number }
export type TradeDetails = {
  positionSize: number
  positionSizeDollars: number
  marginRequired: number
  positionValue: number
  liquidationPrice: number
  currentPrice: number
  estimatedProfit: number
  estimatedLoss: number
  riskRewardRatio: number
  tpProfits: Array<{ index: number; price: number; allocation: number; profit: number }>
  isStopLossValid?: boolean
}
export type Trade = {
  id?: number | string
  index?: number
  _index?: number
  Asset?: string
  Direction?: string
  Entry?: number
  Exit_Price?: number
  Position_Size?: number
  Margin?: number
  Leverage?: number
  SL?: number
  SL_Hit?: boolean
  SL_Price?: number
  TPs?: string
  SLs?: string
  Hit_TPs?: string
  Status?: string
  Hold_Time?: string
  Confirmations?: string
  Thesis?: string
  Date?: string
  'P&L'?: number
}
// Allocations in API requests and stored trades are fractions of the position (0-1), not percentages
export type HyperliquidOrderRequest = { coin: string; is_buy: boolean; margin_amount: number; leverage: number; entry_price: number; take_profits: TakeProfit[]; stop_losses: TakeProfit[]; is_isolated: boolean }
export type HyperliquidOrderResponse = {
  status: 'success' | 'partial'
  order_id?: number | null
  // Every order placed for the trade; sent back when journaling it so its fills are credited to it
  order_ids?: { entry?: number | null; take_profits: (number | null)[]; stop_losses: (number | null)[] }
  requested_size: number
  filled_size: number
  avg_price: number
  notional: number
  margin_used: number
  leverage: number
  warnings: string[]
  message: string
}
export type AnalyticsMetrics = { total_pnl?: number; win_rate?: number; avg_win?: number; avg_loss?: number }
export type PnlSeriesPoint = { date?: string; cumulative_pnl?: number }
