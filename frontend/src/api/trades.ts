import api from './client'

export const getOpenTrades = (mode?: string) => api.get('/api/trades/open', { params: mode ? { mode } : undefined })
export const getClosedTrades = (params?: Record<string, unknown>) => api.get('/api/trades/closed', { params })
export const addTrade = (tradeData: unknown, mode?: 'paper' | 'live') => {
  const params = mode ? { mode } : undefined
  return api.post('/api/trades', tradeData, { params })
}
export const closeTrade = (tradeIndex: number, exitPrice: number, mode?: string) =>
  api.post('/api/trades/close', { trade_index: tradeIndex, exit_price: exitPrice }, { params: mode ? { mode } : undefined })

