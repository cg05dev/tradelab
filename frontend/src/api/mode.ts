import api from './client'

export type TradingMode = 'paper' | 'live'

export const getMode = () => api.get<{ mode: TradingMode }>('/api/mode')
export const setMode = (mode: TradingMode) => api.post<{ mode: TradingMode }>('/api/mode', { mode })
