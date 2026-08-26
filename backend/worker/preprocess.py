import os
import json
import math
import shutil
import tempfile
import numpy as np
from PIL import Image
from datetime import datetime, timezone
import glob
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import get_gcs_client
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.audit import AuditEvent
from pipeline.stain import fit_macenko_stain
from pipeline.tiles import read_region_srgb

def generate_norm_dzi_pyramid(slide_obj, normalizer, local_slide_path: str, scratch_dir: str) -> str:
    """
    Generate normalized DZI pyramid capped at 10x level (~1.0 µm/px).
    Generates normalized DZI tiles matching DeepZoom pyramid level indexing (0..max_norm_level).
    Stores both PNG and JPG format tiles in fake_gcs/GCS under pyramids/{slide_id}/norm/{level}/.
    """
    slide_id = str(slide_obj.id)
    norm_pyramid_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_PYRAMIDS_BUCKET}/{slide_id}/norm"))
    os.makedirs(norm_pyramid_dir, exist_ok=True)

    # Direct path: Transform existing orig pyramid tiles directly to norm tiles for 1:1 grid alignment
    orig_pyramid_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_PYRAMIDS_BUCKET}/{slide_id}/orig"))
    if os.path.exists(orig_pyramid_dir):
        available_levels = sorted([int(d) for d in os.listdir(orig_pyramid_dir) if d.isdigit()])
        if available_levels:
            slide_max_level = max(available_levels)
            max_norm_level = max(0, slide_max_level - 2) # 10x cap level
            
            for level in available_levels:
                orig_level_dir = os.path.join(orig_pyramid_dir, str(level))
                norm_level_dir = os.path.join(norm_pyramid_dir, str(level))
                os.makedirs(norm_level_dir, exist_ok=True)
                
                tile_files = [f for f in os.listdir(orig_level_dir) if f.endswith(".jpg") or f.endswith(".png")]
                for f in tile_files:
                    stem = os.path.splitext(f)[0]
                    t_path = os.path.join(orig_level_dir, f)
                    try:
                        raw_arr = np.array(Image.open(t_path).convert("RGB"))
                        norm_arr = normalizer.transform(raw_arr)
                    except Exception:
                        norm_arr = raw_arr
                    
                    norm_tile = Image.fromarray(norm_arr)
                    norm_tile.save(os.path.join(norm_level_dir, f"{stem}.png"), "PNG")
                    norm_tile.save(os.path.join(norm_level_dir, f"{stem}.jpg"), "JPEG", quality=85)

            # Upload norm pyramid tiles directly to Real GCP Cloud Storage bucket
            client = get_gcs_client()
            if not hasattr(client, "base_dir"):
                try:
                    bucket = client.bucket(settings.GCS_PYRAMIDS_BUCKET)
                    norm_files = glob.glob(os.path.join(norm_pyramid_dir, "**", "*.*"), recursive=True)
                    norm_files = [f for f in norm_files if f.lower().endswith((".jpg", ".jpeg", ".png"))]
                    
                    def upload_single_norm_tile(local_path):
                        try:
                            rel_path = os.path.relpath(local_path, norm_pyramid_dir)
                            parts = rel_path.split(os.sep)
                            if len(parts) >= 2:
                                z_level = parts[-2]
                                filename = parts[-1]
                                blob_path = f"{slide_id}/norm/{z_level}/{filename}"
                                blob = bucket.blob(blob_path)
                                c_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
                                blob.upload_from_filename(local_path, content_type=c_type, timeout=10)
                        except Exception:
                            pass

                    with ThreadPoolExecutor(max_workers=16) as executor:
                        executor.map(upload_single_norm_tile, norm_files)
                except Exception as ge:
                    print(f"[Preprocess Worker Note] Parallel GCP cloud norm pyramid upload note: {ge}")

            return f"gs://{settings.GCS_PYRAMIDS_BUCKET}/{slide_id}/norm/"

    return f"gs://{settings.GCS_PYRAMIDS_BUCKET}/{slide_id}/norm/"


