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
// Hyperliquid's positions compared with the open live journal trades, coin by coin
export type ReconcileIssue = {
  coin: string
  kind: 'untracked' | 'missing' | 'mismatch'
  exchange_size: number
  journal_size: number
  trade_ids: number[]
  // Coin units (negative = short) that adding to the journal would fix; 0 if adding can't fix it
  untracked_size: number
  message: string
}
export const reconcilePositions = () => api.get<{ in_sync: boolean; issues: ReconcileIssue[] }>('/api/hyperliquid/reconcile')
// Add the part of a position the journal doesn't account for as a new open live trade
export const adoptPosition = (coin: string) =>
  api.post<{ trade_index: number; coin: string; size: number; entry_price: number }>(`/api/hyperliquid/reconcile/${encodeURIComponent(coin)}/adopt`)
