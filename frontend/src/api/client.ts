import axios, { AxiosInstance } from 'axios'

const DEFAULT_API_BASE_URL = ''
const API_BASE_URL = import.meta.env.VITE_API_URL || DEFAULT_API_BASE_URL

// Verbose request/response logging only in `npm run dev`
const debugLog = import.meta.env.DEV ? console.debug : () => {}

debugLog(`[API] Base URL: ${API_BASE_URL}`)

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use(
  config => {
    debugLog(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.data)
    return config
  },
  error => {
    console.error('[API Request Error]', error)
    return Promise.reject(error)
  },
)

api.interceptors.response.use(
  response => {
    debugLog(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url}`, response.status, response.data)
    return response
  },
  error => {
    console.error('[API Response Error]', error.config?.method?.toUpperCase(), error.config?.url, error.response?.status, error.response?.data)
    return Promise.reject(error)
  },
)

export default api
