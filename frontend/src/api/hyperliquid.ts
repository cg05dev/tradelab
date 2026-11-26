import api from './client'
import type { HyperliquidOrderRequest, HyperliquidOrderResponse } from '../types'

export const getHyperliquidStatus = () => api.get('/api/hyperliquid/status')
export const getHyperliquidPrice = (coin: string) => api.get(`/api/hyperliquid/price/${coin}`)
export const getHyperliquidPositions = (coin?: string) => {
  const url = coin ? `/api/hyperliquid/positions?coin=${coin}` : '/api/hyperliquid/positions'
  return api.get(url)
}
export const getHyperliquidWsPrice = () => api.get('/api/hyperliquid/ws-price')
export const getHyperliquidAssets = () => api.get('/api/hyperliquid/assets')
export const placeHyperliquidOrder = (orderData: HyperliquidOrderRequest) => api.post<HyperliquidOrderResponse>('/api/hyperliquid/order', orderData)
export type ClosePositionResponse = {
  status: string
  coin: string
  closed_size: number
  fill_price?: number | null
  message?: string
  // The journal trade after its close fills were applied (when trade_index was sent)
  journal?: { trade_index: number; status: string; exit_price: number | null; pnl: number | null } | null
}
// `size` is in coin units; omit it to close the whole position. With `tradeIndex`, the backend
// journals the close from its actual fills.
export const closeHyperliquidPosition = (coin: string, size?: number, tradeIndex?: number) =>
  api.post<ClosePositionResponse>(`/api/hyperliquid/close/${coin}`, {
    ...(size ? { size } : {}),
    ...(tradeIndex != null ? { trade_index: tradeIndex } : {}),
  })
// Fee rates and stop slippage the planner sizes with: the connected account's, else Hyperliquid's base tier
export type FeeRates = { taker: number; maker: number; stop_slippage: number; source: 'account' | 'default' }
export const getFeeRates = () => api.get<FeeRates>('/api/hyperliquid/fees')
// Apply new Hyperliquid fills (TP/SL hits) to the open live journal trades now
export const syncHyperliquidFills = () =>
  api.post<{ synced: boolean; updated: number[]; closed: number[] }>('/api/hyperliquid/sync')

// Mode API
export interface ModeResponse { mode: 'planning' | 'live' }
export const getMode = () => api.get<ModeResponse>('/api/mode')
export interface SetModeRequest { mode: 'planning' | 'live' }
export const setMode = (mode: 'planning' | 'live') => api.post<ModeResponse>('/api/mode', { mode })

