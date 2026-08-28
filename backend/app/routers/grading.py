"""
FastAPI Router for Stage 5: Nottingham Histologic Grading (v4.4).

Provides endpoints for retrieving evidence patches and machine grades,
live reactive debounced recomputation, patch image streaming, and
clinical confirmation gate with mandatory histologic type sign-off.
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import get_local_cache_dir
from app.core.db import get_db
from app.models.case import Case
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.hpf_site import HpfSite
from app.models.grading import Grading
from app.models.audit import AuditEvent
from pipeline.grading import (
    calculate_nottingham_grade,
    validate_grading_invariants,
    load_scoring_config
)

router = APIRouter(prefix="/api/v1/stages/grading", tags=["grading"])


# ---------------------------------------------------------------------------
# Pydantic Request / Response Schemas
# ---------------------------------------------------------------------------

class RecomputeGradePayload(BaseModel):
    case_id: str
    tubule_score: Optional[int] = Field(None, ge=1, le=3)
    tubule_percent: Optional[float] = None
    pleo_score: Optional[int] = Field(None, ge=1, le=3)
    mitotic_score: Optional[int] = Field(None, ge=1, le=3)


class ScoreOverrideDetail(BaseModel):
    score: int = Field(ge=1, le=3)
    percent: Optional[float] = None
    original_score: int
    justification: str = Field(min_length=10, description="Minimum 10-char clinical justification")


class ConfirmGradingPayload(BaseModel):
    case_id: str
    reviewed_by: str = Field(default="user_pathologist_001")
    histologic_type: str = Field(default="IDC-NST")
    type_confirmed: bool = Field(default=False, description="Mandatory confirmation gate")
    overrides: Dict[str, Any] = Field(default_factory=dict)
    tubule_score: int = Field(ge=1, le=3)
    tubule_percent: Optional[float] = None
    pleo_score: int = Field(ge=1, le=3)
    mitotic_score: int = Field(ge=1, le=3)
    nottingham_sum: int = Field(ge=3, le=9)
    grade: int = Field(ge=1, le=3)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def to_uuid(val: Any) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except Exception:
        return val

@router.get("/{case_id}")
def get_grading_stage_data(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieve full Stage 5 Grading data: 24 evidence patches, machine sub-scores,
    active overrides, live calculated grade, and histologic type metadata.
    """
    case_uid = to_uuid(case_id)
    case = db.scalars(select(Case).where(Case.id == case_uid)).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    stage_exec = db.scalars(
        select(StageExecution).where(StageExecution.case_id == case_uid, StageExecution.stage == "grading")
    ).first()

    grading_record = db.scalars(
        select(Grading).where(Grading.case_id == case_uid)
    ).first()

    # If grading has not run yet
    if not grading_record or not grading_record.machine:
        # Check mitotic stage summary for preview
        hpf_sites = list(db.scalars(select(HpfSite).where(HpfSite.case_id == case_uid)).all())
        total_mitoses = sum(h.mitotic_figure_count for h in hpf_sites) if hpf_sites else 0
        m_score = 1 if total_mitoses < 8 else (2 if total_mitoses < 16 else 3)
        
        return {
            "case_id": str(case_id),
            "status": stage_exec.status if stage_exec else "not_started",
            "mitotic_summary": {
                "total_mitoses": total_mitoses,
                "mitotic_score": m_score,
                "evaluated_hpfs": len(hpf_sites)
            },
            "patches": [],
            "aggregate": None,
            "overrides": {},
            "grade": None
        }

    machine_data = grading_record.machine
    overrides = grading_record.overrides or {}

    # Calculate effective scores accounting for overrides
    eff_tubule_score = overrides.get("tubule", {}).get("score", grading_record.tubule_score)
    eff_tubule_percent = overrides.get("tubule", {}).get("percent", grading_record.tubule_percent)
    eff_pleo_score = overrides.get("pleo", {}).get("score", grading_record.pleo_score)
    eff_mitotic_score = overrides.get("mitotic", {}).get("score", grading_record.mitotic_score)
    
    eff_sum, eff_grade = calculate_nottingham_grade(eff_tubule_score, eff_pleo_score, eff_mitotic_score)

    # Mitotic summary
    hpf_sites = list(db.scalars(select(HpfSite).where(HpfSite.case_id == case_uid)).all())
    total_mitoses = sum(h.mitotic_figure_count for h in hpf_sites) if hpf_sites else 0

    return {
        "case_id": str(case_id),
        "slide_id": str(case.slides[0].id) if case.slides else None,
        "status": stage_exec.status if stage_exec else "awaiting_review",
        "patches": machine_data.get("patches", []),
        "machine": {
            "tubule_percent": grading_record.tubule_percent,
            "tubule_score": grading_record.tubule_score,
            "pleo_score": grading_record.pleo_score,
            "mitotic_score": grading_record.mitotic_score,
            "nottingham_sum": grading_record.nottingham_sum,
            "grade": grading_record.grade,
            "flags": machine_data.get("aggregate", {}).get("flags", [])
        },
        "current": {
            "tubule_score": eff_tubule_score,
            "tubule_percent": eff_tubule_percent,
            "pleo_score": eff_pleo_score,
            "mitotic_score": eff_mitotic_score,
            "nottingham_sum": eff_sum,
            "grade": eff_grade,
            "is_overridden": bool(overrides)
        },
        "histologic_type": {
            "proposed_type": machine_data.get("histologic_type", {}).get("type", "IDC-NST"),
            "differential": machine_data.get("histologic_type", {}).get("differential", []),
            "rationale": machine_data.get("histologic_type", {}).get("rationale", ""),
            "confidence": machine_data.get("histologic_type", {}).get("confidence", "medium"),
            "confirmed_type": grading_record.histologic_type,
            "type_confirmed_by": grading_record.type_confirmed_by,
            "is_confirmed": grading_record.type_confirmed_by != "unconfirmed"
        },
        "narrative": machine_data.get("narrative", ""),
        "overrides": overrides,
        "mitotic_summary": {
            "total_mitoses": total_mitoses,
            "mitotic_score": eff_mitotic_score,
            "evaluated_hpfs": len(hpf_sites)
        },
        "model_versions": machine_data.get("model_versions", {})
    }


