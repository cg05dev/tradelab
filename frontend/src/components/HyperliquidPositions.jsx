import { useState, useEffect } from 'react';
import { getHyperliquidPositions, getHyperliquidStatus } from '../api/hyperliquid';

export default function HyperliquidPositions() {
  const [positions, setPositions] = useState([]);
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

    // Fetch positions
    const fetchPositions = async () => {
      if (!status?.enabled) return;
      
      try {
        setLoading(true);
        const res = await getHyperliquidPositions();
        setPositions(res.data.positions || []);
        setError(null);
      } catch (err) {
        setError('Failed to fetch positions');
        console.error('Error fetching positions:', err);
      } finally {
        setLoading(false);
      }
    };

    checkStatus();

    // Poll positions every 5 seconds
    const interval = setInterval(fetchPositions, 5000);
    fetchPositions(); // Initial fetch

    return () => clearInterval(interval);
  }, [status?.enabled]);

  if (!status?.enabled) {
    return null;
  }

  if (loading && positions.length === 0) {
    return (
      <div className="bg-black/50 border border-gray-700/60 rounded-lg px-4 py-3">
        <p className="text-xs text-gray-500 mb-0.5">Hyperliquid Positions</p>
        <p className="text-sm text-gray-400 animate-pulse">Loading positions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-black/50 border border-gray-700/60 rounded-lg px-4 py-3">
        <p className="text-xs text-gray-500 mb-0.5">Hyperliquid Positions</p>
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="bg-black/50 border border-gray-700/60 rounded-lg px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-gray-500">Hyperliquid Positions</p>
          <span className="text-xs text-gray-500">0 positions</span>
        </div>
        <p className="text-sm text-gray-400">No open positions</p>
        <p className="text-xs text-gray-600 mt-1">
          Connect your Hyperliquid wallet to see live positions
        </p>
      </div>
    );
  }

  return (
    <div className="bg-black/50 border border-gray-700/60 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500">Hyperliquid Positions</p>
        <span className="text-xs text-gray-500">{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
      </div>
      
      <div className="space-y-3">
        {positions.map((pos, idx) => (
          <div key={idx} className="border border-gray-700/40 rounded p-3 bg-black/30">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-white">{pos.coin}</span>
              <span className={`text-sm font-medium ${pos.size > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {pos.size > 0 ? 'LONG' : 'SHORT'} {Math.abs(pos.size).toFixed(4)}
              </span>
            </div>
            
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <p className="text-gray-500">Entry Price</p>
                <p className="text-white">${pos.entry_price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
              <div>
                <p className="text-gray-500">Position Value</p>
                <p className="text-white">${pos.position_value?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
              <div>
                <p className="text-gray-500">Unrealized PnL</p>
                <p className={pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Liquidation</p>
                <p className="text-orange-400">
                  {pos.liquidation_price ? `$${pos.liquidation_price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A'}
                </p>
              </div>
            </div>
            
            {pos.margin_used > 0 && (
              <div className="mt-2 pt-2 border-t border-gray-700/40">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Margin Used</span>
                  <span className="text-gray-400">${pos.margin_used?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-xs mt-1">
                  <span className="text-gray-500">Max Leverage</span>
                  <span className="text-gray-400">{pos.max_leverage?.toFixed(1)}x</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
