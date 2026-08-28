"""
OncoGemma Stage v4.3 - Pure Nottingham Mitotic Scoring Engine.
Computes point-in-circle containment of mitotic figures within virtual HPFs,
calculates standardized area-normalized density (mitoses/mm²), and assigns
Elston-Ellis Nottingham Mitotic Scores (Score 1, 2, or 3).
"""
import math
import os
from typing import List, Dict, Any, Tuple, Optional
import yaml


def calculate_hpf_mitosis_counts(
    candidates: List[Dict[str, Any]],
    hpfs: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Computes which mitotic candidates fall inside each virtual HPF circle.
    Updates the 'count' field on each HPF and returns updated HPF list + total count.
    
    A candidate is considered a confirmed mitosis if label == "mitosis".
    """
    updated_hpfs = []
    mitoses_in_any_hpf = set()

    for hpf in hpfs:
        hpf_copy = dict(hpf)
        cx, cy = hpf_copy["center_um"]
        r = float(hpf_copy.get("radius_um", 262.0))
        r_sq = r * r

        hpf_mitosis_count = 0
        for cand in candidates:
            if cand.get("label") != "mitosis":
                continue

            cand_x, cand_y = cand["centroid_um"]
            dist_sq = (cand_x - cx) ** 2 + (cand_y - cy) ** 2
            if dist_sq <= r_sq:
                hpf_mitosis_count += 1
                mitoses_in_any_hpf.add(cand.get("id"))

        hpf_copy["count"] = hpf_mitosis_count
        updated_hpfs.append(hpf_copy)

    total_count = len(mitoses_in_any_hpf)
    return updated_hpfs, total_count


def compute_nottingham_mitotic_score(
    count_total: int,
    n_hpf: int = 10,
    radius_um: float = 262.0,
    config_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Computes Nottingham Mitotic Score based on standardized mm² area normalization.
    
    Standard thresholds (Elston-Ellis):
      - Score 1: < 3.65 mitoses/mm²  (Classic: 0 - 9 / 2.74 mm²)
      - Score 2: 3.65 - 7.30 mitoses/mm² (Classic: 10 - 19 / 2.74 mm²)
      - Score 3: >= 7.30 mitoses/mm² (Classic: >= 20 / 2.74 mm²)
    """
    score2_min = 3.65
    score3_min = 7.30
    classic_area_mm2 = 2.74

    if config_dict and "mitotic_score" in config_dict:
        m_cfg = config_dict["mitotic_score"]
        thresh = m_cfg.get("thresholds", {})
        score2_min = thresh.get("score2_min", score2_min)
        score3_min = thresh.get("score3_min", score3_min)

    # Calculate actual cumulative HPF inspection area
    # Area of one HPF circle = pi * (radius_um / 1000)^2 mm²
    # For r = 262 um: pi * 0.262^2 = 0.215651 mm² -> 10 HPFs = 2.157 mm²
    single_hpf_area_mm2 = math.pi * ((radius_um / 1000.0) ** 2)
    area_mm2 = max(0.001, float(n_hpf * single_hpf_area_mm2))

    density = float(count_total) / area_mm2
    classic_per_10hpf = density * classic_area_mm2

    # Determine score
    if density >= score3_min:
        mitotic_score = 3
    elif density >= score2_min:
        mitotic_score = 2
    else:
        mitotic_score = 1

    return {
        "count_total": int(count_total),
        "n_hpf": int(n_hpf),
        "area_mm2": round(area_mm2, 3),
        "per_mm2": round(density, 2),
        "classic_per_10hpf": round(classic_per_10hpf, 1),
        "mitotic_score": mitotic_score
    }
