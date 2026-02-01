import api from './client'

export const getPortfolio = () => api.get('/api/portfolio')
export const updatePortfolio = (portfolioSize) => 
  api.put('/api/portfolio', { portfolio_size: portfolioSize })
export const deletePortfolio = () => api.post('/api/portfolio/reset')

