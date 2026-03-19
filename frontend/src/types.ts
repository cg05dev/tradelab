export type PortfolioResponse = { portfolio_size?: number }
export type AnalyticsOverview = { total_pnl?: number; win_rate?: number; profit_factor?: number }
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
}
export type Trade = {
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
}
export type HyperliquidOrderRequest = { coin: string; is_buy: boolean; margin_amount: number; leverage: number; entry_price: number; take_profits: TakeProfit[]; stop_losses: TakeProfit[]; is_isolated: boolean }
