import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.db import Base, get_db

# In-memory SQLite DB for fast isolated unit testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_auth_test_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

def test_healthz_endpoint():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data

def test_mock_auth_headers():
    # Valid default header
    response = client.get("/api/v1/cases", headers={"X-User-Role": "pathologist"})
    assert response.status_code == 200

    # Invalid role header -> 403 Forbidden
    response_invalid = client.get("/api/v1/cases", headers={"X-User-Role": "unauthorized_role"})
    assert response_invalid.status_code == 403

def test_create_and_get_case():
    # Create case
    res = client.post("/api/v1/cases", headers={"X-User-Role": "pathologist", "X-User-Id": "path_001"})
    assert res.status_code == 201
    case_data = res.json()
    case_id = case_data["id"]
    assert case_data["created_by"] == "path_001"

    # Get case details
    res_detail = client.get(f"/api/v1/cases/{case_id}", headers={"X-User-Role": "pathologist"})
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["id"] == case_id
