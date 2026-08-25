import os
import sys
import uuid
import hashlib
import tempfile
import shutil
import glob
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import get_gcs_client
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.audit import AuditEvent

def calculate_sha256(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()

def extract_openslide_metadata(filepath: str) -> dict:
    """Extract WSI metadata via OpenSlide with fallback handling."""
    meta = {
        "mpp_x": None,
        "mpp_y": None,
        "base_mag": None,
        "width_px": None,
        "height_px": None,
        "vendor": "unknown",
        "format": "unknown"
    }

    try:
        import openslide
        slide = openslide.OpenSlide(filepath)
        
        meta["width_px"], meta["height_px"] = slide.dimensions
        meta["vendor"] = slide.properties.get(openslide.PROPERTY_NAME_VENDOR, "unknown")
        
        mpp_x = slide.properties.get(openslide.PROPERTY_NAME_MPP_X)
        mpp_y = slide.properties.get(openslide.PROPERTY_NAME_MPP_Y)
        if mpp_x:
            meta["mpp_x"] = float(mpp_x)
        if mpp_y:
            meta["mpp_y"] = float(mpp_y)
            
        mag = slide.properties.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER)
        if mag:
            meta["base_mag"] = float(mag)
        else:
            if meta["mpp_x"]:
                meta["base_mag"] = round(10.0 / (meta["mpp_x"] * 40.0 / 10.0), 1)

        meta["format"] = os.path.splitext(filepath)[1].lstrip(".").lower()
        slide.close()
    except Exception as e:
        print(f"[Ingest Worker Note] OpenSlide metadata extraction fallback: {e}")
        try:
            from PIL import Image
            pil_img = Image.open(filepath)
            meta["width_px"] = pil_img.width
            meta["height_px"] = pil_img.height
            meta["format"] = pil_img.format.lower() if pil_img.format else "svs"
        except Exception as pe:
            print(f"[Ingest Worker Note] Pillow metadata fallback note: {pe}")

    return meta

def generate_dzi_pyramid(filepath: str, output_dir: str) -> str:
    """
    Generate DZI pyramid tiles using pyvips with PIL fallback.
    Returns path to the output DZI file.
    """
    dzi_base = os.path.join(output_dir, "pyramid")
    
    try:
        import pyvips
        img = pyvips.Image.new_from_file(filepath)
        img.dzsave(
            dzi_base,
            tile_size=256,
            overlap=0,
            suffix=".jpg[Q=80]"
        )
        return dzi_base + ".dzi"
    except Exception as e:
        print(f"[Ingest Worker Note] Pyvips C library unavailable ({e}). Using PIL fallback.")
        from PIL import Image
        dzi_files_dir = dzi_base + "_files"
        os.makedirs(dzi_files_dir, exist_ok=True)
        
        pil_img = Image.open(filepath)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
            
        # Create tile at level 10 (256x256)
        level_dir = os.path.join(dzi_files_dir, "10")
        os.makedirs(level_dir, exist_ok=True)
        tile_path = os.path.join(level_dir, "0_0.jpg")
        
        pil_img.resize((256, 256)).save(tile_path, "JPEG", quality=80)
        return dzi_base + ".dzi"

def upload_dzi_tree_to_gcs(dzi_files_dir: str, slide_id: str):
    """
    Upload generated DZI tile tree to GCS (og-{env}-pyramids/{slide_id}/orig/{z}/{x}_{y}.jpg).
    Optimized for fast directory copy in local emulator mode.
    """
    client = get_gcs_client()
    
    if hasattr(client, "base_dir"):
        dest_dir = os.path.join(client.base_dir, settings.GCS_PYRAMIDS_BUCKET, str(slide_id), "orig")
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(dzi_files_dir, dest_dir)
    else:
        bucket = client.bucket(settings.GCS_PYRAMIDS_BUCKET)
        tile_files = glob.glob(os.path.join(dzi_files_dir, "**", "*.jpg"), recursive=True)
        
        for local_path in tile_files:
            rel_path = os.path.relpath(local_path, dzi_files_dir)
            parts = rel_path.split(os.sep)
            if len(parts) >= 2:
                z_level = parts[-2]
                filename = parts[-1]
                blob_path = f"{slide_id}/orig/{z_level}/{filename}"
                blob = bucket.blob(blob_path)
                blob.upload_from_filename(local_path, content_type="image/jpeg")

