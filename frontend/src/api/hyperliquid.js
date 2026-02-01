import axios from 'axios';

const API_URL = 'http://localhost:8000';

// Get Hyperliquid connection status
export const getHyperliquidStatus = () => {
  return axios.get(`${API_URL}/api/hyperliquid/status`);
};

// Get current price for a coin
export const getHyperliquidPrice = (coin) => {
  return axios.get(`${API_URL}/api/hyperliquid/price/${coin}`);
};

// Get open positions
export const getHyperliquidPositions = (coin) => {
  const url = coin 
    ? `${API_URL}/api/hyperliquid/positions?coin=${coin}`
    : `${API_URL}/api/hyperliquid/positions`;
  return axios.get(url);
};

// Get WebSocket price
export const getHyperliquidWsPrice = () => {
  return axios.get(`${API_URL}/api/hyperliquid/ws-price`);
};

// Get available assets with max leverage
export const getHyperliquidAssets = () => {
  return axios.get(`${API_URL}/api/hyperliquid/assets`);
};

// Place an order on Hyperliquid
export const placeHyperliquidOrder = (orderData) => {
  return axios.post(`${API_URL}/api/hyperliquid/order`, orderData, {
    headers: {
      'Content-Type': 'application/json',
    },
  });
};
