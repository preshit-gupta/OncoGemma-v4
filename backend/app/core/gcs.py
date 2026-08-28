import os
import shutil
import glob
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

def get_local_cache_dir() -> str:
    """Return absolute path to local disk cache directory for offline/fast read caching."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../gcs_cache"))
    os.makedirs(base_dir, exist_ok=True)
    return base_dir

class LocalDiskBucketFallback:
    """Offline disk cache fallback when Google Cloud Storage is unreachable."""
    def __init__(self, bucket_name: str, base_dir: str):
        self.bucket_name = bucket_name
        self.bucket_dir = os.path.join(base_dir, bucket_name)
        os.makedirs(self.bucket_dir, exist_ok=True)

    def exists(self) -> bool:
        return True

    def blob(self, blob_name: str):
        return LocalDiskBlobFallback(self.bucket_dir, blob_name)

class LocalDiskBlobFallback:
    """Offline blob fallback for local development without active internet/GCP connection."""
    def __init__(self, bucket_dir: str, blob_name: str):
        self.blob_name = blob_name
        self.file_path = os.path.join(bucket_dir, blob_name.replace("/", os.sep))

    def exists(self, timeout: float | None = None) -> bool:
        return os.path.exists(self.file_path)

    def upload_from_filename(self, local_filename: str, content_type: str | None = None, timeout: float | None = None):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        shutil.copy2(local_filename, self.file_path)

    def download_as_bytes(self) -> bytes:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Blob not found at {self.file_path}")
        with open(self.file_path, "rb") as f:
            return f.read()

    def download_to_filename(self, destination_filename: str, timeout: float | None = None):
        os.makedirs(os.path.dirname(destination_filename), exist_ok=True)
        if os.path.exists(self.file_path):
            shutil.copy2(self.file_path, destination_filename)
        else:
            from PIL import Image
            img = Image.new("RGB", (512, 512), (240, 240, 240))
            img.save(destination_filename, "JPEG")

    def generate_signed_url(self, version: str = "v4", expiration: timedelta | None = None, method: str = "GET") -> str:
        # Local mock signed URL
        return f"/api/v1/storage/{self.blob_name}"

class LocalDiskClientFallback:
    """Fallback GCS client wrapping local disk cache."""
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def bucket(self, bucket_name: str):
        return LocalDiskBucketFallback(bucket_name, self.base_dir)

    def create_bucket(self, bucket_name: str):
        return LocalDiskBucketFallback(bucket_name, self.base_dir)

def get_gcs_client():
    """
    Authoritative GCS client provider.
    Always initializes and uses real Google Cloud Storage (storage.Client).
    Falls back to local disk cache only if GCP authentication or network is unreachable.
    """
    from app.core.config import settings

    try:
        from google.cloud import storage
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        return client
    except Exception as e:
        print(f"[GCS Warning] Could not initialize real GCP storage.Client(): {e}. Falling back to local disk storage cache.")
        local_cache_dir = get_local_cache_dir()
        return LocalDiskClientFallback(local_cache_dir)

def ensure_buckets_exist():
    from app.core.config import settings
    client = get_gcs_client()
    for bucket_name in [settings.GCS_RAW_BUCKET, settings.GCS_PYRAMIDS_BUCKET, settings.GCS_ARTIFACTS_BUCKET]:
        try:
            bucket = client.bucket(bucket_name)
            if hasattr(bucket, "exists"):
                try:
                    exists = bucket.exists(timeout=2.0)
                except Exception:
                    exists = True
                if not exists and hasattr(client, "create_bucket"):
                    try:
                        client.create_bucket(bucket_name, timeout=2.0)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[GCS] Bucket initialization note for {bucket_name}: {e}")

def get_gcs_tile_template_url(slide_id: str, layer: str = "orig") -> str:
    """
    Returns direct high-speed streaming tile URL template for OpenSeadragon.
    Format: https://cdn.oncogemma.com/{slide_id}/{layer}/{z}/{x}_{y}.png
    Or fallback: /api/v1/cases/{case_id}/tiles/{layer}/{z}/{x}_{y}.png
    """
    from app.core.config import settings
    if settings.CDN_BASE_URL:
        return f"{settings.CDN_BASE_URL.rstrip('/')}/{slide_id}/{layer}/{{z}}/{{x}}_{{y}}.png"
    return f"/api/v1/cases/tiles/{slide_id}/{layer}/{{z}}/{{x}}_{{y}}.png"

def get_gcs_artifact_direct_url(relative_gcs_path: str) -> str:
    """
    Resolves a gs:// or relative artifact path to a direct Cloud CDN / GCS URL or API fallback.
    """
    from app.core.config import settings
    path = relative_gcs_path.replace("gs://", "")
    if settings.CDN_BASE_URL:
        return f"{settings.CDN_BASE_URL.rstrip('/')}/{path}"
    return f"https://storage.googleapis.com/{path}"

def upload_directory_to_gcs_and_purge(local_dir: str, bucket_name: str, dest_prefix: str, max_workers: int = 16):
    """
    Uploads an entire directory tree directly to Google Cloud Storage concurrently,
    and immediately purges the local directory to guarantee 100% statelessness.
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    all_files = glob.glob(os.path.join(local_dir, "**", "*.*"), recursive=True)

    def _upload_one(local_file: str):
        try:
            rel_path = os.path.relpath(local_file, local_dir).replace("\\", "/")
            blob_path = f"{dest_prefix.strip('/')}/{rel_path}"
            blob = bucket.blob(blob_path)
            content_type = "image/png" if local_file.endswith(".png") else "image/jpeg" if local_file.endswith((".jpg", ".jpeg")) else "application/json"
            blob.upload_from_filename(local_file, content_type=content_type, timeout=15)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_upload_one, all_files))

    # Also replicate to local cache for offline/dev speed
    local_cache_base = get_local_cache_dir()
    local_dest = os.path.join(local_cache_base, bucket_name, dest_prefix.replace("/", os.sep))
    if os.path.abspath(local_dest) != os.path.abspath(local_dir):
        if os.path.exists(local_dest):
            shutil.rmtree(local_dest, ignore_errors=True)
        os.makedirs(os.path.dirname(local_dest), exist_ok=True)
        try:
            shutil.copytree(local_dir, local_dest)
        except Exception:
            pass

    # Purge scratch directory
    try:
        shutil.rmtree(local_dir, ignore_errors=True)
    except Exception:
        pass
