import uuid
import os
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
    Proxy & stream DZI pyramid tile from storage with fast local cache check.
    """
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slide = db.scalars(select(Slide).where(Slide.case_id == case_id)).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found for case")

    # Fast local cache path for 0.001s instant tile rendering
    local_tile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_PYRAMIDS_BUCKET}/{slide.id}/{layer}/{z}/{x_y}.jpg"))
    if os.path.exists(local_tile_path):
        with open(local_tile_path, "rb") as f:
            tile_bytes = f.read()
        return Response(
            content=tile_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=86400",
                "X-Tile-Layer": layer,
                "X-Tile-Zoom": str(z)
            }
        )

    client = get_gcs_client()

    if hasattr(client, "base_dir"):
        tile_path = os.path.join(client.base_dir, settings.GCS_PYRAMIDS_BUCKET, str(slide.id), layer, str(z), f"{x_y}.jpg")
        if os.path.exists(tile_path):
            with open(tile_path, "rb") as f:
                tile_bytes = f.read()
            return Response(
                content=tile_bytes,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=86400",
                    "X-Tile-Layer": layer,
                    "X-Tile-Zoom": str(z)
                }
            )
    else:
        blob_path = f"{slide.id}/{layer}/{z}/{x_y}.jpg"
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
            print(f"[Tiles Router Note] Storage fetch error: {e}")

    # Return clean HTTP 404 if tile is missing
    raise HTTPException(status_code=404, detail="Tile missing")
