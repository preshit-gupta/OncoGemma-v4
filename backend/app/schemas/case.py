from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class CaseCreate(BaseModel):
    pass

class CaseResponse(BaseModel):
    id: UUID
    created_by: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class SlideUploadUrlRequest(BaseModel):
    filename: str
    size_bytes: int
    content_type: str = "application/octet-stream"

class SlideUploadUrlResponse(BaseModel):
    upload_url: str
    gcs_uri: str

class SlideFinalizeRequest(BaseModel):
    gcs_uri: str
    client_sha256: str | None = None

class CaseDetailResponse(BaseModel):
    id: UUID
    created_by: str
    status: str
    created_at: datetime
    slides: list[dict] = []
    stages: list[dict] = []

    class Config:
        from_attributes = True
