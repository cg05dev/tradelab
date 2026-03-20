import api from './client'
import type { PortfolioResponse } from '../types'

export const getPortfolio = (mode?: string) => api.get<PortfolioResponse>('/api/portfolio', { params: { mode } })
export const updatePortfolio = (portfolioSize: number, mode?: string) =>
  api.put('/api/portfolio', { portfolio_size: portfolioSize }, { params: { mode } })
export const deletePortfolio = () => api.post('/api/portfolio/reset')
