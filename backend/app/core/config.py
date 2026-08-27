import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
    DEBUG: bool = True
    
    # GCP
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "oncogemma")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")
    USE_REAL_GCS: bool = os.getenv("USE_REAL_GCS", "true").lower() in ("true", "1")
    
    # Vertex AI Endpoint Configuration
    VERTEX_PATH_FOUNDATION_ENDPOINT_ID: str = os.getenv(
        "VERTEX_PATH_FOUNDATION_ENDPOINT_ID",
        "mg-endpoint-b556566c-9220-4e82-8d6b-96c28e8392aa"
    )
    VERTEX_PATH_FOUNDATION_LOCATION: str = os.getenv(
        "VERTEX_PATH_FOUNDATION_LOCATION",
        "asia-east1"
    )
    VERTEX_PATH_FOUNDATION_API_ENDPOINT: str = os.getenv(
        "VERTEX_PATH_FOUNDATION_API_ENDPOINT",
        "mg-endpoint-b556566c-9220-4e82-8d6b-96c28e8392aa.asia-east1-250493189138.prediction.vertexai.goog"
    )
    USE_MOCK_VERTEX_AI: bool = os.getenv("USE_MOCK_VERTEX_AI", "false").lower() in ("true", "1")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://oncogemma:oncogemma_dev_password@localhost:5432/oncogemma_db"
    )
    
    # GCS Configuration
    GCS_RAW_BUCKET: str = os.getenv("GCS_RAW_BUCKET", "oncogemma-dev-raw")
    GCS_PYRAMIDS_BUCKET: str = os.getenv("GCS_PYRAMIDS_BUCKET", "oncogemma-dev-pyramids")
    GCS_ARTIFACTS_BUCKET: str = os.getenv("GCS_ARTIFACTS_BUCKET", "oncogemma-dev-artifacts")
    STORAGE_EMULATOR_HOST: str | None = os.getenv("STORAGE_EMULATOR_HOST", None)
    
    # Auth
    MOCK_AUTH_ENABLED: bool = True
    DEFAULT_MOCK_ROLE: str = "pathologist"
    DEFAULT_MOCK_USER_ID: str = "user_pathologist_001"
    
    # Config directory
    CONFIGS_DIR: str = os.path.join(os.path.dirname(__file__), "../../../configs")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
