import time
import traceback
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.stage_execution import StageExecution
from worker.ingest import run_ingest

HANDLERS = {
    "ingest": run_ingest
}

def poll_and_execute_single_task():
    """
    Executes a single queued task using Postgres FOR UPDATE SKIP LOCKED.
    Returns True if a task was found and executed, False if queue was empty.
    """
    db: Session = SessionLocal()
    try:
        # 1. Acquire next available queued stage execution row atomically
        stmt = text("""
            SELECT id FROM stage_executions
            WHERE status = 'queued' AND stage = ANY(:stages)
            ORDER BY started_at NULLS FIRST, id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)
        
        row = db.execute(stmt, {"stages": list(HANDLERS.keys())}).first()
        if not row:
            return False

        exec_id = row[0]
        stage_exec = db.get(StageExecution, exec_id)
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

            stage_exec.status = "done" # Ingest has no review gate in v4.0
            stage_exec.output_ref = out_uri
            stage_exec.model_versions = model_versions
            stage_exec.completed_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[Worker] Successfully completed stage '{stage_exec.stage}' for case {stage_exec.case_id}.")

        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"[Worker ERROR] Stage '{stage_exec.stage}' failed for case {stage_exec.case_id}: {e}")
            stage_exec.status = "failed"
            stage_exec.error = err_msg
            stage_exec.completed_at = datetime.now(timezone.utc)
            db.commit()

        return True

    finally:
        db.close()

def run_worker_loop():
    print(f"[Worker] Starting OncoGemma stage worker poll loop. Handlers registered: {list(HANDLERS.keys())}")
    while True:
        try:
            executed = poll_and_execute_single_task()
            if not executed:
                time.sleep(2.0)
        except Exception as e:
            print(f"[Worker Loop Exception] {e}")
            time.sleep(5.0)

if __name__ == "__main__":
    run_worker_loop()
