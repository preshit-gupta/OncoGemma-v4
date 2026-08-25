from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, field_serializer

class CaseCreate(BaseModel):
    pass

class CaseResponse(BaseModel):
    id: UUID
    created_by: str
    status: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

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

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    class Config:
        from_attributes = True