@router.get("/{case_id}/patches/{patch_id}/image")
def get_patch_image(case_id: str, patch_id: str):
    """
    Stream the 512x512 normalized evidence patch PNG.
    """
    cache_base = get_local_cache_dir()
    patch_path = os.path.join(
        cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "grading_patches", f"{patch_id}.png"
    )

    if not os.path.exists(patch_path):
        # Check alternate directory locations
        alt_path = os.path.join("gcs_cache", settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "grading_patches", f"{patch_id}.png")
        if os.path.exists(alt_path):
            patch_path = alt_path
        else:
            raise HTTPException(status_code=404, detail=f"Patch image {patch_id}.png for case {case_id} not found")

    return FileResponse(patch_path, media_type="image/png")


@router.post("/recompute")
def recompute_grade_preview(payload: RecomputeGradePayload, db: Session = Depends(get_db)):
    """
    Live debounced in-memory preview of Nottingham Sum and Grade (<10ms execution).
    """
    case_uid = to_uuid(payload.case_id)
    grading_record = db.scalars(select(Grading).where(Grading.case_id == case_uid)).first()

    t_score = payload.tubule_score or (grading_record.tubule_score if grading_record else 2)
    p_score = payload.pleo_score or (grading_record.pleo_score if grading_record else 2)
    m_score = payload.mitotic_score or (grading_record.mitotic_score if grading_record else 2)

    nottingham_sum, grade = calculate_nottingham_grade(t_score, p_score, m_score)
    validate_grading_invariants(t_score, p_score, m_score, nottingham_sum, grade)

    is_overridden = False
    if grading_record:
        if t_score != grading_record.tubule_score or p_score != grading_record.pleo_score or m_score != grading_record.mitotic_score:
            is_overridden = True

    return {
        "tubule_score": t_score,
        "pleo_score": p_score,
        "mitotic_score": m_score,
        "nottingham_sum": nottingham_sum,
        "grade": grade,
        "is_overridden": is_overridden
    }