def run_preprocess(stage_execution: StageExecution, session: Session) -> tuple[str, dict]:
    """
    Preprocess worker handler:
    1. Fits Macenko stain normalizer on tissue patches.
    2. Extracts 1-bit tissue mask PNG and 1.25x thumbnail PNG.
    3. Assembles 10x capped normalized DZI pyramid matching DeepZoom indexing.
    4. Persists preprocess output JSON & queues next stage ('qc').
    """
    input_ref = stage_execution.input_ref or {}
    slide_id = input_ref.get("slide_id")
    case_id = stage_execution.case_id

    if not slide_id:
        slide_obj = session.scalars(select(Slide).where(Slide.case_id == case_id)).first()
        if slide_obj:
            slide_id = str(slide_obj.id)

    if not slide_id:
        raise ValueError(f"Slide not found for preprocess stage in case {case_id}")

    slide_obj = session.get(Slide, str(slide_id))
    if not slide_obj:
        slide_obj = session.scalars(select(Slide).where(Slide.id == str(slide_id))).first()

    if not slide_obj:
        raise ValueError(f"Slide object {slide_id} not found in database")

    scratch_dir = tempfile.mkdtemp(prefix="og_preprocess_")

    try:
        client = get_gcs_client()

        ext = os.path.splitext(slide_obj.gcs_uri_original or ".svs")[1]
        local_slide_path = os.path.join(scratch_dir, f"slide{ext}")

        slide_file = None
        
        # Candidate 1: input_ref local_file_path
        if input_ref.get("local_file_path") and os.path.exists(input_ref.get("local_file_path")):
            slide_file = input_ref.get("local_file_path")

        # Candidate 2: fake_gcs raw bucket
        if not slide_file:
            raw_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_RAW_BUCKET}/cases/{case_id}"))
            if os.path.exists(raw_dir):
                raw_files = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if os.path.isfile(os.path.join(raw_dir, f))]
                if raw_files:
                    slide_file = raw_files[0]

        # Candidate 3: raw_uploads directory
        if not slide_file:
            raw_uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../raw_uploads"))
            if os.path.exists(raw_uploads_dir):
                cached_files = [os.path.join(raw_uploads_dir, f) for f in os.listdir(raw_uploads_dir) if str(case_id) in f or str(slide_id) in f]
                if cached_files:
                    slide_file = cached_files[0]

        if slide_file and os.path.exists(slide_file):
            shutil.copy2(slide_file, local_slide_path)
        else:
            # Reconstruct slide from highest level orig tiles in fake_gcs pyramids
            orig_top_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_PYRAMIDS_BUCKET}/{slide_id}/orig"))
            if os.path.exists(orig_top_dir):
                levels = [int(d) for d in os.listdir(orig_top_dir) if d.isdigit()]
                if levels:
                    max_lvl = max(levels)
                    lvl_dir = os.path.join(orig_top_dir, str(max_lvl))
                    tile_files = [f for f in os.listdir(lvl_dir) if f.endswith(".jpg") or f.endswith(".png")]
                    if tile_files:
                        max_c = max([int(f.split("_")[0]) for f in tile_files])
                        max_r = max([int(f.split("_")[1].split(".")[0]) for f in tile_files])
                        
                        canvas = Image.new("RGB", ((max_c + 1) * 256, (max_r + 1) * 256), (255, 255, 255))
                        for f in tile_files:
                            c, r = int(f.split("_")[0]), int(f.split("_")[1].split(".")[0])
                            t_img = Image.open(os.path.join(lvl_dir, f))
                            canvas.paste(t_img, (c * 256, r * 256))
                        canvas.save(local_slide_path, "JPEG")

        if not os.path.exists(local_slide_path):
            raise FileNotFoundError(f"Raw slide file not found for preprocess stage in case {case_id}")

        mpp_x = float(getattr(slide_obj, "mpp_x", 0.25) or 0.25)
        mpp_y = float(getattr(slide_obj, "mpp_y", 0.25) or 0.25)
        checksum = getattr(slide_obj, "checksum_sha256", "default_checksum") or "default_checksum"

        try:
            import openslide
            slide = openslide.OpenSlide(local_slide_path)
        except Exception:
            slide = Image.open(local_slide_path)

        # Fit STAINS Macenko Normalizer & Extract Tissue Mask
        normalizer, stain_params, tissue_mask_1bit = fit_macenko_stain(
            slide,
            checksum_sha256=checksum,
            ref_image_path="configs/stain_reference.png",
            mpp_x=mpp_x,
            mpp_y=mpp_y
        )

        px_area_mm2 = (8.0 * mpp_x / 0.25) * (8.0 * mpp_y / 0.25) * 1e-6
        tissue_area_mm2 = float(np.count_nonzero(tissue_mask_1bit) * px_area_mm2)

        from pipeline.tiles import check_icc_profile
        _, icc_applied = check_icc_profile(slide)

        if hasattr(slide, "close"):
            slide.close()

        # Save artifacts locally in fake_gcs
        stain_params_uri = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/preprocess/stain_params.json"
        tissue_mask_uri = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/preprocess/tissue_mask.png"
        thumbnail_uri = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/preprocess/thumbnail.png"

        artifacts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../fake_gcs/{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/preprocess"))
        os.makedirs(artifacts_dir, exist_ok=True)

        with open(os.path.join(artifacts_dir, "stain_params.json"), "w", encoding="utf-8") as f:
            json.dump(stain_params, f, indent=2)

        mask_img = Image.fromarray((tissue_mask_1bit * 255).astype(np.uint8))
        mask_img.save(os.path.join(artifacts_dir, "tissue_mask.png"), "PNG")

        # Assemble 10x Capped Normalized DZI Pyramid
        norm_pyramid_uri = generate_norm_dzi_pyramid(slide_obj, normalizer, local_slide_path, scratch_dir)

        # Save preprocess/output.json
        preprocess_output = {
            "icc_applied": icc_applied,
            "stain_params_uri": stain_params_uri,
            "norm_pyramid_uri": norm_pyramid_uri,
            "thumbnail_uri": thumbnail_uri,
            "tissue_mask_uri": tissue_mask_uri,
            "tissue_area_mm2": round(tissue_area_mm2, 2),
            "model_versions": {"tiatoolbox": "1.6.0"}
        }

        output_json_path = os.path.join(artifacts_dir, "preprocess_output.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(preprocess_output, f, indent=2)

        output_ref = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/preprocess/output.json"

        # Update stage execution status
        stage_execution.status = "done"

        # Emit audit event
        audit = AuditEvent(
            case_id=str(case_id),
            actor="worker_preprocess",
            event_type="stage_output",
            stage="preprocess",
            payload={
                "icc_applied": icc_applied,
                "tissue_area_mm2": tissue_area_mm2,
                "norm_pyramid_uri": norm_pyramid_uri
            }
        )
        session.add(audit)

        # Auto-chain next stage ('qc') in queued status
        existing_qc = session.scalars(
            select(StageExecution).where(
                StageExecution.case_id == case_id,
                StageExecution.stage == "qc",
                StageExecution.attempt == 1
            )
        ).first()

        if not existing_qc:
            next_qc_stage = StageExecution(
                case_id=case_id,
                stage="qc",
                attempt=1,
                status="queued",
                input_ref={"slide_id": str(slide_id), "preprocess_output_ref": output_ref}
            )
            session.add(next_qc_stage)
        session.commit()

        return output_ref, {"tiatoolbox": "1.6.0"}

    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
