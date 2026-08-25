# OncoGemma v4 — Breast Cancer Diagnostic Copilot

OncoGemma is a copilot designed for pathologists to assist in handling H&E whole-slide images (WSIs) for breast tissue and generating CAP-compliant reports (Nottingham Histologic Grade).

## Architecture

OncoGemma v4 follows a 7-stage incremental workflow where intermediate outputs are validated by pathologists:
1. **v4.0 Walking Skeleton**: WSI Upload, Ingest (`pyvips` DZI tile generation), OpenSeadragon 5 viewer, FastAPI backend, Next.js frontend, audit log.
2. **v4.1 Preprocessing + QC Gate**: Macenko stain normalization, tissue coverage, focus variance, pen marks, fold detection.
3. **v4.2 Hotspot Triage**: Path Foundation embeddings (Vertex AI) + Logistic Regression linear probe, Annotorious polygon ROI editor.
4. **v4.3 Mitosis Detection**: 40x object-detection sweep (MIDOG published weights), virtual 10 HPFs placement ($r = 262\,\mu\text{m}$), live mitotic score.
5. **v4.4 Nottingham Grading**: MedGemma 1.5 per-patch tubule formation and pleomorphism assessment, deterministic code-level grade calculation (`tubule + pleo + mitosis`).
6. **v4.5 CAP Report + Sign-off**: Audit-ready signed clinical dossier (server-rendered PDF via WeasyPrint).
7. **v4.6 Hardening & Validation**: Batch harness vs archive slides, override analytics, cost logs.

## Setup & Local Development

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Node.js 20+

### Starting Local Services (Postgres 16 + Fake GCS Emulator)
```bash
docker-compose -f ops/docker-compose.yml up -d
```

### Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Worker Setup
```bash
cd backend
python -m worker.main
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Navigate to `http://localhost:3000` to access the OncoGemma workspace.
