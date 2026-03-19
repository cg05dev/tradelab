import api from './client'
import type { AnalyticsOverview } from '../types'

export const getAnalyticsOverview = () => api.get<AnalyticsOverview>('/api/analytics/overview')
