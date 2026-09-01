# SatQuery AI — SIH26167

Agentic Vision-Language Assistant for Remote Sensing Imagery.

---

## Project Structure

```
satquery/
├── backend/
│   ├── app/
│   │   ├── agent/          # Agentic controller, planner, dispatcher, validator, registry
│   │   ├── api/            # FastAPI endpoints
│   │   ├── fusion/         # Evidence fusion + confidence estimation
│   │   ├── models/         # Pydantic schemas (ExecutionPlan, EvidenceObject, etc.)
│   │   ├── preprocessing/  # Geospatial pipeline (rasterio, SAR preprocessing)
│   │   ├── storage/        # SQLite trace store
│   │   └── tools/          # Specialist model tools (RS_VQA, CHANGE_DETECTION, etc.)
│   ├── configs/
│   │   └── registry.yaml   # Model/tool registry
│   ├── scripts/
│   │   ├── train_optical_sar.py   # Train DualEncoderFusion on SEN12MS + BigEarthNet
│   │   └── finetune_rsvqa.py      # Fine-tune RSVQA-HR
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios API client
│   │   ├── components/     # ImageUploadPanel, QueryBar, ResultsPanel, MapViewer
│   │   ├── types/          # TypeScript types matching backend schemas
│   │   └── utils/
│   ├── index.html
│   └── package.json
└── data/
    ├── uploads/            # Uploaded images
    ├── cache/              # Preprocessed tile cache
    ├── results/            # Generated overlays (change maps, segmentation)
    ├── traces/             # Job trace JSON files
    └── models/             # Downloaded/trained model weights
        ├── rsvqa_hr/
        ├── geochat/
        ├── changeformer/
        ├── changevlp/
        ├── cdvqa/
        ├── optical_sar_fusion/
        ├── sam/
        └── remoteclip/
```

---

## Backend Setup

### 1. Create virtual environment

```bash
cd satquery/backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS
```

### 2. Install dependencies

```bash
# Install GDAL first (Windows — use pre-built wheel)
pip install GDAL-3.8.4-cp311-cp311-win_amd64.whl

# Then install all requirements
pip install -r requirements.txt
```

> On Linux: `sudo apt install gdal-bin libgdal-dev` then `pip install GDAL==$(gdal-config --version)`

### 3. Configure environment

```bash
copy .env.example .env
# Edit .env to set ORCHESTRATOR_MODEL, DEFAULT_DEVICE, etc.
```

### 4. Run the backend

```bash
python run.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

## Frontend Setup

### Prerequisites
Install Node.js 20+ from https://nodejs.org

```bash
cd satquery/frontend
npm install
npm run dev
# Frontend at http://localhost:5173
```

---

## Model Weights

### Models that load automatically from HuggingFace (internet required first run)

| Model | HuggingFace ID | Local path |
|-------|---------------|------------|
| RemoteCLIP | `chendelong/RemoteCLIP` | `data/models/remoteclip/` |
| GeoChat | `MBZUAI/GeoChat` | `data/models/geochat/` |
| SAM-ViT-B | (direct URL) | `data/models/sam/sam_vit_b_01ec64.pth` |

Download SAM weights:
```bash
curl -L https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth \
     -o data/models/sam/sam_vit_b_01ec64.pth
```

Install SAM:
```bash
pip install git+https://github.com/facebookresearch/segment-anything.git
```

### Models requiring manual download (REQUIRES VERIFICATION)

| Model | Source | Local path |
|-------|--------|------------|
| ChangeFormer | https://github.com/wgcban/ChangeFormer | `data/models/changeformer/changeformer_levir.pth` |
| ChangeVLP | https://github.com/Chen-Yang-Liu/ChangeVLP | `data/models/changevlp/changevlp.pth` |
| CDVQA | https://github.com/YZHJessica/CDVQA | `data/models/cdvqa/cdvqa.pth` |

---

## Training (SIH Mandatory Fine-Tuning)

### Train DualEncoderFusion on SEN12MS + BigEarthNet

```bash
# Download SEN12MS: https://mediatum.ub.tum.de/1474000
# Download BigEarthNet: https://bigearth.net/

python scripts/train_optical_sar.py \
    --sen12ms_root /data/SEN12MS \
    --bigearth_root /data/BigEarthNet \
    --output_dir data/models/optical_sar_fusion \
    --epochs 30 \
    --batch_size 16 \
    --lr 1e-4
```

### Fine-tune RSVQA-HR

```bash
# Download RSVQA-HR: https://zenodo.org/record/6344334

