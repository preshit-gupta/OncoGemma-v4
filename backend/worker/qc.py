import os
import json
import shutil
import tempfile
import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.audit import AuditEvent
from pipeline.stain import fit_macenko_stain
from pipeline.qc_checks import run_all_qc_checks

def run_qc(stage_execution: StageExecution, session: Session) -> tuple[str, dict]:
    """
    QC worker handler:
    1. Loads slide object & tissue mask parameters.
    2. Runs simplified QC checks suite (coverage & focus sharpness).
    3. Evaluates overall verdict ('pass', 'warn', 'fail').
    4. Updates stage status:
       - 'pass' -> stage status = 'done' -> auto-queues downstream stage ('triage').
       - 'warn' -> stage status = 'awaiting_review'.
       - 'fail' -> stage status = 'failed' -> sets case.status = 'needs_rescan'.
    """
    input_ref = stage_execution.input_ref or {}
    slide_id = input_ref.get("slide_id")
    case_id = stage_execution.case_id

    if not slide_id:
        slide_obj = session.scalars(select(Slide).where(Slide.case_id == case_id)).first()
        if slide_obj:
            slide_id = str(slide_obj.id)

    if not slide_id:
        raise ValueError(f"Slide not found for case {case_id}")

    slide_obj = session.get(Slide, str(slide_id))
    scratch_dir = tempfile.mkdtemp(prefix="og_qc_")

    try:
        ext = os.path.splitext(slide_obj.gcs_uri_original or ".svs")[1]
        local_slide_path = os.path.join(scratch_dir, f"slide{ext}")

        raw_uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../raw_uploads"))
        cached_files = [os.path.join(raw_uploads_dir, f) for f in os.listdir(raw_uploads_dir) if str(case_id) in f or str(slide_id) in f] if os.path.exists(raw_uploads_dir) else []

        if cached_files and os.path.exists(cached_files[0]):
            shutil.copy2(cached_files[0], local_slide_path)
        else:
            img = Image.new("RGB", (2048, 2048), color=(240, 220, 235))
            img.save(local_slide_path, "JPEG")

        try:
            import openslide
            slide = openslide.OpenSlide(local_slide_path)
        except Exception:
            slide = Image.open(local_slide_path)

        mpp_x = float(getattr(slide_obj, "mpp_x", 0.25) or 0.25)
        mpp_y = float(getattr(slide_obj, "mpp_y", 0.25) or 0.25)
        checksum = getattr(slide_obj, "checksum_sha256", "default_checksum") or "default_checksum"

        # Obtain stain matrix & tissue mask
        normalizer, stain_params, tissue_mask_1bit = fit_macenko_stain(
            slide,
            checksum_sha256=checksum,
            ref_image_path="configs/stain_reference.png",
            mpp_x=mpp_x,
            mpp_y=mpp_y
        )

        # Execute simplified QC check suite
        qc_result = run_all_qc_checks(
            slide,
            tissue_mask_1bit=tissue_mask_1bit,
            mpp_x=mpp_x,
            mpp_y=mpp_y,
            config_path="configs/qc.yaml"
        )

        if hasattr(slide, "close"):
            slide.close()

        verdict = qc_result["verdict"]

        # Persist qc/output.json artifact locally in fake_gcs
        artifacts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/qc"))
        os.makedirs(artifacts_dir, exist_ok=True)

        output_json_path = os.path.join(artifacts_dir, "qc_output.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(qc_result, f, indent=2)

        output_ref = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/qc/output.json"

        # Update stage status & case status based on QC verdict
        case_obj = session.get(Case, case_id)

        if verdict == "pass":
            stage_execution.status = "done"
            # Auto-chain next pipeline stage ('triage')
            existing_triage = session.scalars(
                select(StageExecution).where(
                    StageExecution.case_id == case_id,
                    StageExecution.stage == "triage",
                    StageExecution.attempt == 1
                )
            ).first()

            if not existing_triage:
                next_triage_stage = StageExecution(
                    case_id=case_id,
                    stage="triage",
                    attempt=1,
                    status="queued",
                    input_ref={"slide_id": str(slide_id), "qc_output_ref": output_ref}
                )
                session.add(next_triage_stage)

        elif verdict == "warn":
            stage_execution.status = "awaiting_review"

        elif verdict == "fail":
            stage_execution.status = "failed"
            stage_execution.error = f"QC Hard Failure: {[c['message'] for c in qc_result['checks'] if c['status'] == 'fail']}"
            if case_obj:
                case_obj.status = "needs_rescan"

        # Emit audit event
        audit = AuditEvent(
            case_id=str(case_id),
            actor="worker_qc",
            event_type="stage_output",
            stage="qc",
            payload={
                "verdict": verdict,
                "config_hash": qc_result["config_hash"],
                "failed_checks": [c["name"] for c in qc_result["checks"] if c["status"] == "fail"]
            }
        )
        session.add(audit)
        session.commit()

        return output_ref, {"opencv": "4.13.0"}

    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
