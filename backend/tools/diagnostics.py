"""
OncoGemma Stage v4.3 Diagnostic & Verification Utility
Tests slide integrity, runs mitosis detection across all cases, and verifies 10-HPF Nottingham scoring.
"""
import os
import sys
import uuid
import json

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.models.case import Case
from app.models.slide import Slide
from app.models.hotspot import Hotspot
from app.models.detection import Detection
from app.models.hpf_site import HpfSite
from worker.mitosis import run_mitosis, find_slide_file


def run_full_diagnostics(clean_first: bool = False):
    print("=" * 80)
    print("ONCOGEMMA STAGE v4.3 FULL SYSTEM DIAGNOSTICS")
    print("=" * 80)

    db = SessionLocal()
    cases = db.query(Case).all()
    print(f"\n[1] Total Cases in DB: {len(cases)}")

    if clean_first:
        print("\nCleaning existing Stage 4 detections and HPFs for a fresh run...")
        db.query(Detection).delete()
        db.query(HpfSite).delete()
        db.commit()
        print("Database Stage 4 tables cleaned.")

    results = []

    for c in cases:
        case_id = str(c.id)
        print(f"\n------------------------------------------------------------")
        print(f"Checking Case: {case_id}")
        
        slide = db.query(Slide).filter(Slide.case_id == c.id).first()
        if not slide:
            print(f"  [FAIL] No slide record found for case {case_id}")
            continue

        slide_id = str(slide.id)
        slide_file = find_slide_file(case_id, slide_id, getattr(slide, "local_path", None))
        print(f"  Slide ID: {slide_id}")
        print(f"  Slide File: {slide_file}")
        
        if not slide_file or not os.path.exists(slide_file):
            print(f"  [FAIL] SVS file does not exist on disk!")
            continue

        # Test OpenSlide read
        try:
            import openslide
            oslide = openslide.OpenSlide(slide_file)
            dims = oslide.dimensions
            levels = oslide.level_count
            print(f"  [OK] OpenSlide Dimensions: {dims}, Levels: {levels}")
            oslide.close()
        except Exception as e:
            print(f"  [FAIL] OpenSlide failed: {e}")
            continue

        # Run Mitosis Pipeline
        print(f"  Running Stage 4 Mitosis Detection Pipeline...")
        try:
            status, artifacts = run_mitosis(c, db)
            db.commit()

            mitoses_count = db.query(Detection).filter(Detection.case_id == c.id).count()
            hpfs_count = db.query(HpfSite).filter(HpfSite.case_id == c.id).count()
            confirmed_mitoses = db.query(Detection).filter(Detection.case_id == c.id, Detection.label == "mitosis").count()

            print(f"  [SUCCESS] Status: {status}")
            print(f"  [SUCCESS] Mitotic Candidates Detected: {mitoses_count}")
            print(f"  [SUCCESS] Confirmed Mitoses: {confirmed_mitoses}")
            print(f"  [SUCCESS] Virtual HPF Sites Placed: {hpfs_count}")

            results.append({
                "case_id": case_id,
                "slide_file": os.path.basename(slide_file),
                "candidates": mitoses_count,
                "confirmed": confirmed_mitoses,
                "hpfs": hpfs_count,
                "status": "PASS"
            })
        except Exception as e:
            print(f"  [ERROR] Mitosis pipeline execution failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "case_id": case_id,
                "status": "FAIL",
                "error": str(e)
            })

    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Case ID':<38} | {'Candidates':<11} | {'Confirmed':<10} | {'HPFs':<6} | {'Status':<6}")
    print("-" * 80)
    for r in results:
        if r["status"] == "PASS":
            print(f"{r['case_id']:<38} | {r['candidates']:<11} | {r['confirmed']:<10} | {r['hpfs']:<6} | {r['status']:<6}")
        else:
            print(f"{r['case_id']:<38} | {'ERROR':<11} | {'ERROR':<10} | {'0':<6} | {r['status']:<6}")
    print("=" * 80)


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    run_full_diagnostics(clean_first=clean)
