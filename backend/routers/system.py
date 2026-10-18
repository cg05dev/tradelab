from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/")
def read_root():
    return {"message": "TradeLab API"}

@router.get("/health")
def health_check():
    """Health check endpoint for faster startup detection"""
    return {"status": "ok"}

@router.post("/api/shutdown")
def shutdown():
    """Shutdown endpoint (called when frontend closes)"""
    # Note: This is informational - actual shutdown should be done via the launcher
    return {"message": "Shutdown signal received"}
