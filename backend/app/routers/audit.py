import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.db import get_db
from app.core.auth import get_current_user, CurrentUser
from app.models.audit import AuditEvent
from app.models.case import Case
from app.schemas.audit import PaginatedAuditEvents, AuditEventResponse

router = APIRouter(prefix="/api/v1/cases", tags=["audit"])

@router.get("/{case_id}/audit", response_model=PaginatedAuditEvents)
def get_case_audit_events(
    case_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    offset = (page - 1) * page_size

    stmt = select(AuditEvent).where(AuditEvent.case_id == str(case_id)).order_by(AuditEvent.created_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    
    events = db.scalars(stmt.offset(offset).limit(page_size)).all()

    return PaginatedAuditEvents(
        events=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size
    )
