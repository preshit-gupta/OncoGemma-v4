from datetime import datetime
from pydantic import BaseModel

class AuditEventResponse(BaseModel):
    id: int
    case_id: str | None
    actor: str
    event_type: str
    stage: str | None
    payload: dict | None
    created_at: datetime

    class Config:
        from_attributes = True

class PaginatedAuditEvents(BaseModel):
    events: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
