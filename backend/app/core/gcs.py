import os
import shutil

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

    def upload_from_filename(self, local_filename: str, content_type: str | None = None):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        shutil.copy2(local_filename, self.file_path)

    def download_as_bytes(self) -> bytes:
        with open(self.file_path, "rb") as f:
            return f.read()

    def download_to_filename(self, destination_filename: str):
        os.makedirs(os.path.dirname(destination_filename), exist_ok=True)
        shutil.copy2(self.file_path, destination_filename)

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
    emulator_host = os.getenv("STORAGE_EMULATOR_HOST") or settings.STORAGE_EMULATOR_HOST
    if emulator_host:
        try:
            from google.cloud import storage
            os.environ["STORAGE_EMULATOR_HOST"] = emulator_host
            return storage.Client.create_anonymous_client()
        except Exception:
            pass
    
    local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fake_gcs"))
    return LocalClientEmulator(local_storage_dir)

def ensure_buckets_exist():
    from app.core.config import settings
    client = get_gcs_client()
    for bucket_name in [settings.GCS_RAW_BUCKET, settings.GCS_PYRAMIDS_BUCKET, settings.GCS_ARTIFACTS_BUCKET]:
        try:
            bucket = client.bucket(bucket_name)
        except Exception as e:
            print(f"[GCS] Local storage init note for {bucket_name}: {e}")