@router.post("/confirm")
def confirm_grading_stage(payload: ConfirmGradingPayload, db: Session = Depends(get_db)):
    """
    Clinical Confirmation Gate for Stage 5 (Nottingham Grading).
    Enforces mandatory Histologic Type confirmation and >=10 char override justification,
    validates mathematical invariants, persists final scores to DB, and queues Stage 6.
    """
    case_id = payload.case_id

    # 1. Mandatory Histologic Type Confirmation Gate
    if not payload.type_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clinical Confirmation Gate: Histologic Type must be explicitly confirmed by the pathologist before proceeding to Report Generation."
        )

    # 2. Validate Override Justifications (min 10 chars)
    for comp_name, override_info in payload.overrides.items():
        justification = override_info.get("justification", "").strip()
        if len(justification) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clinical Safety Requirement: Score override for '{comp_name}' requires a minimum 10-character justification (got {len(justification)} characters)."
            )

    # 3. Pure Code Invariant Check
    try:
        validate_grading_invariants(
            tubule_score=payload.tubule_score,
            pleo_score=payload.pleo_score,
            mitotic_score=payload.mitotic_score,
            nottingham_sum=payload.nottingham_sum,
            grade=payload.grade
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    # 4. Fetch / Update Database Grading Record
    case_uid = to_uuid(case_id)
    grading_record = db.scalars(select(Grading).where(Grading.case_id == case_uid)).first()
    if not grading_record:
        raise HTTPException(status_code=404, detail="Grading record for case not found")

    grading_record.tubule_score = payload.tubule_score
    if payload.tubule_percent is not None:
        grading_record.tubule_percent = payload.tubule_percent
    grading_record.pleo_score = payload.pleo_score
    grading_record.mitotic_score = payload.mitotic_score
    grading_record.nottingham_sum = payload.nottingham_sum
    grading_record.grade = payload.grade
    grading_record.histologic_type = payload.histologic_type
    grading_record.type_confirmed_by = payload.reviewed_by
    grading_record.overrides = payload.overrides

    # 5. Mark Stage 5 as Confirmed
    stage_exec = db.scalars(
        select(StageExecution).where(StageExecution.case_id == case_uid, StageExecution.stage == "grading")
    ).first()
    if stage_exec:
        stage_exec.status = "confirmed"
        stage_exec.reviewed_at = datetime.now(timezone.utc)
        stage_exec.reviewed_by = payload.reviewed_by

    # 6. Queue Stage 6 (Report Generation)
    next_exec = db.scalars(
        select(StageExecution).where(StageExecution.case_id == case_uid, StageExecution.stage == "report")
    ).first()
    if not next_exec:
        next_exec = StageExecution(
            case_id=case_id,
            stage="report",
            attempt=1,
            status="queued"
        )
        db.add(next_exec)

    # 7. Record Audit Events
    audit_confirm = AuditEvent(
        case_id=str(case_id),
        actor=payload.reviewed_by,
        event_type="stage_5_grading_confirmed",
        stage="grading",
        payload={
            "nottingham_sum": payload.nottingham_sum,
            "grade": payload.grade,
            "histologic_type": payload.histologic_type,
            "has_overrides": bool(payload.overrides)
        }
    )
    db.add(audit_confirm)

    # Record individual score_override audit events
    for comp, o_info in payload.overrides.items():
        audit_ovr = AuditEvent(
            case_id=str(case_id),
            actor=payload.reviewed_by,
            event_type="score_override",
            stage="grading",
            payload={
                "component": comp,
                "from_score": o_info.get("original_score"),
                "to_score": o_info.get("score"),
                "justification": o_info.get("justification")
            }
        )
        db.add(audit_ovr)

    db.commit()

    return {
        "status": "success",
        "case_id": case_id,
        "stage": "grading",
        "next_stage": "report",
        "grade": payload.grade,
        "nottingham_sum": payload.nottingham_sum,
        "histologic_type": payload.histologic_type
    }
