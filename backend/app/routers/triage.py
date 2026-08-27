"""
FastAPI router for Hotspot Triage (v4.2 Stage 3).
Handles triage data fetching, RFC-6902 review edit recording, and stage confirmation gate.
"""
import os
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.case import Case
from app.models.stage_execution import StageExecution
from app.models.hotspot import Hotspot
from app.models.audit import AuditEvent

router = APIRouter(prefix="/api/v1/stages/triage", tags=["triage"])


class TriageEditsPayload(BaseModel):
    case_id: str
    edits: list[dict[str, Any]] # RFC-6902 style edit operations


class TriageConfirmPayload(BaseModel):
    case_id: str
    no_invasive_tumor: bool = False
    reviewed_by: str = "pathologist_01"


def apply_edit_ops(machine_hotspots: list[dict], edits: list[dict]) -> list[dict]:
    """
    Applies RFC-6902 style diff operations to machine output hotspots.
    Idempotent and order-stable.
    """
    hotspots_dict = {h["id"]: dict(h) for h in machine_hotspots}

    for op in edits:
        action = op.get("op")
        hid = op.get("id")

        if action == "modify" and hid in hotspots_dict:
            if "polygon_um" in op:
                hotspots_dict[hid]["polygon_um"] = op["polygon_um"]
                hotspots_dict[hid]["source"] = "pathologist_modified"

        elif action == "add":
            new_id = hid or f"user_{len(hotspots_dict)+1:02d}"
            hotspots_dict[new_id] = {
                "id": new_id,
                "polygon_um": op.get("polygon_um", []),
                "area_mm2": op.get("area_mm2", 1.0),
                "prob_mean": op.get("prob_mean", 1.0),
                "prob_max": op.get("prob_max", 1.0),
                "source": "pathologist_added",
                "excluded": False,
                "exclude_reason": None
            }

        elif action == "exclude" and hid in hotspots_dict:
            hotspots_dict[hid]["excluded"] = True
            hotspots_dict[hid]["exclude_reason"] = op.get("reason", "Pathologist excluded")

        elif action == "delete" and hid in hotspots_dict:
            del hotspots_dict[hid]

    return list(hotspots_dict.values())


from app.core.gcs import get_gcs_client, get_local_cache_dir

def resolve_local_path(gcs_uri: str) -> str:
    """Helper to resolve gs:// bucket URIs to local disk cache paths with real GCS downloading."""
    if not gcs_uri:
        return ""
    cache_dir = get_local_cache_dir()
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        bucket_name = parts[0]
        rel_path = parts[1] if len(parts) > 1 else ""
        local_path = os.path.join(cache_dir, bucket_name, rel_path)
        if not os.path.exists(local_path):
            try:
                client = get_gcs_client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(rel_path)
                if hasattr(blob, "download_to_filename"):
                    blob.download_to_filename(local_path, timeout=10)
            except Exception as ge:
                print(f"[Triage Router Warning] Artifact fetch note: {ge}")
        return local_path
    return gcs_uri


@router.get("/{case_id}")
def get_triage_data(case_id: str, db: Session = Depends(get_db)):
    """
    Returns latest triage machine outputs, probability grid ref, heatmap URI, and saved edits.
    """
    stage_exec = db.scalars(
        select(StageExecution).where(
            StageExecution.case_id == case_id,
            StageExecution.stage == "triage"
        ).order_by(StageExecution.attempt.desc())
    ).first()

    if not stage_exec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No triage stage execution found for case {case_id}"
        )

    output_ref = stage_exec.output_ref or ""
    machine_output = {}

    if output_ref:
        local_path = resolve_local_path(output_ref)
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                machine_output = json.load(f)

    edits = stage_exec.review_edits or []
    machine_hotspots = machine_output.get("hotspots", [])
    effective_hotspots = apply_edit_ops(machine_hotspots, edits)

    return {
        "case_id": case_id,
        "stage_execution_id": str(stage_exec.id),
        "status": stage_exec.status,
        "heatmap_png_uri": machine_output.get("heatmap_png_uri"),
        "prob_grid_uri": machine_output.get("prob_grid_uri"),
        "grid": machine_output.get("grid"),
        "machine_hotspots": machine_hotspots,
        "effective_hotspots": effective_hotspots,
        "review_edits": edits,
        "model_versions": stage_exec.model_versions
    }


