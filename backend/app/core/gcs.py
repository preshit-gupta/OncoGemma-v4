import os
from google.cloud import storage
from app.core.config import settings

def get_gcs_client() -> storage.Client:
    """
    Returns a configured Google Cloud Storage client.
    Uses STORAGE_EMULATOR_HOST if running in local dev mode.
    """
    emulator_host = os.getenv("STORAGE_EMULATOR_HOST") or settings.STORAGE_EMULATOR_HOST
    if emulator_host:
        os.environ["STORAGE_EMULATOR_HOST"] = emulator_host
        # For fake-gcs-server, anonymous credentials can be used
        return storage.Client.create_anonymous_client()
    return storage.Client()

def ensure_buckets_exist():
    """Ensure local buckets exist when running with fake-gcs-server emulator."""
    client = get_gcs_client()
    for bucket_name in [settings.GCS_RAW_BUCKET, settings.GCS_PYRAMIDS_BUCKET, settings.GCS_ARTIFACTS_BUCKET]:
        try:
            bucket = client.bucket(bucket_name)
            if not bucket.exists():
                client.create_bucket(bucket_name)
        except Exception as e:
            print(f"[GCS] Bucket check note for {bucket_name}: {e}")
