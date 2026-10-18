from fastapi import APIRouter, HTTPException

from models import ModeUpdateRequest
from storage import _normalize_mode_value, load_mode, save_mode

router = APIRouter(prefix="/api/mode", tags=["mode"])


@router.get("")
def get_mode():
    """Get current trading mode"""
    return {"mode": load_mode()}

@router.post("")
def update_mode(request: ModeUpdateRequest):
    """Update trading mode"""
    normalized_mode = _normalize_mode_value(request.mode)
    if not normalized_mode:
        raise HTTPException(
            status_code=400, 
            detail="Invalid mode '%s'. Valid modes are: paper, live" % request.mode
        )
    save_mode(normalized_mode)
    return {"mode": normalized_mode, "message": f"Mode updated to '{normalized_mode}'"}
