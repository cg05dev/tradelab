"""TradeLab: the API (trading journal, Hyperliquid integration) and, once built, the app itself.

Run with `python main.py`, or `python start.py` from the repository root, which also installs and
builds what's needed. It listens on localhost only (see the local-only middleware below).
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

# TRADELAB_LOG_LEVEL=DEBUG shows order/exchange diagnostics
logging.basicConfig(
    level=os.getenv("TRADELAB_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import backup  # noqa: E402
import fees  # noqa: E402
import fill_sync  # noqa: E402
import paper_sim  # noqa: E402
import storage  # noqa: E402
from hyperliquid_client import hl_client  # noqa: E402
from routers import analytics, connection, hyperliquid, mode, portfolio, system, trades  # noqa: E402

logger = logging.getLogger(__name__)

# How often open live trades are checked against Hyperliquid fills (TP/SL hits on the exchange)
FILL_SYNC_SECONDS = float(os.getenv("TRADELAB_FILL_SYNC_SECONDS", "15"))
# How often open paper trades are checked against mainnet prices
PAPER_SIM_SECONDS = float(os.getenv("TRADELAB_PAPER_SIM_SECONDS", "5"))


async def _sync_fills_forever():
    while True:
        try:
            if hl_client.enabled:
                await asyncio.to_thread(fill_sync.sync, hl_client)
        except Exception as e:
            logger.warning(f"Fill sync failed, retrying in {FILL_SYNC_SECONDS:g}s: {e}")
        await asyncio.sleep(FILL_SYNC_SECONDS)


async def _back_up_forever():
    """Back up the database when the last backup is TRADELAB_BACKUP_HOURS old, checking hourly, so
    restarting the app often doesn't crowd older backups out."""
    while True:
        try:
            await asyncio.to_thread(backup.back_up_if_due, storage.DB_FILE)
        except Exception:
            logger.exception("Database backup failed; retrying in an hour")
        await asyncio.sleep(min(3600, backup.BACKUP_HOURS * 3600))


async def _simulate_paper_forever():
    market = paper_sim.MainnetMarket()
    while True:
        try:
            await asyncio.to_thread(lambda: paper_sim.step(market, fees.current_rates(hl_client)))
        except Exception as e:
            logger.warning(f"Paper simulation failed, retrying in {PAPER_SIM_SECONDS:g}s: {e}")
        await asyncio.sleep(PAPER_SIM_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if FILL_SYNC_SECONDS > 0:
        tasks.append(asyncio.create_task(_sync_fills_forever()))
    if PAPER_SIM_SECONDS > 0:
        tasks.append(asyncio.create_task(_simulate_paper_forever()))
    if backup.BACKUP_HOURS > 0:
        tasks.append(asyncio.create_task(_back_up_forever()))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="TradeLab API", lifespan=lifespan)

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
#   domain at 127.0.0.1) and stops a tunnel from exposing it. Requests
#   carrying proxy headers count as remote even if the proxy rewrote Host to localhost.
# - Requests that change anything must carry X-TradeLab-Client. Browsers only let another site send
#   a custom header after a CORS preflight, which CORS_ORIGINS rejects, so this stops cross-site
#   form posts and fetches.
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
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
    remote = _hostname(request.headers.get("host", "")) not in LOCAL_HOSTNAMES or any(
        header in request.headers for header in FORWARDING_HEADERS
    )
    if remote:
        return JSONResponse(status_code=403, content={"detail": "TradeLab's API only accepts requests from this computer."})
    if request.method not in SAFE_METHODS and not request.headers.get(CLIENT_HEADER):
        return JSONResponse(status_code=403, content={"detail": f"Missing {CLIENT_HEADER} header."})
    return await call_next(request)

for module in (system, portfolio, mode, trades, analytics, hyperliquid, connection):
    app.include_router(module.router)

# The built app (`npm run build`), served from the same origin as the API. In development the Vite dev
# server serves it instead and proxies /api here.
FRONTEND_DIST = Path(os.getenv("TRADELAB_FRONTEND_DIST", Path(__file__).resolve().parent.parent / "frontend" / "dist"))


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serve a built file, or the app's index.html for its own routes (/trade, /settings, ...)."""
    if path == "api" or path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    dist = FRONTEND_DIST.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=404, content={
            "detail": "The app isn't built yet. Run `python start.py` from the repository root, "
                      "or `npm run build` in frontend/.",
        })
    file = (dist / path).resolve()
    if path and file.is_file() and file.is_relative_to(dist):
        # Built assets have content hashes in their names, so they can be cached for good
        cache = "public, max-age=31536000, immutable" if file.parent.name == "assets" else "no-cache"
        return FileResponse(file, headers={"Cache-Control": cache})
    if "." in path.rsplit("/", 1)[-1]:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})  # a missing file, not a route
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TRADELAB_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
