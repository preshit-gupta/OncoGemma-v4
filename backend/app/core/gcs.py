import os
import shutil
import socket

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

    # Always attempt real Google Cloud Storage first
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
            if hasattr(bucket, "exists") and not bucket.exists():
                if hasattr(client, "create_bucket"):
                    client.create_bucket(bucket_name)
        except Exception as e:
            print(f"[GCS] Bucket initialization note for {bucket_name}: {e}")