python scripts/finetune_rsvqa.py \
    --rsvqa_root /data/RSVQA_HR \
    --output_dir data/models/rsvqa_hr \
    --epochs 20 \
    --batch_size 32
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload` | POST | Upload a satellite image. Returns `upload_id`. |
| `/query` | POST | Submit a query with image references. Returns `job_id`. |
| `/job/{id}/status` | GET | Poll job status. |
| `/job/{id}/result` | GET | Get final result + evidence object. |
| `/job/{id}/trace` | GET | Get full auditable execution trace. |
| `/results/{filename}` | GET | Serve generated overlay images. |
| `/health` | GET | Health check. |

### Example: Single-image VQA

```bash
# 1. Upload image
UPLOAD=$(curl -s -X POST http://localhost:8000/upload \
  -F "file=@my_image.tif" | python -c "import sys,json; print(json.load(sys.stdin)['upload_id'])")

# 2. Submit query
JOB_ID=$(python -c "import uuid; print(str(uuid.uuid4()))")
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"job_id\":\"$JOB_ID\",\"query\":\"What land cover dominates this image?\",\"image_roles\":{\"$UPLOAD\":\"PRIMARY\"}}"

# 3. Poll status
curl http://localhost:8000/job/$JOB_ID/status

# 4. Get result
curl http://localhost:8000/job/$JOB_ID/result
```

---

## Supported Tasks

| Task | Images Required | Models Used |
|------|----------------|-------------|
| Single-image VQA | 1 optical (role: PRIMARY) | RS_VQA |
| Scene captioning | 1 optical (role: PRIMARY) | RS_CAPTION |
| Region grounding | 1 optical (role: PRIMARY) | RS_GROUNDING + RS_GROUNDING_FALLBACK |
| Change detection | 2 optical (roles: T1, T2) | CHANGE_DETECTION + CHANGE_CAPTION |
| Change VQA | 2 optical (roles: T1, T2) | CHANGE_DETECTION + CHANGE_VQA |
| Optical+SAR analysis | 1 optical + 1 SAR (roles: OPTICAL, SAR) | SAR_PREPROCESS + OPTICAL_SAR_ANALYZER |

---

## SIH Requirement Compliance

| Requirement | Component |
|-------------|-----------|
| Single-image VQA | `RS_VQA` (RSVQA-HR) |
| Captioning | `RS_CAPTION` (GeoChat) |
| Text-guided grounding | `RS_GROUNDING` + `RS_GROUNDING_FALLBACK` (SAM) |
| Bi-temporal change analysis | `CHANGE_DETECTION` (ChangeFormer) + `CHANGE_CAPTION` (ChangeVLP) |
| Change VQA | `CHANGE_VQA` (CDVQA) |
| Optical + SAR cross-modal | `OPTICAL_SAR_ANALYZER` (DualEncoderFusion) |
| Fine-tuning on open RS dataset | DualEncoderFusion trained on SEN12MS + BigEarthNet; RSVQA fine-tuned on RSVQA-HR |
| GeoTIFF/TIFF input | `geo_pipeline.py` (rasterio) |
| PNG/JPEG for benchmarks | `geo_pipeline.py` (OpenCV) |
| Auditable execution trace | `trace_store.py` (SQLite) + `/job/{id}/trace` endpoint |
| Confidence estimation | `evidence_fusion.py` — weighted per-tool confidence |
| Visual overlays | Change maps + segmentation overlays served via `/results/` |

---

## GPU Requirements (MVP)

| Component | Min VRAM |
|-----------|----------|
| RSVQA-HR inference | 2 GB |
| GeoChat (4-bit) | 8 GB |
| ChangeFormer | 4 GB |
| DualEncoderFusion | 4 GB |
| SAM-ViT-B | 2 GB |
| Mistral-7B (4-bit orchestrator) | 6 GB |
| **All models simultaneously** | **~24 GB** (A100) |
| **MVP (lazy loading, one at a time)** | **8 GB** (RTX 3070/3080) |

Models are loaded lazily — only the tools needed for a given query are loaded.

---

## Known Limitations (MVP)

- ChangeVLP and CDVQA weights require manual verification of public availability.
- GeoChat grounding head availability requires verification.
- The DualEncoderFusion model requires training before use (weights not pretrained).
- Large GeoTIFF files (>500 MB) are tiled but stitching for VQA/captioning is not yet implemented.
- Confidence scores are estimates, not calibrated probabilities.

## Demo-safe fallback mode

The application no longer returns fake `[STUB]` answers when optional model checkpoints are missing. Every major task has a deterministic, real image-analysis fallback:

- Bi-temporal change detection: normalized pixel-difference + morphology + probability map.
- Change VQA/captioning: answers derived from the detected change mask and image statistics.
- Single-image VQA/captioning: transparent spectral/color statistics baseline.
- Grounding: semantic color/brightness masks + connected components; optional GrabCut refinement.
- Optical + SAR: optical spectral heuristics fused with SAR backscatter statistics.

Fallback outputs are explicitly labelled `BASELINE` in metadata. They are suitable for an offline demo, but they are **not a substitute for benchmark-trained ChangeFormer/GeoChat/CDVQA/ChangeVLP or the trained DualEncoderFusion model**. For SIH, use the trained checkpoints when reporting quantitative model accuracy.

### Analytical report

After a completed job, open `GET /job/{job_id}/report` to view a self-contained HTML report containing the query, task, answer, confidence, tools, detected regions, and spatial artifacts.

### Quick smoke test

```bash
cd backend
python scripts/smoke_test.py
```

## SIH26167 real-model setup

The project now prefers real research checkpoints when available and keeps the deterministic baselines only as an explicitly labelled fallback.

### 1) ChangeFormerV6 (recommended first)

From `backend/`:

```bash
python scripts/setup_models.py --changeformer
```

This clones the official ChangeFormer repository and installs the official LEVIR pretrained checkpoint under `data/models/changeformer/`. SatQuery will automatically discover it and use ChangeFormerV6 for bi-temporal change detection. The official repository documents its LEVIR pretrained model and evaluation pipeline.

### 2) RSVQA-HR via PaliGemma

Google publishes a PaliGemma 3B checkpoint fine-tuned specifically on RSVQA-HR. Accept the PaliGemma license on Hugging Face, authenticate, then run:

```bash
huggingface-cli login
cd backend
python scripts/setup_models.py --rsvqa
```

SatQuery defaults to this model through `RSVQA_BACKEND=paligemma` and `RSVQA_MODEL_ID=google/paligemma-3b-ft-rsvqa-hr-224`. If it cannot be loaded, the app falls back to the local RSVQA classifier and finally to the labelled heuristic baseline.

### 3) Verify ChangeFormer on your dataset

For a LEVIR-style directory containing `A/`, `B/`, and `label/`:

```bash
cd backend
python scripts/evaluate_changeformer.py --dataset /path/to/LEVIR-CD --limit 100
```

Do not put benchmark numbers in the SIH presentation until you have actually run this evaluation on your local checkpoint/dataset.

## Research-model setup (optional but recommended for SIH)

SatQuery deliberately separates the core API from heavyweight research checkpoints. The app uses transparent image-analysis baselines if a checkpoint is unavailable and labels those results as `BASELINE`.

For the strongest SIH demo, install the official research implementations:

```bash
cd backend
python scripts/setup_models.py --changeformer
python scripts/setup_models.py --rsvqa
python scripts/setup_models.py --geochat
python scripts/setup_models.py --deltavlm
```

### Models used

- **ChangeFormerV6** for bi-temporal pixel-level change detection (official LEVIR checkpoint).
- **PaliGemma 3B RSVQA-HR** for single-image remote-sensing VQA.
- **GeoChat-7B** for remote-sensing captioning and grounded region reasoning. GeoChat is specifically designed for RS VQA, captioning and grounding.
- **DeltaVLM** for bi-temporal change captioning and open-ended change VQA. It is an official RS change-analysis model with a released checkpoint.

GeoChat and DeltaVLM are large GPU workloads. They should be installed in their own research environments if dependency conflicts occur; SatQuery calls their official inference adapters rather than reimplementing their architectures.

### Important licensing/model notes

Some checkpoints require Hugging Face access approval or additional base-model weights. Do not commit model weights, tokens, or credentials into Git.

### SIH evidence mode

The UI/API metadata distinguishes `REAL_MODEL` from `BASELINE`. This is intentional: judges should never be shown a classical fallback as if it were a trained research checkpoint.


## Model status and deployment

The backend exposes `GET /models/status` so the UI/deployment can distinguish configured research checkpoints from transparent baseline fallbacks.

For GPU validation, `backend/scripts/hf_gpu_check.py` can be run as a Hugging Face Job. GPU jobs require available Hugging Face compute credits.

The application never labels a classical fallback as ChangeFormer, GeoChat, DeltaVLM, or RemoteCLIP.


## ₹0 deployment/development profile

SatQuery defaults to CPU-safe transparent baselines. Heavy models are optional. Use a temporary free Colab/Kaggle GPU session for benchmark/training work, then bring checkpoints back into `data/models/`. See `FREE_COMPUTE.md`.

## SIH26167 Judge Demo Flow

Use these three scenarios in the final demo:

1. **Bi-temporal change:** upload T1 + T2 → ask “What changed and how much area was affected?” → show change mask, area, GeoJSON and execution trace.
2. **Single-image grounding:** upload one optical image → ask “Locate the built-up area and show evidence.” → show bounding boxes + confidence.
3. **Optical + SAR cross-check:** upload optical + SAR → ask “Does SAR support the optical land-cover interpretation?” → show modality-specific evidence and fusion result.

Every result exposes model status (`REAL_MODEL`, `PRETRAINED_RS_VQA`, or `BASELINE`) so the demo never disguises a heuristic baseline as a trained model.
