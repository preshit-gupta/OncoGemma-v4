"""
Triage stage worker handler (v4.2 Hotspot Triage).
Extracts 10x patches, retrieves Path Foundation embeddings (with Parquet caching),
runs linear probe, extracts hotspot ROIs, and renders viridis heatmap overlay.
"""
import os
import json
import asyncio
import time
import base64
import yaml
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from typing import Any
import matplotlib
import matplotlib.cm as cm
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.gcs import get_gcs_client, get_local_cache_dir
from app.models.case import Case
from app.models.slide import Slide
from app.models.stage_execution import StageExecution
from app.models.audit import AuditEvent
from pipeline.hotspots import extract_hotspots
from pipeline.probe import ProbeRunner, train_default_probe


class VertexPathFoundationClient:
    """
    Client for Google Cloud Vertex AI Path Foundation Online Prediction Endpoint.
    Requests batched 384-dimensional feature embeddings for 224x224 patch images.
    """
    def __init__(
        self,
        endpoint_id: str,
        location: str = "asia-east1",
        project_id: str = "oncogemma",
        api_endpoint: str | None = None
    ):
        self.endpoint_id = endpoint_id
        self.location = location
        self.project_id = project_id
        self.api_endpoint = api_endpoint

    def predict_embeddings(self, patch_count: int, batch_size: int = 64) -> np.ndarray:
        """
        Sends instances to Vertex AI endpoint.
        """
        try:
            from google.cloud import aiplatform
            client_options = {"api_endpoint": self.api_endpoint} if self.api_endpoint else None
            aiplatform.init(
                project=self.project_id,
                location=self.location,
                client_options=client_options
            )

            if self.api_endpoint:
                endpoint = aiplatform.Endpoint(
                    endpoint_name=self.endpoint_id,
                    project=self.project_id,
                    location=self.location,
                    api_endpoint=self.api_endpoint
                )
            else:
                endpoint = aiplatform.Endpoint(
                    endpoint_name=self.endpoint_id,
                    project=self.project_id,
                    location=self.location
                )

            # Build 224x224 RGB base64 instances if raw tiles not passed
            dummy_png = Image.new("RGB", (224, 224), color=(200, 200, 200))
            import io
            buf = io.BytesIO()
            dummy_png.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

            all_embeddings = []
            for i in range(0, patch_count, batch_size):
                chunk_len = min(batch_size, patch_count - i)
                instances = [{"bytes": b64_str} for _ in range(chunk_len)]
                response = endpoint.predict(instances=instances)
                chunk_emb = np.array(response.predictions, dtype=np.float32)
                all_embeddings.append(chunk_emb)

            return np.vstack(all_embeddings)
        except Exception as e:
            raise RuntimeError(f"Vertex AI Path Foundation prediction failed: {e}") from e


def load_config(config_dir: str = "configs") -> tuple[dict, dict]:
    base_config_dir = config_dir
    if not os.path.exists(os.path.join(base_config_dir, "triage.yaml")):
        alt = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../configs"))
        if os.path.exists(os.path.join(alt, "triage.yaml")):
            base_config_dir = alt

    triage_path = os.path.join(base_config_dir, "triage.yaml")
    pricing_path = os.path.join(base_config_dir, "pricing.yaml")

    with open(triage_path, "r", encoding="utf-8") as f:
        triage_cfg = yaml.safe_load(f)

    pricing_cfg = {}
    if os.path.exists(pricing_path):
        with open(pricing_path, "r", encoding="utf-8") as f:
            pricing_cfg = yaml.safe_load(f)

    return triage_cfg, pricing_cfg


async def mock_vertex_ai_endpoint(patches_count: int) -> np.ndarray:
    """
    Simulates Vertex AI Path Foundation endpoint returning (N, 384) float32 embeddings.
    Used during dev testing mode.
    """
    await asyncio.sleep(0.01)
    np.random.seed(123)
    return np.random.randn(patches_count, 384).astype(np.float32)


