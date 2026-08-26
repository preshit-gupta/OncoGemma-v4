import uuid
import os
import math
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.db import get_db
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings
from app.core.gcs import get_gcs_client
from app.models.case import Case
from app.models.slide import Slide

router = APIRouter(prefix="/api/v1/cases", tags=["tiles"])

@router.get("/{case_id}/tiles/{layer}/{z}/{filename}")
def get_tile(
    case_id: uuid.UUID,
    layer: str, # "orig" or "norm"
    z: int,
    filename: str, # e.g. "0_0.jpg" or "0_0.png"
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """
    Proxy & stream DZI pyramid tile directly from Real GCP Cloud Storage bucket (oncogemma-dev-pyramids)
    with local disk cache for instant sub-millisecond tile serving.
    Supports both JPEG and PNG format tiles.
    Strict coordinate matching: returns 404 for missing tiles to prevent tile repeating.
    Capped normalized view at 10x (z <= cap_10x_level).
    """
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slide = db.scalars(select(Slide).where(Slide.case_id == case_id)).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found for case")

    stem = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1] or ".png"

    # Dynamic 10x level calculation from slide dimensions
    slide_w = float(getattr(slide, "width_px", 2048) or 2048)
    slide_h = float(getattr(slide, "height_px", 2048) or 2048)
    max_dim = max(slide_w, slide_h)
    slide_max_level = int(math.ceil(math.log2(max_dim))) if max_dim > 0 else 11
    cap_10x_level = max(0, slide_max_level - 2)

    # Local tile cache directory
    local_cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fake_gcs"))
    if not os.path.exists(local_cache_dir):
        local_cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../fake_gcs"))

    slide_dir = os.path.join(local_cache_dir, settings.GCS_PYRAMIDS_BUCKET, str(slide.id))
    
    target_layer = layer
    
    # 10x cap check: normalized DZI pyramid is capped at 10x (z <= cap_10x_level).
    # Beyond 10x level (z > cap_10x_level), automatically serve 'orig' layer tiles.
    if layer == "norm" and z > cap_10x_level:
        target_layer = "orig"

    target_z = z

    # Disable browser caching in dev mode to ensure tile changes reflect immediately
    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Tile-Layer": target_layer,
        "X-Tile-Zoom": str(target_z)
    }

    # 1. Local disk cache check (fast path)
    layer_dir = os.path.join(slide_dir, target_layer)
    for check_ext in [ext, ".png", ".jpg"]:
        tile_path = os.path.join(layer_dir, str(target_z), f"{stem}{check_ext}")
        if os.path.exists(tile_path):
            with open(tile_path, "rb") as f:
                tile_bytes = f.read()
            m_type = "image/png" if check_ext.lower() == ".png" else "image/jpeg"
            return Response(content=tile_bytes, media_type=m_type, headers=no_cache_headers)

    # 2. Fetch directly from Real GCP Cloud Storage Bucket (oncogemma-dev-pyramids)
    try:
        client = get_gcs_client()
        bucket = client.bucket(settings.GCS_PYRAMIDS_BUCKET)
        
        for check_ext in [ext, ".png", ".jpg"]:
            blob_name = f"{slide.id}/{target_layer}/{target_z}/{stem}{check_ext}"
            blob = bucket.blob(blob_name)
            
            if hasattr(blob, "download_as_bytes"):
                try:
                    tile_bytes = blob.download_as_bytes()
                    # Cache locally for future requests
                    os.makedirs(os.path.join(layer_dir, str(target_z)), exist_ok=True)
                    with open(os.path.join(layer_dir, str(target_z), f"{stem}{check_ext}"), "wb") as f:
                        f.write(tile_bytes)
                    m_type = "image/png" if check_ext.lower() == ".png" else "image/jpeg"
                    return Response(content=tile_bytes, media_type=m_type, headers=no_cache_headers)
                except Exception:
                    pass
    except Exception as gcs_err:
        print(f"[Tile Router Warning] GCS fetch note: {gcs_err}")

    # 3. Fallback for 'norm' to 'orig'
    if target_layer == "norm":
        orig_dir = os.path.join(slide_dir, "orig")
        for check_ext in [ext, ".jpg", ".png"]:
            tile_path = os.path.join(orig_dir, str(target_z), f"{stem}{check_ext}")
            if os.path.exists(tile_path):
                with open(tile_path, "rb") as f:
                    tile_bytes = f.read()
                m_type = "image/png" if check_ext.lower() == ".png" else "image/jpeg"
                return Response(content=tile_bytes, media_type=m_type, headers=no_cache_headers)

    # Return HTTP 404 for missing tiles to prevent OpenSeadragon tile duplication/repeating
    raise HTTPException(status_code=404, detail="Tile missing")
