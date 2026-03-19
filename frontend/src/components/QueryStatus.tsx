type QueryStatusProps = {
  isLoading?: boolean
  isError?: boolean
  error?: string
  emptyMessage?: string
  loadingMessage?: string
  className?: string
}

export default function QueryStatus({
  isLoading,
  isError,
  error,
  emptyMessage = 'No data available',
  loadingMessage = 'Loading...',
  className = '',
}: QueryStatusProps) {
  if (isLoading) {
    return <div className={`text-center py-8 text-neutral-500 text-sm ${className}`}>{loadingMessage}</div>
  }

  if (isError) {
    return <div className={`text-center py-8 text-red-400 text-sm ${className}`}>{error || 'Unable to load data'}</div>
  }

  return <div className={`text-center py-8 text-neutral-500 text-sm ${className}`}>{emptyMessage}</div>
}
