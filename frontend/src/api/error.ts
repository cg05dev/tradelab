import type { AxiosError } from 'axios'

export type ApiErrorResponse = {
  detail?: string
  error?: string
  mode?: string
  reason?: string
}

export function getErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const axiosError = error as AxiosError<ApiErrorResponse>
  
  // Check for mode_blocked error (from frontend) or API response
  if (axiosError.response?.data) {
    // Handle detail field - can be string, array, or object
    const detail = axiosError.response?.data?.detail
    if (detail) {
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        return (detail as any[])
          .map((item: any) => (typeof item === 'string' ? item : item?.msg || item?.message || JSON.stringify(item)))
          .join('. ')
      }
      if (typeof detail === 'object') {
        const d = detail as any
        return d?.msg || d?.message || JSON.stringify(detail)
      }
    }
    // Fallback to reason or error fields
    return axiosError.response?.data?.reason
      || axiosError.response?.data?.error
      || fallback
  }
  
  // Check for mode_blocked error object (from frontend throw)
  if (typeof error === 'object' && error !== null) {
    const errorObj = error as { error?: string; mode?: string; reason?: string }
    if (errorObj.error === 'mode_blocked') {
      return errorObj.reason || `Trading is blocked in ${errorObj.mode || 'unknown'} mode`
    }
  }
  
  // Fallback to Error message
  return error instanceof Error ? error.message : fallback
}
