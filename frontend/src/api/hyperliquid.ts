import api from './client'
import type { HyperliquidOrderRequest } from '../types'

export const getHyperliquidStatus = () => api.get('/api/hyperliquid/status')
export const getHyperliquidPrice = (coin: string) => api.get(`/api/hyperliquid/price/${coin}`)
export const getHyperliquidPositions = (coin?: string) => {
  const url = coin ? `/api/hyperliquid/positions?coin=${coin}` : '/api/hyperliquid/positions'
  return api.get(url)
}
export const getHyperliquidWsPrice = () => api.get('/api/hyperliquid/ws-price')
export const getHyperliquidAssets = () => api.get('/api/hyperliquid/assets')
export const placeHyperliquidOrder = (orderData: HyperliquidOrderRequest) => api.post('/api/hyperliquid/order', orderData)
export const closeHyperliquidPosition = (coin: string) => api.post(`/api/hyperliquid/close/${coin}`, {})