@router.post("/edits")
def save_triage_edits(payload: TriageEditsPayload, db: Session = Depends(get_db)):
    """
    Saves draft edit operations diff.
    """
    stage_exec = db.scalars(
        select(StageExecution).where(
            StageExecution.case_id == payload.case_id,
            StageExecution.stage == "triage"
        ).order_by(StageExecution.attempt.desc())
    ).first()

    if not stage_exec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Triage stage execution not found for case {payload.case_id}"
        )

    stage_exec.review_edits = payload.edits
    
    audit = AuditEvent(
        case_id=payload.case_id,
        actor="pathologist",
        event_type="review_edit",
        stage="triage",
        payload={"edit_count": len(payload.edits)}
    )
    db.add(audit)
    db.commit()

    return {"status": "success", "edits_count": len(payload.edits)}


@router.post("/confirm")
def confirm_triage(payload: TriageConfirmPayload, db: Session = Depends(get_db)):
    """
    Confirms triage stage, writes effective hotspots into DB, and queues next stage.
    """
    stage_exec = db.scalars(
        select(StageExecution).where(
            StageExecution.case_id == payload.case_id,
            StageExecution.stage == "triage"
        ).order_by(StageExecution.attempt.desc())
    ).first()

    if not stage_exec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Triage stage execution not found for case {payload.case_id}"
        )

    output_ref = stage_exec.output_ref or ""
    machine_hotspots = []
    if output_ref:
        local_path = resolve_local_path(output_ref)
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                machine_hotspots = json.load(f).get("hotspots", [])

    edits = stage_exec.review_edits or []
    effective_hotspots = apply_edit_ops(machine_hotspots, edits)

    # Delete any prior confirmed hotspots for this case
    db.query(Hotspot).filter(Hotspot.case_id == payload.case_id).delete()

    # Persist effective hotspots to DB
    for hs in effective_hotspots:
        hotspot_row = Hotspot(
            id=hs["id"],
            case_id=payload.case_id,
            stage_execution_id=str(stage_exec.id),
            polygon_um=hs["polygon_um"],
            area_mm2=hs.get("area_mm2"),
            prob_mean=hs.get("prob_mean"),
            prob_max=hs.get("prob_max"),
            source=hs.get("source", "model"),
            excluded=hs.get("excluded", False),
            exclude_reason=hs.get("exclude_reason")
        )
        db.add(hotspot_row)

    stage_exec.status = "confirmed"
    stage_exec.reviewed_at = datetime.now(timezone.utc)
    stage_exec.reviewed_by = payload.reviewed_by

    if payload.no_invasive_tumor:
        next_stage_name = "report"
        input_data = {"benign_flag": True, "reason": "No invasive tumor identified"}
    else:
        next_stage_name = "mitosis"
        input_data = {"confirmed_hotspots_count": len(effective_hotspots)}

    next_exec = db.scalars(
        select(StageExecution).where(
            StageExecution.case_id == payload.case_id,
            StageExecution.stage == next_stage_name,
            StageExecution.attempt == 1
        )
    ).first()

    if not next_exec:
        next_exec = StageExecution(
            case_id=payload.case_id,
            stage=next_stage_name,
            attempt=1,
            status="queued",
            input_ref=input_data
        )
        db.add(next_exec)

    audit = AuditEvent(
        case_id=payload.case_id,
        actor=payload.reviewed_by,
        event_type="stage_confirmed",
        stage="triage",
        payload={
            "confirmed_hotspots": len(effective_hotspots),
            "no_invasive_tumor": payload.no_invasive_tumor,
            "next_stage": next_stage_name
        }
    )
    db.add(audit)
    db.commit()

    return {
        "status": "confirmed",
        "case_id": payload.case_id,
        "confirmed_hotspots_count": len(effective_hotspots),
        "next_stage_queued": next_stage_name
    }
