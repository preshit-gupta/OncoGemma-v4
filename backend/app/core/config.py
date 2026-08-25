import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "local"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://oncogemma:oncogemma_dev_password@localhost:5432/oncogemma_db"
    )
    
    # GCS Configuration
    GCS_RAW_BUCKET: str = "og-local-raw"
    GCS_PYRAMIDS_BUCKET: str = "og-local-pyramids"
    GCS_ARTIFACTS_BUCKET: str = "og-local-artifacts"
    STORAGE_EMULATOR_HOST: str | None = os.getenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    
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
