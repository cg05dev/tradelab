import type { AxiosError } from 'axios'

export type ApiErrorResponse = {
  detail?: string
  error?: string
  mode?: string
  reason?: string
}

export function getErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const axiosError = error as AxiosError<ApiErrorResponse>
  return axiosError.response?.data?.detail
    || axiosError.response?.data?.reason
    || axiosError.response?.data?.error
    || (error instanceof Error ? error.message : fallback)
}
