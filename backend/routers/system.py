from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check():
    """Health check endpoint for faster startup detection"""
    return {"status": "ok"}