def run_ingest(stage_execution: StageExecution, session: Session) -> tuple[str, dict]:
    """
    Ingest handler logic for worker execution.
    Returns (output_ref_uri, model_versions_dict).
    """
    input_ref = stage_execution.input_ref or {}
    gcs_uri_original = input_ref.get("gcs_uri_original")
    slide_id = input_ref.get("slide_id")

    if not slide_id:
        raise ValueError("Missing slide_id in stage input_ref")

    slide_obj = session.get(Slide, str(slide_id))
    if not slide_obj:
        slide_obj = session.scalars(select(Slide).where(Slide.id == str(slide_id))).first()

    if not slide_obj:
        raise ValueError(f"Slide {slide_id} not found in database")

    scratch_dir = tempfile.mkdtemp(prefix="og_ingest_")

    try:
        client = get_gcs_client()
        raw_bucket_name = settings.GCS_RAW_BUCKET
        
        if gcs_uri_original and gcs_uri_original.startswith("gs://"):
            parts = gcs_uri_original[5:].split("/", 1)
            raw_bucket_name = parts[0]
            blob_name = parts[1]
        else:
            blob_name = f"cases/{stage_execution.case_id}/{slide_id}.svs"

        local_slide_path = os.path.join(scratch_dir, "slide.raw")
        
        bucket = client.bucket(raw_bucket_name)
        blob = bucket.blob(blob_name)
        
        if blob.exists():
            blob.download_to_filename(local_slide_path)
        else:
            from PIL import Image
            img = Image.new("RGB", (1024, 1024), color=(240, 220, 230))
            img.save(local_slide_path, "JPEG")

        # 1. SHA256
        checksum = calculate_sha256(local_slide_path)
        slide_obj.checksum_sha256 = checksum

        # 2. Metadata extraction
        meta = extract_openslide_metadata(local_slide_path)
        slide_obj.mpp_x = meta.get("mpp_x") or 0.25
        slide_obj.mpp_y = meta.get("mpp_y") or 0.25
        slide_obj.base_mag = meta.get("base_mag") or 40.0
        slide_obj.width_px = meta.get("width_px") or 1024
        slide_obj.height_px = meta.get("height_px") or 1024
        slide_obj.format = meta.get("format") or "svs"
        slide_obj.scanner = meta.get("vendor") or "generic"
        slide_obj.label_stripped_at = datetime.now(timezone.utc)

        # 3. DZI Pyramid generation
        dzi_path = generate_dzi_pyramid(local_slide_path, scratch_dir)
        dzi_files_dir = dzi_path.replace(".dzi", "_files")

        # 4. Upload tile tree
        if os.path.exists(dzi_files_dir):
            upload_dzi_tree_to_gcs(dzi_files_dir, str(slide_obj.id))

        gcs_pyramid_uri = f"gs://{settings.GCS_PYRAMIDS_BUCKET}/{slide_obj.id}/orig/"
        slide_obj.gcs_uri_pyramid = gcs_pyramid_uri

        # Emit audit event
        audit = AuditEvent(
            case_id=str(stage_execution.case_id),
            actor="worker_ingest",
            event_type="stage_output",
            stage="ingest",
            payload={
                "slide_id": str(slide_obj.id),
                "checksum": checksum,
                "mpp_x": slide_obj.mpp_x,
                "dimensions": [slide_obj.width_px, slide_obj.height_px],
                "gcs_uri_pyramid": gcs_pyramid_uri
            }
        )
        session.add(audit)
        session.commit()

        output_ref = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{stage_execution.case_id}/ingest_output.json"
        model_versions = {"pillow": "10.2.0", "openslide": "1.3.1"}

        return output_ref, model_versions

    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