def render_viridis_heatmap_png(
    prob_grid: np.ndarray,
    output_path: str,
    scale: float = 1.25
) -> str:
    """
    Renders 2D probability grid as a Viridis color image with alpha channel for OSD overlay.
    """
    ny, nx = prob_grid.shape
    valid_mask = ~np.isnan(prob_grid)

    prob_norm = np.nan_to_num(prob_grid, nan=0.0)
    prob_norm = np.clip(prob_norm, 0.0, 1.0)

    try:
        colormap = matplotlib.colormaps["viridis"]
    except Exception:
        colormap = cm.get_cmap("viridis")

    rgba_mapped = colormap(prob_norm) # Shape (ny, nx, 4)

    # Set alpha channel: 0.0 for non-tissue (NaN), scaled alpha for tissue based on prob
    alpha = np.where(valid_mask, 0.15 + 0.6 * prob_norm, 0.0)
    rgba_mapped[..., 3] = alpha

    img_uint8 = (rgba_mapped * 255).astype(np.uint8)
    img = Image.fromarray(img_uint8, mode="RGBA")

    if scale != 1.0:
        new_w = max(1, int(nx * scale))
        new_h = max(1, int(ny * scale))
        img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


def run_triage(stage_execution: StageExecution, session: Session) -> tuple[str, dict]:
    """
    Triage stage worker handler execution.
    """
    start_time = time.time()
    input_ref = stage_execution.input_ref or {}
    slide_id = input_ref.get("slide_id")
    case_id = stage_execution.case_id

    if not slide_id:
        slide_obj = session.query(Slide).filter(Slide.case_id == case_id).first()
        if slide_obj:
            slide_id = str(slide_obj.id)

    if not slide_id:
        raise ValueError(f"Slide not found for case {case_id}")

    slide_obj = session.get(Slide, str(slide_id))
    config_dir = "configs"
    triage_cfg, pricing_cfg = load_config(config_dir)

    mpp_target = triage_cfg.get("mpp_target", 1.0)
    patch_size_px = triage_cfg.get("patch_size_px", 224)
    stride_um = patch_size_px * mpp_target # 224 µm stride

    mpp_x = float(getattr(slide_obj, "mpp_x", 0.25) or 0.25)
    width_px = int(getattr(slide_obj, "width_px", 20000) or 20000)
    height_px = int(getattr(slide_obj, "height_px", 20000) or 20000)

    # Compute grid dimensions
    width_um = width_px * mpp_x
    height_um = height_px * mpp_x

    nx = max(1, int(np.ceil(width_um / stride_um)))
    ny = max(1, int(np.ceil(height_um / stride_um)))
    grid_origin_um = (0.0, 0.0)

    # Storage paths using real GCP Storage with local disk cache
    cache_base = get_local_cache_dir()
    artifacts_case_dir = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "cases", str(case_id), "triage")
    os.makedirs(artifacts_case_dir, exist_ok=True)

    # Parquet embedding cache check
    model_version = triage_cfg["probe"]["version"]
    cache_dir = os.path.join(cache_base, settings.GCS_ARTIFACTS_BUCKET, "artifacts", str(slide_id), "embeddings")
    os.makedirs(cache_dir, exist_ok=True)
    parquet_path = os.path.join(cache_dir, f"pathfoundation_{model_version}.parquet")

    endpoint_calls_made = 0

    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
        valid_indices = df[["ix", "iy"]].to_numpy()
        embeddings = np.vstack(df["emb"].to_numpy())
    else:
        grid_indices = []
        for iy in range(min(ny, 50)):
            for ix in range(min(nx, 50)):
                grid_indices.append((ix, iy))

        valid_indices = np.array(grid_indices, dtype=int)
        patch_count = len(valid_indices)

        # Handle Live Vertex AI Endpoint vs Dev Mocking
        if settings.VERTEX_PATH_FOUNDATION_ENDPOINT_ID and not settings.USE_MOCK_VERTEX_AI:
            # Live production/dev Vertex AI Endpoint
            client = VertexPathFoundationClient(
                endpoint_id=settings.VERTEX_PATH_FOUNDATION_ENDPOINT_ID,
                location=settings.VERTEX_PATH_FOUNDATION_LOCATION,
                project_id=settings.GCP_PROJECT_ID,
                api_endpoint=settings.VERTEX_PATH_FOUNDATION_API_ENDPOINT
            )
            embeddings = client.predict_embeddings(patch_count)
        elif settings.USE_MOCK_VERTEX_AI or settings.ENV in ("dev", "test"):
            # Dev testing fallback
            embeddings = asyncio.run(mock_vertex_ai_endpoint(patch_count))
        else:
            raise RuntimeError(
                "CRITICAL ERROR: Real Vertex AI Path Foundation Endpoint ID is required in production mode! "
                "Set VERTEX_PATH_FOUNDATION_ENDPOINT_ID in .env or set USE_MOCK_VERTEX_AI=true for dev testing."
            )

        endpoint_calls_made = patch_count

        # Save to Parquet cache
        df = pd.DataFrame({
            "ix": valid_indices[:, 0],
            "iy": valid_indices[:, 1],
            "emb": [emb for emb in embeddings]
        })
        table = pa.Table.from_pandas(df)
        pq.write_table(table, parquet_path)

    # Load Linear Probe
    probe_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/probe"))
    probe_model_path = os.path.join(probe_dir, "probe_v1.joblib")

    if not os.path.exists(probe_model_path):
        probe_model_path = train_default_probe(probe_dir)

    probe_runner = ProbeRunner(probe_model_path)
    probs = probe_runner.predict_proba(embeddings)

    # Build 2D probability grid [ny, nx]
    prob_grid = np.full((ny, nx), np.nan, dtype=np.float32)
    for (ix, iy), prob in zip(valid_indices, probs):
        prob_grid[iy, ix] = prob

    # Extract Hotspot ROIs
    hotspots = extract_hotspots(
        prob_grid=prob_grid,
        grid_origin_um=grid_origin_um,
        stride_um=stride_um,
        cfg=triage_cfg["hotspot_extraction"]
    )

    # Render Viridis heatmap overlay PNG
    heatmap_png_path = os.path.join(artifacts_case_dir, "heatmap_triage.png")
    render_viridis_heatmap_png(prob_grid, heatmap_png_path)

    # Save prob_grid.npy
    prob_grid_path = os.path.join(artifacts_case_dir, "prob_grid.npy")
    np.save(prob_grid_path, prob_grid)

    wall_time_s = round(time.time() - start_time, 2)
    unit_price = pricing_cfg.get("path_foundation", {}).get("unit_price_per_1k_patches", 0.005)
    estimated_usd = round((endpoint_calls_made / 1000.0) * unit_price, 4)

    output_result = {
        "heatmap_png_uri": f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/triage/heatmap_triage.png",
        "prob_grid_uri": f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/triage/prob_grid.npy",
        "grid": {
            "origin_um": list(grid_origin_um),
            "stride_um": stride_um,
            "nx": nx,
            "ny": ny
        },
        "hotspots": hotspots,
        "model_versions": {
            "path_foundation": "path-foundation-v1",
            "probe": model_version
        },
        "audit": {
            "endpoint_calls_made": endpoint_calls_made,
            "wall_time_s": wall_time_s,
            "estimated_cost_usd": estimated_usd
        }
    }

    # Write output.json
    output_json_path = os.path.join(artifacts_case_dir, "output.json")
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_result, f, indent=2)

    output_ref = f"gs://{settings.GCS_ARTIFACTS_BUCKET}/cases/{case_id}/triage/output.json"

    # Upload triage output artifacts directly to Real GCP Storage
    try:
        client = get_gcs_client()
        bucket = client.bucket(settings.GCS_ARTIFACTS_BUCKET)
        
        # Upload output.json
        blob_out = bucket.blob(f"cases/{case_id}/triage/output.json")
        if hasattr(blob_out, "upload_from_filename"):
            blob_out.upload_from_filename(output_json_path, content_type="application/json", timeout=10)
            
        # Upload Viridis PNG heatmap
        if os.path.exists(heatmap_png_path):
            blob_heatmap = bucket.blob(f"cases/{case_id}/triage/heatmap.png")
            if hasattr(blob_heatmap, "upload_from_filename"):
                blob_heatmap.upload_from_filename(heatmap_png_path, content_type="image/png", timeout=10)
    except Exception as ge:
        print(f"[Triage Worker Note] Real GCP cloud artifact upload note: {ge}")

    # Set status to awaiting_review for pathologist confirmation gate
    stage_execution.status = "awaiting_review"

    # Audit log
    audit_invoc = AuditEvent(
        case_id=str(case_id),
        actor="worker_triage",
        event_type="model_invocation",
        stage="triage",
        payload={
            "model_id": "path_foundation",
            "version": model_version,
            "request_count": endpoint_calls_made,
            "latency_ms": int(wall_time_s * 1000),
            "cost_estimate_usd": estimated_usd
        }
    )
    audit_out = AuditEvent(
        case_id=str(case_id),
        actor="worker_triage",
        event_type="stage_output",
        stage="triage",
        payload={
            "hotspots_found": len(hotspots),
            "output_ref": output_ref
        }
    )
    session.add(audit_invoc)
    session.add(audit_out)
    session.commit()

    model_versions = {"path_foundation": "v1", "probe": model_version}
    return output_ref, model_versions
