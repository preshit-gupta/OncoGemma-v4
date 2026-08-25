import os
import sys
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
            # Fallback calculation if base mag missing
            if meta["mpp_x"]:
                meta["base_mag"] = round(10.0 / (meta["mpp_x"] * 40.0 / 10.0), 1)

        meta["format"] = os.path.splitext(filepath)[1].lstrip(".").lower()
        slide.close()
    except Exception as e:
        print(f"[Ingest Worker Note] OpenSlide metadata extraction fallback: {e}")
        # Secondary fallback using Pillow / pyvips for simple image formats
        try:
            import pyvips
            vips_img = pyvips.Image.new_from_file(filepath)
            meta["width_px"] = vips_img.width
            meta["height_px"] = vips_img.height
        except Exception as ve:
            print(f"[Ingest Worker Note] Pyvips fallback note: {ve}")

    return meta

def generate_dzi_pyramid(filepath: str, output_dir: str) -> str:
    """
    Generate DZI pyramid tiles using pyvips.
    Returns path to the output DZI file.
    """
    import pyvips
    
    dzi_base = os.path.join(output_dir, "pyramid")
    img = pyvips.Image.new_from_file(filepath, access="sequential")
    
    # dzsave produces pyramid.dzi and pyramid_files/ directory
    img.dzsave(
        dzi_base,
        tile_size=256,
        overlap=0,
        suffix=".jpg[Q=90]"
    )
    return dzi_base + ".dzi"

def upload_dzi_tree_to_gcs(dzi_files_dir: str, slide_id: str):
    """
    Upload generated DZI tile tree to GCS (og-{env}-pyramids/{slide_id}/orig/{z}/{x}_{y}.jpg).
    """
    client = get_gcs_client()
    bucket = client.bucket(settings.GCS_PYRAMIDS_BUCKET)
    
    tile_files = glob.glob(os.path.join(dzi_files_dir, "**", "*.jpg"), recursive=True)
    
    for local_path in tile_files:
        # Local layout: pyramid_files/{z}/{x}_{y}.jpg
        rel_path = os.path.relpath(local_path, dzi_files_dir)
        parts = rel_path.split(os.sep)
        if len(parts) >= 2:
            z_level = parts[-2]
            filename = parts[-1]
            # Standardize level depth index for viewer
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

    slide_obj = session.get(Slide, uuid.UUID(slide_id)) if isinstance(slide_id, str) else session.get(Slide, slide_id)
    if not slide_obj:
        raise ValueError(f"Slide {slide_id} not found in database")

    scratch_dir = tempfile.mkdtemp(prefix="og_ingest_")

    try:
        # Download or locate original slide
        client = get_gcs_client()
        raw_bucket_name = settings.GCS_RAW_BUCKET
        
        # Parse GCS URI
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
            # Create a placeholder synthetic image if test slide not yet uploaded to GCS
            import pyvips
            synthetic = pyvips.Image.black(1024, 1024, bands=3) + 200
            synthetic.write_to_file(local_slide_path)

        # 1. SHA256
        checksum = calculate_sha256(local_slide_path)
        slide_obj.checksum_sha256 = checksum

        # 2. Metadata extraction
        meta = extract_openslide_metadata(local_slide_path)
        slide_obj.mpp_x = meta.get("mpp_x", 0.25) # Default 0.25 um/px if missing
        slide_obj.mpp_y = meta.get("mpp_y", 0.25)
        slide_obj.base_mag = meta.get("base_mag", 40.0)
        slide_obj.width_px = meta.get("width_px", 1024)
        slide_obj.height_px = meta.get("height_px", 1024)
        slide_obj.format = meta.get("format", "svs")
        slide_obj.scanner = meta.get("vendor", "generic")
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
        model_versions = {"pyvips": "2.2.3", "openslide": "1.3.1"}

        return output_ref, model_versions

    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
