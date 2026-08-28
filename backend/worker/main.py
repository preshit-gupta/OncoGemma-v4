import time
import uuid
import traceback
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine
from app.models.stage_execution import StageExecution
from worker.ingest import run_ingest
from worker.preprocess import run_preprocess
from worker.qc import run_qc
from worker.triage import run_triage
from worker.mitosis import run_mitosis
from worker.grading import run_grading

HANDLERS = {
    "ingest": run_ingest,
    "preprocess": run_preprocess,
    "qc": run_qc,
    "triage": run_triage,
    "mitosis": run_mitosis,
    "grading": run_grading
}

def reset_stuck_running_stages():
    """Reset any orphan stages left in 'running' state by previous worker restarts."""
    db = SessionLocal()
    try:
        stmt = update(StageExecution).where(StageExecution.status == "running").values(status="queued")
        res = db.execute(stmt)
        db.commit()
        if res.rowcount > 0:
            print(f"[Worker Startup] Reset {res.rowcount} stuck 'running' stages back to 'queued'...")
    except Exception as e:
        print(f"[Worker Startup Reset Note] {e}")
    finally:
        db.close()

def poll_and_execute_single_task():
    """
    Executes a single queued task using SQLAlchemy ORM queue fetch.
    """
    db: Session = SessionLocal()
    try:
        stages_list = list(HANDLERS.keys())
        stmt = (
            select(StageExecution)
            .where(
                StageExecution.status == "queued",
                StageExecution.stage.in_(stages_list)
            )
            .order_by(StageExecution.started_at.asc().nulls_first(), StageExecution.id.asc())
            .limit(1)
        )

        stage_exec = db.scalars(stmt).first()
        if not stage_exec:
            return False

        # Mark as running
        stage_exec.status = "running"
        stage_exec.started_at = datetime.now(timezone.utc)
        db.commit()

        print(f"[Worker] Processing stage '{stage_exec.stage}' for case {stage_exec.case_id} (attempt {stage_exec.attempt})...")

        try:
            handler = HANDLERS[stage_exec.stage]
            out_uri, model_versions = handler(stage_exec, db)

            if stage_exec.status == "running":
                stage_exec.status = "done"
            stage_exec.output_ref = out_uri
            stage_exec.model_versions = model_versions
            stage_exec.completed_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[Worker] Successfully completed stage '{stage_exec.stage}' for case {stage_exec.case_id} (Status: {stage_exec.status}).")

        except Exception as e:
            db.rollback()
            err_msg = traceback.format_exc()
            print(f"[Worker ERROR] Stage '{stage_exec.stage}' failed for case {stage_exec.case_id}: {e}")
            try:
                stage_exec_curr = db.get(StageExecution, stage_exec.id)
                if stage_exec_curr:
                    stage_exec_curr.status = "failed"
                    stage_exec_curr.error = err_msg
                    stage_exec_curr.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as e2:
                print(f"[Worker Fail State Error] {e2}")

        return True

    finally:
        db.close()

def run_worker_loop():
    print(f"[Worker] Starting OncoGemma stage worker poll loop. Engine: {engine.dialect.name}. Handlers: {list(HANDLERS.keys())}")
    reset_stuck_running_stages()
    while True:
        try:
            executed = poll_and_execute_single_task()
            if not executed:
                time.sleep(1.0)
        except Exception as e:
            print(f"[Worker Loop Exception] {e}")
            time.sleep(3.0)

if __name__ == "__main__":
    run_worker_loop()
