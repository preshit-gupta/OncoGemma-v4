import os
import shutil
import socket

class LocalBucketEmulator:
    def __init__(self, bucket_name: str, base_dir: str):
        self.bucket_name = bucket_name
        self.bucket_dir = os.path.join(base_dir, bucket_name)
        os.makedirs(self.bucket_dir, exist_ok=True)

    def exists(self) -> bool:
        return True

    def blob(self, blob_name: str):
        return LocalBlobEmulator(self.bucket_dir, blob_name)

class LocalBlobEmulator:
    def __init__(self, bucket_dir: str, blob_name: str):
        self.blob_name = blob_name
        self.file_path = os.path.join(bucket_dir, blob_name.replace("/", os.sep))

    def exists(self) -> bool:
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

class LocalClientEmulator:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def bucket(self, bucket_name: str):
        return LocalBucketEmulator(bucket_name, self.base_dir)

    def create_bucket(self, bucket_name: str):
        return LocalBucketEmulator(bucket_name, self.base_dir)

def get_gcs_client():
    from app.core.config import settings
    
    use_real = os.getenv("USE_REAL_GCS", "true").lower() in ("true", "1") or settings.USE_REAL_GCS
    if use_real and not os.getenv("STORAGE_EMULATOR_HOST"):
        try:
            # Fast 0.5-second socket pre-flight to verify Google Cloud Storage API availability
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("storage.googleapis.com", 443))
            s.close()

            from google.cloud import storage
            client = storage.Client(project=settings.GCP_PROJECT_ID)
            return client
        except Exception as e:
            print(f"[GCS Core Note] Real GCS connection unreachable/fallback: {e}")

    local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fake_gcs"))
    return LocalClientEmulator(local_storage_dir)

def ensure_buckets_exist():
    from app.core.config import settings
    client = get_gcs_client()
    for bucket_name in [settings.GCS_RAW_BUCKET, settings.GCS_PYRAMIDS_BUCKET, settings.GCS_ARTIFACTS_BUCKET]:
        try:
            bucket = client.bucket(bucket_name)
            if hasattr(bucket, "exists") and not bucket.exists():
                client.create_bucket(bucket_name)
        except Exception as e:
            print(f"[GCS] Bucket check note for {bucket_name}: {e}")
