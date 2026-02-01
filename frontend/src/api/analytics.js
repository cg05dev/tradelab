import api from './client'

export const getAnalyticsOverview = () => api.get('/api/analytics/overview')

