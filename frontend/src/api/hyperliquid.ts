import api from './client'
import type { HyperliquidOrderRequest, HyperliquidOrderResponse } from '../types'

export const getHyperliquidPrice = (coin: string) => api.get(`/api/hyperliquid/price/${coin}`)
export const getHyperliquidAssets = () => api.get('/api/hyperliquid/assets')
// The connected account's open positions, with Hyperliquid's own liquidation price
export type HyperliquidPosition = { coin: string; size: number; liquidation_price: number | null }
export const getHyperliquidPositions = () => api.get<{ positions: HyperliquidPosition[] }>('/api/hyperliquid/positions')
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
import type { FeeRates } from '../trading'
export type { FeeRates }
export const getFeeRates = () => api.get<FeeRates>('/api/hyperliquid/fees')
// Apply new Hyperliquid fills (TP/SL hits) to the open live journal trades now
export const syncHyperliquidFills = () =>
  api.post<{ synced: boolean; updated: number[]; closed: number[] }>('/api/hyperliquid/sync')


