"""
FastAPI Backend for TradeLab
Handles all trading journal logic and data persistence
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from routers import analytics, calculations, hyperliquid, mode, portfolio, system, trades, webhook  # noqa: E402

app = FastAPI(title="TradeLab API")

# CORS middleware for React frontend. The Vite dev server proxies /api, so only
# origins that call the API directly need to be listed here.
DEFAULT_CORS_ORIGINS = "http://localhost:3001,http://127.0.0.1:3001"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("TRADELAB_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (system, portfolio, mode, trades, analytics, calculations, hyperliquid, webhook):
    app.include_router(module.router)

if __name__ == "__main__":
    import uvicorn
    # Optimize for faster startup - use single worker, disable access log
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8000,
        log_level="warning",  # Reduce logging overhead
        access_log=False  # Disable access logs for faster startup
    )
