"""
FastAPI router for Hotspot Triage (v4.2 Stage 3).
Handles triage data fetching, RFC-6902 review edit recording, and stage confirmation gate.
"""
import os
import io
import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional
import numpy as np
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import get_local_cache_dir
from app.core.db import get_db
from app.core.openslide_lock import OPENSLIDE_GLOBAL_LOCK
from app.models.case import Case
from app.models.slide import Slide
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

    # Ensure all effective hotspots have thumbnail_url
    for hs in effective_hotspots:
        if not hs.get("thumbnail_url"):
            hs_id = hs.get("id")
            hs["thumbnail_url"] = f"/api/v1/stages/triage/{case_id}/hotspots/{hs_id}/thumbnail?mag=10x"

    return {
        "case_id": case_id,
        "stage_execution_id": str(stage_exec.id),
        "status": stage_exec.status,
        "heatmap_png_uri": machine_output.get("heatmap_png_uri"),
        "heatmap_direct_url": machine_output.get("heatmap_direct_url") or f"/api/v1/stages/triage/{case_id}/heatmap",
        "prob_grid_uri": machine_output.get("prob_grid_uri"),
        "grid": machine_output.get("grid"),
        "machine_hotspots": machine_hotspots,
        "effective_hotspots": effective_hotspots,
        "review_edits": edits,
        "model_versions": stage_exec.model_versions
    }


@router.get("/{case_id}/heatmap")
def get_triage_heatmap_image(case_id: str, db: Session = Depends(get_db)):
    """Returns the Viridis heatmap PNG overlay for OpenSeadragon viewer."""
    stage_exec = db.scalars(
        select(StageExecution).where(
            StageExecution.case_id == case_id,
            StageExecution.stage == "triage"
        ).order_by(StageExecution.attempt.desc())
    ).first()

    if not stage_exec:
        raise HTTPException(status_code=404, detail="Triage execution not found")

    cache_base = get_local_cache_dir()
    heatmap_png_path = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "triage", "heatmap_triage.png")

    if not os.path.exists(heatmap_png_path):
        heatmap_png_path = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "triage", "heatmap.png")

    if not os.path.exists(heatmap_png_path):
        raise HTTPException(status_code=404, detail="Heatmap image artifact not found")

    return FileResponse(heatmap_png_path, media_type="image/png")


