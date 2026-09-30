import api from './client'

export type AnalyticsMetrics = {
  total_pnl?: number
  win_rate?: number
  avg_win?: number
  avg_loss?: number
  profit_factor?: number | null
  max_drawdown?: number
  trade_count?: number
  win_count?: number
  loss_count?: number
}

export type PnlSeriesPoint = { date?: string; asset?: string; pnl?: number; cumulative_pnl?: number }

export const getAnalyticsMetrics = (timeframe = 'all', mode?: string) =>
  api.get<AnalyticsMetrics>('/api/analytics/metrics', { params: { timeframe, mode } })

export const getAnalyticsOverview = (mode?: string) => getAnalyticsMetrics('all', mode)

export const getPnlSeries = (timeframe = 'all', mode?: string) =>
  api.get<PnlSeriesPoint[]>('/api/analytics/pnl-series', { params: { timeframe, mode } })
