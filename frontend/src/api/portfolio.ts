import api from './client'
import type { PortfolioResponse } from '../types'

export const getPortfolio = () => api.get<PortfolioResponse>('/portfolio')
export const updatePortfolio = (portfolioSize: number) =>
  api.put('/portfolio', { portfolio_size: portfolioSize })
export const deletePortfolio = () => api.post('/portfolio/reset')
