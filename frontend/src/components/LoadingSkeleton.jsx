export function MetricCardSkeleton() {
  return (
    <div className="border border-gray-700/60 rounded p-4 bg-black/50 animate-pulse">
      <div className="h-3 bg-gray-700/50 rounded w-20 mb-2"></div>
      <div className="h-6 bg-gray-700/50 rounded w-24"></div>
    </div>
  )
}

export function TradeCardSkeleton() {
  return (
    <div className="border border-gray-700/60 rounded p-4 bg-black/50 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="h-4 bg-gray-700/50 rounded w-24 mb-2"></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <div className="h-3 bg-gray-700/50 rounded w-16 mb-1"></div>
              <div className="h-4 bg-gray-700/50 rounded w-20"></div>
            </div>
            <div>
              <div className="h-3 bg-gray-700/50 rounded w-16 mb-1"></div>
              <div className="h-4 bg-gray-700/50 rounded w-20"></div>
            </div>
            <div>
              <div className="h-3 bg-gray-700/50 rounded w-16 mb-1"></div>
              <div className="h-4 bg-gray-700/50 rounded w-20"></div>
            </div>
            <div>
              <div className="h-3 bg-gray-700/50 rounded w-16 mb-1"></div>
              <div className="h-4 bg-gray-700/50 rounded w-20"></div>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="h-8 w-16 bg-gray-700/50 rounded"></div>
          <div className="h-8 w-16 bg-gray-700/50 rounded"></div>
        </div>
      </div>
    </div>
  )
}

export function ChartSkeleton() {
  return (
    <div className="border border-gray-700/60 rounded-lg p-4 bg-black/50 animate-pulse">
      <div className="h-4 bg-gray-700/50 rounded w-32 mb-4"></div>
      <div className="h-64 bg-gray-700/30 rounded"></div>
    </div>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* Portfolio Section */}
      <div className="border border-gray-700/60 rounded p-4 bg-black/50 animate-pulse">
        <div className="h-4 bg-gray-700/50 rounded w-24 mb-2"></div>
        <div className="h-8 bg-gray-700/50 rounded w-32"></div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <MetricCardSkeleton key={i} />
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>

      {/* Past Trades */}
      <div className="border border-gray-700/60 rounded p-4 bg-black/50 animate-pulse">
        <div className="h-4 bg-gray-700/50 rounded w-24 mb-4"></div>
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-12 bg-gray-700/30 rounded mb-2"></div>
        ))}
      </div>
    </div>
  )
}

