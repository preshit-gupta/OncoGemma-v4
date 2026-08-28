# OncoGemma Stage v4.4: Nottingham Histologic Grading & Architectural Synthesis (MedGemma 1.5)

OncoGemma is an enterprise-grade clinical AI copilot for automated Whole-Slide Image (WSI) processing, hotspot triage, and Nottingham Histological Grading of invasive breast carcinoma.

This repository branch (`v4.4` / `v4.4-nottingham-grading`) implements **Stage v4.4 (Nottingham Histological Grading via MedGemma 1.5 & Pure Zero-LLM Aggregation)**, combining cell-level mitotic counts from Stage v4.3 with automated architectural analysis across 24 normalized $10\times$ evidence patches to establish Tubule Formation, Nuclear Pleomorphism, CAP Histologic Subtype, and live Nottingham Grade.

---

## 🏗️ Architecture & Pipeline Overview

```mermaid
flowchart TD
    A["Confirmed Stage 3 Hotspots + Stage 4 Mitotic Score"] -->|"Stratified Top-50% Draw (Seeded RNG) + Top-3 Hottest"| B["Sample 24 Evidence Patches (512x512 @ 1.0 µm/px)"]
    B --> C["Macenko Stain Normalizer Transform"]
    C --> D["Persist Patch PNGs to gcs_cache/{case_id}/grading_patches/"]
    
    D -->|"Async Batch (Concurrency <= 4)"| E1["MedGemma 1.5: Tubule Assessment (24 calls)"]
    D -->|"Async Batch (Concurrency <= 4)"| E2["MedGemma 1.5: Pleomorphism Assessment (24 calls)"]
    D -->|"Multi-Image Call (Top-8 Patches)"| E3["MedGemma 1.5: Histologic Subtype (1 call)"]
    
    E1 -->|"Schema Validation + Pydantic Parsing"| F["Parsed Machine Responses"]
    E2 -->|"Schema Validation + Pydantic Parsing"| F
    E3 -->|"Schema Validation + Pydantic Parsing"| F
    
    F -->|"Pure Zero-LLM Calculation (pipeline/grading.py)"| G["Deterministic Aggregation Engine"]
    G -->|"Weighted Median (Tubule %) -> Score 1/2/3"| H1["Tubule Score (T)"]
    G -->|"Weighted Mode (Tie -> Worst Grade)"| H2["Pleomorphism Score (P)"]
    A -->|"From Stage 4"| H3["Mitotic Score (M)"]
    
    H1 & H2 & H3 -->|"T + P + M = Nottingham Sum"| I["Nottingham Grade (Grade 1 / 2 / 3)"]
    G -->|"Quality Checks (len < 8 or variance > 30%)"| J["Quality Flags (amber UI alerts)"]
    I & J -->|"Aggregated JSON Input Only"| K["MedGemma 1.5: Grounded Findings Narrative"]
    
    I & K & E3 --> L["Stage 5 Pathologist Review Workspace"]
    L -->|"Override T or P (>=10 char justification)"| M["Live Reactive Recalculation + Manually Assigned Chip"]
    L -->|"Mandatory Type Confirmation Gate"| N["Explicit Pathologist Sign-Off"]
    N -->|"Commit to DB (CHECK Constraint Enforced)"| O["Persist to gradings Table + Audit Logs -> Advance to Stage 6"]
```

---

## 🔬 Mathematical Specification & Invariants

### 1. Tubule Formation
- Filtered to tumor-containing patches:
  $$\text{Tubule } \% = \text{WeightedMedian}\left(\{\text{tubule\_percent}_i\}, w_i\right) \quad \text{where } w_i = \{ \text{low}: 0.5, \text{medium}: 1.0, \text{high}: 1.5 \}$$
- Nottingham sub-score mapping:
  - **Score 1**: $> 75\%$
  - **Score 2**: $10\% - 75\%$
  - **Score 3**: $< 10\%$

### 2. Nuclear Pleomorphism
- Conservative mode across 24 patches:
  $$\text{Pleomorphism Score} = \text{WeightedMode}\left(\{\text{pleomorphism\_score}_i\}, w_i\right)$$
- **Tie-Breaking Rule**: Ties resolve strictly to the higher score (conservative clinical bias favoring the worse grade).

### 3. Nottingham Histological Grade Synthesis (Zero-LLM Guard)
- Pure integer sum:
  $$\text{Nottingham Sum} = \text{Tubule Score} + \text{Pleomorphism Score} + \text{Mitotic Score}$$
- Final grade determination:
  - **Grade 1 (Well Differentiated)**: Sum $3 - 5$
  - **Grade 2 (Moderately Differentiated)**: Sum $6 - 7$
  - **Grade 3 (Poorly Differentiated)**: Sum $8 - 9$

### 4. Database Invariant & Guard
Enforced directly via PostgreSQL / SQLite `CHECK` constraint:
```sql
CHECK (grade = CASE WHEN tubule_score + pleo_score + mitotic_score <= 5 THEN 1 
                    WHEN tubule_score + pleo_score + mitotic_score <= 7 THEN 2 
                    ELSE 3 END)
```

---

## 🛠️ Key REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/stages/grading/{case_id}` | Retrieve complete Stage 5 state (patches, machine sub-scores, histologic type, narrative, overrides, grade) |
| `GET` | `/api/v1/stages/grading/{case_id}/patches/{id}/image` | Stream 512×512 normalized evidence patch PNG |
| `POST` | `/api/v1/stages/grading/recompute` | Live debounced sub-score preview endpoint (<10ms execution) |
| `POST` | `/api/v1/stages/grading/confirm` | Clinical safety gate, validates mandatory type confirmation & justifications, persists final grading, queues Stage 6 |

---

## 🧪 Verification & Automated Testing

Run the full test suite (46 tests):
```bash
pytest backend/tests/ -v
```

Build the Next.js frontend:
```bash
cd frontend
npm run build
```