@router.get("/{case_id}/hotspots/{hotspot_id}/thumbnail")
def get_hotspot_thumbnail(
    case_id: str, 
    hotspot_id: str, 
    mag: str = "10x",
    stain: str = "norm",
    cx: Optional[float] = Query(None),
    cy: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    """Extracts and streams a calibrated microscopic RGB patch centered on the specified hotspot or coordinates."""
    cache_base = get_local_cache_dir()

    # 0. Fast Path: Serve pre-rendered cloud artifact thumbnail if present
    pregen_patch_path = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "triage", "patches", f"{hotspot_id}_thumb.png")
    if os.path.exists(pregen_patch_path) and mag == "10x":
        return FileResponse(pregen_patch_path, media_type="image/png")

    case_obj = db.get(Case, case_id)
    slide_obj = case_obj.slides[0] if case_obj and case_obj.slides else None
    if not slide_obj:
        raise HTTPException(status_code=404, detail="Slide not found")

    mpp_x = float(slide_obj.mpp_x or 0.25)
    mpp_y = float(slide_obj.mpp_y or mpp_x)

    cx_um = None
    cy_um = None

    if cx is not None and cy is not None:
        cx_um = float(cx)
        cy_um = float(cy)
    else:
        out_json_path = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "triage", "output.json")
        if os.path.exists(out_json_path):
            with open(out_json_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
            target_hs = next((h for h in tdata.get("hotspots", []) if h["id"] == hotspot_id), None)
            if target_hs and "polygon_um" in target_hs:
                poly = np.array(target_hs["polygon_um"])
                cx_um = float(poly[:, 0].mean())
                cy_um = float(poly[:, 1].mean())

    if cx_um is None or cy_um is None:
        # Check review edits in DB
        st_obj = next((s for s in case_obj.stage_executions if s.stage == "triage"), None)
        if st_obj and st_obj.review_edits:
            for ed in st_obj.review_edits:
                if ed.get("id") == hotspot_id and "polygon_um" in ed:
                    poly = np.array(ed["polygon_um"])
                    cx_um = float(poly[:, 0].mean())
                    cy_um = float(poly[:, 1].mean())
                    break

    if cx_um is None or cy_um is None:
        cx_um = float(slide_obj.width_px or 20000) * mpp_x * 0.5
        cy_um = float(slide_obj.height_px or 20000) * mpp_y * 0.5

    cx_px = int(cx_um / mpp_x)
    cy_px = int(cy_um / mpp_y)

    # Resolve field size in micrometers based on requested magnification
    field_um = 512.0
    if mag == "20x":
        field_um = 256.0
    elif mag == "40x":
        field_um = 128.0

    # 1. Search candidate locations for the raw WSI slide
    candidate_paths = []
    # Location A: GCS cache raw cases directory
    raw_case_dir = os.path.join(cache_base, settings.GCS_RAW_BUCKET, "cases", str(case_id))
    if os.path.exists(raw_case_dir):
        for f in os.listdir(raw_case_dir):
            if f.endswith((".svs", ".ndpi", ".tif", ".tiff")):
                candidate_paths.append(os.path.join(raw_case_dir, f))

    # Location B: raw_uploads
    raw_uploads_dir = os.path.abspath("raw_uploads")
    if os.path.exists(raw_uploads_dir):
        for f in os.listdir(raw_uploads_dir):
            if str(case_id) in f and f.endswith((".svs", ".ndpi", ".tif", ".tiff")):
                candidate_paths.append(os.path.join(raw_uploads_dir, f))

    # Location C: GCS cache direct bucket
    raw_bucket_dir = os.path.join(cache_base, settings.GCS_RAW_BUCKET)
    if os.path.exists(raw_bucket_dir):
        for root, _, files in os.walk(raw_bucket_dir):
            for f in files:
                if str(case_id) in root and f.endswith((".svs", ".ndpi", ".tif", ".tiff")):
                    candidate_paths.append(os.path.join(root, f))

    if candidate_paths:
        try:
            with OPENSLIDE_GLOBAL_LOCK:
                import openslide
                slide_file = candidate_paths[0]
                os_slide = None
                try:
                    os_slide = openslide.OpenSlide(slide_file)
                    dim_w, dim_h = getattr(os_slide, "dimensions", (100000, 100000))
                    crop_w_px = int(round(field_um / mpp_x))
                    crop_h_px = int(round(field_um / mpp_y))

                    x0 = max(0, min(dim_w - crop_w_px, cx_px - crop_w_px // 2))
                    y0 = max(0, min(dim_h - crop_h_px, cy_px - crop_h_px // 2))

                    # Read region at highest resolution level 0
                    patch_raw = os_slide.read_region((x0, y0), 0, (crop_w_px, crop_h_px)).convert("RGB")
                finally:
                    if os_slide and hasattr(os_slide, "close"):
                        os_slide.close()

            # Apply Macenko Stain Normalization if requested
            if stain == "norm":
                try:
                    from pipeline.stain import PureNumpyMacenkoNormalizer
                    stain_json = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "preprocess", "stain_params.json")
                    if os.path.exists(stain_json):
                        with open(stain_json, "r", encoding="utf-8") as sf:
                            sp_data = json.load(sf)
                        if "stain_matrix" in sp_data and "max_concentrations" in sp_data:
                            norm_obj = PureNumpyMacenkoNormalizer()
                            norm_obj.stain_matrix_target = np.array(sp_data["stain_matrix"], dtype=float)
                            norm_obj.max_conc_target = np.array(sp_data["max_concentrations"], dtype=float)
                            norm_arr = norm_obj.transform(np.array(patch_raw))
                            patch_raw = Image.fromarray(norm_arr)
                except Exception as se:
                    print(f"[Thumbnail Normalization Note] {se}")

            patch_final = patch_raw.resize((512, 512), Image.LANCZOS)

            buf = io.BytesIO()
            patch_final.save(buf, format="JPEG", quality=92)
            return Response(content=buf.getvalue(), media_type="image/jpeg")
        except Exception as e:
            print(f"[Thumbnail OpenSlide Error] {e}")

    # Fallback placeholder
    img = Image.new("RGB", (512, 512), color=(240, 235, 245))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return Response(content=buf.getvalue(), media_type="image/jpeg")


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
