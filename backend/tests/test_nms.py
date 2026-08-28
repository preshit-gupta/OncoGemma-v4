"""
Unit tests for Global Cross-Tile NMS in Physical Micrometer Space (v4.3).
"""
import pytest
from pipeline.detect import apply_global_nms


def test_global_nms_suppression():
    candidates = [
        # Candidate 1: high confidence
        {"id": "m1", "centroid_um": [500.0, 500.0], "det_conf": 0.90},
        # Candidate 2: within 5.0 um of m1 -> should be suppressed
        {"id": "m2", "centroid_um": [503.0, 504.0], "det_conf": 0.70},
        # Candidate 3: 15.0 um away from m1 -> should be kept
        {"id": "m3", "centroid_um": [515.0, 500.0], "det_conf": 0.85},
        # Candidate 4: within 4.0 um of m3 -> should be suppressed
        {"id": "m4", "centroid_um": [517.0, 502.0], "det_conf": 0.60},
    ]

    survivors = apply_global_nms(candidates, nms_radius_um=7.5)

    assert len(survivors) == 2
    survivor_ids = [c["id"] for c in survivors]
    assert "m1" in survivor_ids
    assert "m3" in survivor_ids
    assert "m2" not in survivor_ids
    assert "m4" not in survivor_ids


def test_global_nms_empty():
    assert apply_global_nms([]) == []
