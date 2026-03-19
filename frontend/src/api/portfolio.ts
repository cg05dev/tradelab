import api from './client'
import type { PortfolioResponse } from '../types'

export const getPortfolio = () => api.get<PortfolioResponse>('/api/portfolio')
export const updatePortfolio = (portfolioSize: number) =>
  api.put('/api/portfolio', { portfolio_size: portfolioSize })
export const deletePortfolio = () => api.post('/api/portfolio/reset')
