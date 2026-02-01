import { useState, useEffect } from 'react';
import { getHyperliquidPrice, getHyperliquidStatus } from '../api/hyperliquid';

export default function BtcPriceTicker() {
  const [price, setPrice] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Check Hyperliquid status
    const checkStatus = async () => {
      try {
        const res = await getHyperliquidStatus();
        setStatus(res.data);
      } catch (err) {
        setStatus({ enabled: false });
      }
    };

    // Fetch BTC price
    const fetchPrice = async () => {
      if (!status?.enabled) return;
      
      try {
        const res = await getHyperliquidPrice('BTC');
        setPrice(res.data);
        setError(null);
      } catch (err) {
        setError('Failed to fetch price');
      } finally {
        setLoading(false);
      }
    };

    checkStatus();

    // Poll price every 2 seconds
    const interval = setInterval(fetchPrice, 2000);
    fetchPrice(); // Initial fetch

    return () => clearInterval(interval);
  }, [status?.enabled]);

  if (!status?.enabled) {
    return null;
  }

  return (
    <div className="bg-black/50 border border-gray-700/60 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-500 mb-0.5">BTC Price (Hyperliquid)</p>
          <p className="text-2xl font-medium text-white">
            {loading ? (
              <span className="animate-pulse">Loading...</span>
            ) : error ? (
              <span className="text-red-400 text-sm">{error}</span>
            ) : price?.price ? (
              `$${price.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            ) : (
              'N/A'
            )}
          </p>
        </div>
        <div className="flex flex-col items-end">
          <span className={`text-xs px-2 py-1 rounded ${status?.connected ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'}`}>
            {status?.connected ? 'Connected' : 'Disconnected'}
          </span>
          <span className="text-xs text-gray-500 mt-1">
            {price?.timestamp ? new Date(price.timestamp).toLocaleTimeString() : ''}
          </span>
        </div>
      </div>
    </div>
  );
}
