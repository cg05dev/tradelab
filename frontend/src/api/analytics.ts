import api from './client'

export type AnalyticsMetrics = {
  total_pnl?: number
  win_rate?: number
  avg_win?: number
  avg_loss?: number
}

export type PnlSeriesPoint = { date?: string; cumulative_pnl?: number }

export const getAnalyticsMetrics = (timeframe = 'all', mode?: string) =>
  api.get<AnalyticsMetrics>('/api/analytics/metrics', { params: { timeframe, mode } })

export const getAnalyticsOverview = (mode?: string) => getAnalyticsMetrics('all', mode)

export const getPnlSeries = (timeframe = 'all', mode?: string) =>
  api.get<PnlSeriesPoint[]>('/api/analytics/pnl-series', { params: { timeframe, mode } })
