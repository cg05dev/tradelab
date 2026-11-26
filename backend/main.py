"""
FastAPI Backend for TradeLab
Handles all trading journal logic and data persistence
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

# TRADELAB_LOG_LEVEL=DEBUG shows order/exchange diagnostics
logging.basicConfig(
    level=os.getenv("TRADELAB_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from routers import analytics, calculations, connection, hyperliquid, mode, portfolio, system, trades, webhook  # noqa: E402

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

# The API can trade with the user's API wallet, so only the TradeLab page on this machine may call it:
# - Requests must be addressed to localhost, which blocks DNS rebinding (a web page pointing its own
#   domain at 127.0.0.1) and stops a tunnel from exposing anything but the paths below. Requests
#   carrying proxy headers count as remote even if the proxy rewrote Host to localhost.
# - Requests that change anything must carry X-TradeLab-Client. Browsers only let another site send
#   a custom header after a CORS preflight, which CORS_ORIGINS rejects, so this stops cross-site
#   form posts and fetches.
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
PUBLIC_PATHS = {"/health", "/api/webhook/trade"}  # the webhook checks its own secret
FORWARDING_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip", "cf-connecting-ip")
CLIENT_HEADER = "x-tradelab-client"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6, e.g. [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.split(":")[0] if host.count(":") <= 1 else host


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.path not in PUBLIC_PATHS:
        remote = _hostname(request.headers.get("host", "")) not in LOCAL_HOSTNAMES or any(
            header in request.headers for header in FORWARDING_HEADERS
        )
        if remote:
            return JSONResponse(status_code=403, content={"detail": "TradeLab's API only accepts requests from this computer."})
        if request.method not in SAFE_METHODS and not request.headers.get(CLIENT_HEADER):
            return JSONResponse(status_code=403, content={"detail": f"Missing {CLIENT_HEADER} header."})
    return await call_next(request)

for module in (system, portfolio, mode, trades, analytics, calculations, hyperliquid, connection, webhook):
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
