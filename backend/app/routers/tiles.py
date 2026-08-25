import uuid
import io
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

@router.get("/{case_id}/tiles/{layer}/{z}/{x_y}.jpg")
def get_tile(
    case_id: uuid.UUID,
    layer: str, # "orig" or "norm"
    z: int,
    x_y: str, # e.g. "0_0"
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """
    Proxy & stream DZI pyramid tile from GCS/storage with auth check and caching headers.
    """
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slide = db.scalars(select(Slide).where(Slide.case_id == case_id)).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found for case")

    # Construct object path: og-{env}-pyramids/{slide_id}/{layer}/{z}/{x}_{y}.jpg
    blob_path = f"{slide.id}/{layer}/{z}/{x_y}.jpg"

    client = get_gcs_client()
    bucket = client.bucket(settings.GCS_PYRAMIDS_BUCKET)
    blob = bucket.blob(blob_path)

    try:
        if blob.exists():
            tile_bytes = blob.download_as_bytes()
            return Response(
                content=tile_bytes,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=86400",
                    "X-Tile-Layer": layer,
                    "X-Tile-Zoom": str(z)
                }
            )
    except Exception as e:
        print(f"[Tiles Router] Storage fetch note: {e}")

    # Fallback / placeholder for test fixtures or ungenerated tiles
    raise HTTPException(status_code=404, detail=f"Tile not found at {blob_path}")
