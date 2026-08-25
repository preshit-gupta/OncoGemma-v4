import uuid
import os
import shutil
import tempfile
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.db import get_db
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings
from app.core.gcs import get_gcs_client
from app.models.case import Case
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.audit import AuditEvent
from app.schemas.case import (
    CaseResponse,
    SlideUploadUrlRequest,
    SlideUploadUrlResponse,
    SlideFinalizeRequest,
    CaseDetailResponse
)

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    case_obj = Case(created_by=user.id)
    db.add(case_obj)
    db.commit()
    db.refresh(case_obj)

    audit = AuditEvent(
        case_id=str(case_obj.id),
        actor=user.id,
        event_type="case_created",
        payload={"created_by": user.id}
    )
    db.add(audit)
    db.commit()

    return case_obj

@router.get("", response_model=list[CaseResponse])
def list_cases(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    stmt = select(Case).order_by(Case.created_at.desc())
    cases = db.scalars(stmt).all()
    return cases

@router.delete("", status_code=status.HTTP_200_OK)
def clear_all_cases(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """Clear all diagnostic cases and audit logs."""
    cases = db.scalars(select(Case)).all()
    count = len(cases)
    for c in cases:
        db.delete(c)
    db.commit()

    # Clear local fake_gcs files if emulator
    client = get_gcs_client()
    if hasattr(client, "base_dir") and os.path.exists(client.base_dir):
        for item in os.listdir(client.base_dir):
            item_path = os.path.join(client.base_dir, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception:
                pass

    return {"status": "cleared", "deleted_count": count}

@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """Delete a single diagnostic case."""
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")
    
    db.delete(case_obj)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{case_id}/slide/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_slide_file(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """Direct file upload endpoint with seek(0) to preserve file stream bytes."""
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    file_uuid = uuid.uuid4()
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "svs"
    
    gcs_uri = f"gs://{settings.GCS_RAW_BUCKET}/cases/{case_id}/{file_uuid}.{ext}"
    blob_name = f"cases/{case_id}/{file_uuid}.{ext}"

    # Fast local buffer save with seek(0) to write complete file bytes
    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../raw_uploads"))
    os.makedirs(temp_dir, exist_ok=True)
    local_temp_path = os.path.join(temp_dir, f"{case_id}_{file_uuid}.{ext}")
    
    try:
        await file.seek(0)
        with open(local_temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as save_err:
        print(f"[Upload Error] Local file save failed: {save_err}")
        raise HTTPException(status_code=500, detail=f"Local file buffer save failed: {str(save_err)}")

    # Create slide record
    slide_obj = Slide(
        case_id=case_id,
        gcs_uri_original=gcs_uri
    )
    db.add(slide_obj)
    db.flush()
    
    # Queue 'ingest' stage_execution with local file reference for background worker GCS streaming
    stage_exec = StageExecution(
        case_id=case_id,
        stage="ingest",
        attempt=1,
        status="queued",
        input_ref={
            "gcs_uri_original": gcs_uri,
            "slide_id": str(slide_obj.id),
            "blob_name": blob_name,
            "local_file_path": local_temp_path
        }
    )
    db.add(stage_exec)
    
    # Audit event
    audit = AuditEvent(
        case_id=str(case_id),
        actor=user.id,
        event_type="slide_uploaded",
        stage="ingest",
        payload={"gcs_uri": gcs_uri, "slide_id": str(slide_obj.id), "filename": file.filename}
    )
    db.add(audit)
    
    db.commit()

    return {
        "status": "queued",
        "slide_id": str(slide_obj.id),
        "stage_execution_id": str(stage_exec.id),
        "gcs_uri": gcs_uri
    }

@router.post("/{case_id}/stages/{stage_name}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_case_stage(
    case_id: uuid.UUID,
    stage_name: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    """Re-queue execution attempt for a specific pipeline stage."""
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slide_obj = db.scalars(select(Slide).where(Slide.case_id == case_id)).first()
    if not slide_obj:
        raise HTTPException(status_code=404, detail="Slide not found")

    stmt = (
        select(StageExecution)
        .where(StageExecution.case_id == case_id, StageExecution.stage == stage_name)
        .order_by(StageExecution.attempt.desc())
    )
    existing_stage = db.scalars(stmt).first()
    next_attempt = (existing_stage.attempt + 1) if existing_stage else 1

    new_stage = StageExecution(
        case_id=case_id,
        stage=stage_name,
        attempt=next_attempt,
        status="queued",
        input_ref={"gcs_uri_original": slide_obj.gcs_uri_original, "slide_id": str(slide_obj.id)}
    )
    db.add(new_stage)
    
    audit = AuditEvent(
        case_id=str(case_id),
        actor=user.id,
        event_type="stage_retried",
        stage=stage_name,
        payload={"attempt": next_attempt}
    )
    db.add(audit)
    db.commit()
    db.refresh(new_stage)

    return {
        "status": "queued",
        "stage_execution_id": str(new_stage.id),
        "attempt": next_attempt
    }

@router.post("/{case_id}/slide/upload-url", response_model=SlideUploadUrlResponse)
def get_slide_upload_url(
    case_id: uuid.UUID,
    req: SlideUploadUrlRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    file_uuid = uuid.uuid4()
    ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else "svs"
    
    gcs_uri = f"gs://{settings.GCS_RAW_BUCKET}/cases/{case_id}/{file_uuid}.{ext}"
    upload_url = f"{settings.STORAGE_EMULATOR_HOST}/upload/storage/v1/b/{settings.GCS_RAW_BUCKET}/o?uploadType=resumable&name=cases/{case_id}/{file_uuid}.{ext}"

    return SlideUploadUrlResponse(
        upload_url=upload_url,
        gcs_uri=gcs_uri
    )

@router.post("/{case_id}/slide/finalize", status_code=status.HTTP_202_ACCEPTED)
def finalize_slide_upload(
    case_id: uuid.UUID,
    req: SlideFinalizeRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slide_obj = Slide(
        case_id=case_id,
        gcs_uri_original=req.gcs_uri,
        checksum_sha256=req.client_sha256
    )
    db.add(slide_obj)
    db.flush()
    
    stage_exec = StageExecution(
        case_id=case_id,
        stage="ingest",
        attempt=1,
        status="queued",
        input_ref={"gcs_uri_original": req.gcs_uri, "slide_id": str(slide_obj.id)}
    )
    db.add(stage_exec)
    
    audit = AuditEvent(
        case_id=str(case_id),
        actor=user.id,
        event_type="slide_uploaded",
        stage="ingest",
        payload={"gcs_uri": req.gcs_uri, "slide_id": str(slide_obj.id)}
    )
    db.add(audit)
    
    db.commit()
    db.refresh(slide_obj)
    db.refresh(stage_exec)

    return {
        "status": "queued",
        "slide_id": str(slide_obj.id),
        "stage_execution_id": str(stage_exec.id)
    }

@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user)
):
    case_obj = db.get(Case, case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    slides = db.scalars(select(Slide).where(Slide.case_id == case_id)).all()
    stages = db.scalars(select(StageExecution).where(StageExecution.case_id == case_id).order_by(StageExecution.started_at.asc())).all()

    slides_data = [
        {
            "id": str(s.id),
            "gcs_uri_original": s.gcs_uri_original,
            "gcs_uri_pyramid": s.gcs_uri_pyramid,
            "format": s.format,
            "scanner": s.scanner,
            "mpp_x": s.mpp_x,
            "mpp_y": s.mpp_y,
            "base_mag": s.base_mag,
            "width_px": s.width_px,
            "height_px": s.height_px,
            "checksum_sha256": s.checksum_sha256,
            "label_stripped_at": s.label_stripped_at.isoformat() if s.label_stripped_at else None
        }
        for s in slides
    ]

    stages_data = [
        {
            "id": str(st.id),
            "stage": st.stage,
            "attempt": st.attempt,
            "status": st.status,
            "output_ref": st.output_ref,
            "error": st.error,
            "started_at": st.started_at.isoformat() if st.started_at else None,
            "completed_at": st.completed_at.isoformat() if st.completed_at else None
        }
        for st in stages
    ]

    return CaseDetailResponse(
        id=case_obj.id,
        created_by=case_obj.created_by,
        status=case_obj.status,
        created_at=case_obj.created_at,
        slides=slides_data,
        stages=stages_data
    )
