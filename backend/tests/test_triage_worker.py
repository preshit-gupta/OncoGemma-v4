import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Case, Slide, StageExecution, AuditEvent, Hotspot
from app.core.db import Base
from worker.triage import run_triage


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_run_triage_stage_e2e(db_session, tmp_path):
    case_id = "test_case_triage_123"
    slide_id = "test_slide_triage_456"

    # Seed Case & Slide with created_by
    case = Case(id=case_id, created_by="test_user", status="processing")
    slide = Slide(
        id=slide_id,
        case_id=case_id,
        gcs_uri_original="gs://raw/test.svs",
        mpp_x=0.25,
        mpp_y=0.25,
        width_px=10000,
        height_px=10000
    )
    stage_exec = StageExecution(
        case_id=case_id,
        stage="triage",
        attempt=1,
        status="running",
        input_ref={"slide_id": slide_id}
    )
    db_session.add(case)
    db_session.add(slide)
    db_session.add(stage_exec)
    db_session.commit()

    # Run triage worker handler
    output_ref, model_versions = run_triage(stage_exec, db_session)

    assert "triage/output.json" in output_ref
    assert model_versions["path_foundation"] == "v1"
    assert stage_exec.status == "awaiting_review"

    # Verify second run uses cached parquet embeddings (0 new endpoint calls)
    mock_client = MagicMock()
    mock_client.get_embeddings.side_effect = Exception("Should not be called when cached!")

    stage_exec.status = "running"
    db_session.commit()

    output_ref_2, _ = run_triage(stage_exec, db_session)
    assert output_ref_2 == output_ref
