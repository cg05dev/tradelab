import api from './client'

export const getTrades = () => api.get('/api/trades')
export const getOpenTrades = () => api.get('/api/trades/open')
export const getClosedTrades = (params?: Record<string, unknown>) => api.get('/api/trades/closed', { params })
export const getClosedTradesCount = () => api.get('/api/trades/closed/count')
export const getTradeHistory = () => api.get('/api/trades')
export const addTrade = (tradeData: unknown) => api.post('/api/trades', tradeData)
export const closeTrade = (tradeIndex: number, exitPrice: number) =>
  api.post('/api/trades/close', { trade_index: tradeIndex, exit_price: exitPrice })
export const partialCloseTrade = (tradeIndex: number, tpPrice: number, tpAllocation: number, tpIndex: number) =>
  api.post('/api/trades/partial-close', {
    trade_index: tradeIndex,
    tp_price: tpPrice,
    tp_allocation: tpAllocation,
    tp_index: tpIndex,
  })
export const stopLossHit = (tradeIndex: number, slPrice: number, slAllocation: number, slIndex: number) =>
  api.post('/api/trades/stop-loss-hit', {
    trade_index: tradeIndex,
    sl_price: slPrice,
    sl_allocation: slAllocation,
    sl_index: slIndex,
  })
export const deleteTrade = (tradeIndex: number) => api.delete(`/api/trades/${tradeIndex}`)
export const clearAllTrades = () => api.delete('/api/trades/clear')
export const importTrades = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/trades/import', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}
