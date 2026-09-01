# SatQuery AI Architecture

## System Overview

SatQuery AI is an agentic vision-language assistant for remote sensing imagery. It combines geospatial preprocessing, multi-modal deep learning, and autonomous task orchestration to answer complex queries about satellite imagery.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React + Leaflet)                   │
│  - Image upload panel                                            │
│  - Query input interface                                         │
│  - Interactive map viewer                                        │
│  - Results visualization                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/WebSocket
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Port 8000)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           API Layer (main.py)                            │   │
│  │  - /upload          (POST multipart/form-data)           │   │
│  │  - /query           (POST JSON query)                    │   │
│  │  - /job/{id}/status (GET job status)                     │   │
│  │  - /job/{id}/result (GET job result)                     │   │
│  │  - /job/{id}/trace  (GET execution trace)                │   │
│  │  - /health          (GET health check)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                        │
│         ┌───────────────┼───────────────┐                       │
│         ▼               ▼               ▼                       │
│  ┌─────────────┐ ┌────────────┐ ┌──────────────┐               │
│  │ Preprocessing│ │Agent/Planner│ │ Storage/Trace│               │
│  │  Pipeline   │ │  & Dispatch │ │   System     │               │
│  └─────────────┘ └────────────┘ └──────────────┘               │
│         │               │               │                       │
│  ┌─────┴───────┐       │          ┌────┴─────┐                │
│  │ Rasterio/   │       │          │ SQLite   │                │
│  │ Pyproj/     │       ▼          │ (traces) │                │
│  │ Shapely     │  ┌────────────────────────┐ │                │
│  │             │  │ Tool/Model Registry    │ │                │
│  │ - GeoTIFF   │  │                        │ │                │
│  │ - Reproject │  │ - RSVQA_HR             │ │                │
│  │ - Tile      │  │ - ChangeFormer         │ │                │
│  │ - SAR prep  │  │ - GeoChat              │ │                │
│  │ - Normalize │  │ - ChangeVLP            │ │                │
│  │             │  │ - CDVQA                │ │                │
│  └─────────────┘  │ - SAM                  │ │                │
│                   │ - RemoteCLIP           │ │                │
│                   │ - Optical-SAR Fusion   │ │                │
│                   │                        │ │                │
│                   └────────────────────────┘ │                │
│                                              │                │
│                   ┌──────────────────────┐   │                │
│                   │ Fusion & Validation  │   │                │
│                   │ - Evidence Fusion    │   │                │
│                   │ - Confidence Est.    │   │                │
│                   │ - Answer Validator   │   │                │
│                   └──────────────────────┘   │                │
└─────────────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌────────┐    ┌──────────────┐    ┌───────────┐
   │ Uploads│    │ Cache/Results│    │ Models    │
   │Directory│    │ Directory    │    │ Directory │
   └────────┘    └──────────────┘    └───────────┘
```

## Directory Structure

```
satquery/
├── backend/
│   ├── app/
│   │   ├── agent/              # Agentic orchestration
│   │   │   ├── controller.py   # Main orchestrator
│   │   │   ├── planner.py      # Query planning
│   │   │   ├── dispatcher.py   # Tool dispatch
│   │   │   ├── validator.py    # Result validation
│   │   │   └── registry.py     # Model/tool registry
│   │   │
│   │   ├── api/                # FastAPI routes
│   │   │   └── main.py         # Endpoints & middleware
│   │   │
│   │   ├── preprocessing/      # Geospatial pipeline
│   │   │   ├── geo_pipeline.py # Format detection, ingestion
│   │   │   ├── sar_processor.py# SAR-specific processing
│   │   │   └── normalizer.py   # Data normalization
│   │   │
│   │   ├── fusion/             # Evidence fusion
│   │   │   ├── fusion.py       # Fusion algorithm
│   │   │   └── confidence.py   # Confidence estimation
│   │   │
│   │   ├── tools/              # Specialist models
│   │   │   ├── rsvqa.py        # Remote sensing VQA
│   │   │   ├── change_detect.py# Change detection
│   │   │   ├── segmentation.py # Segmentation tools
│   │   │   └── vlm.py          # Vision-language models
│   │   │
│   │   ├── models/             # Pydantic schemas
│   │   │   ├── schemas.py      # Input/output schemas
│   │   │   └── config.py       # Configuration classes
│   │   │
│   │   ├── storage/            # Data persistence
│   │   │   ├── trace_store.py  # Execution traces
│   │   │   ├── migrations.py   # DB migrations
│   │   │   └── schema.sql      # Schema definition
│   │   │
│   │   └── config.py           # Global configuration
│   │
│   ├── configs/
│   │   └── registry.yaml       # Model registry
│   │
│   ├── scripts/
│   │   ├── train_optical_sar.py# Training scripts
│   │   └── finetune_rsvqa.py   # Fine-tuning scripts
│   │
│   ├── tests/                  # Unit & integration tests
│   │   ├── conftest.py         # Test fixtures
│   │   ├── test_api.py         # API endpoint tests
│   │   ├── test_preprocessing.py
│   │   ├── test_agent.py       # Agent logic tests
│   │   └── test_fusion.py
│   │
│   ├── requirements.txt         # Production dependencies
│   ├── requirements-dev.txt     # Development dependencies
│   ├── .env.example             # Environment template
│   ├── run.py                   # Development runner
│   ├── run_server.py            # Production runner
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── api/               # Axios API client
│   │   │   └── client.ts      # Typed API calls
│   │   │
│   │   ├── components/        # React components
│   │   │   ├── ImageUploadPanel.tsx
│   │   │   ├── QueryBar.tsx
│   │   │   ├── ResultsPanel.tsx
│   │   │   └── MapViewer.tsx
│   │   │
│   │   ├── types/             # TypeScript interfaces
│   │   │   └── index.ts       # Shared types
│   │   │
│   │   ├── hooks/             # Custom React hooks
│   │   │   └── useApi.ts      # API integration
│   │   │
│   │   ├── utils/             # Utility functions
│   │   │   ├── validation.ts
│   │   │   └── formatting.ts
│   │   │
│   │   ├── App.tsx            # Root component
│   │   └── main.tsx           # Entry point
│   │
│   ├── tests/                 # Frontend tests
│   │   ├── components/
│   │   └── utils/
│   │
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── .eslintrc
│   ├── .prettierrc
│   └── postcss.config.js
│
├── data/
│   ├── uploads/              # Uploaded images (user)
│   ├── cache/                # Preprocessed cache
│   ├── results/              # Generated outputs
│   ├── traces/               # Execution traces (JSON)
│   └── models/               # Model weights
│
├── docker-compose.yml        # Container orchestration
├── Dockerfile
├── README.md                 # Project overview
├── CONTRIBUTING.md          # Contribution guidelines
├── CODE_OF_CONDUCT.md       # Community guidelines
├── ARCHITECTURE.md          # This file
├── CHANGELOG.md             # Version history
├── LICENSE                  # MIT License
├── DEPLOYMENT.md            # Deployment guide
└── .gitignore
```

## Key Components

### Agent Controller (agent/controller.py)

Orchestrates the query processing pipeline:

1. **Receives** query + upload_id
2. **Invokes Planner** → generates ExecutionPlan with tool sequence
3. **Invokes Dispatcher** → executes tools, collects evidence
4. **Invokes Fusion** → combines evidence, estimates confidence
5. **Invokes Validator** → checks answer quality
6. **Returns** result or routes to fallback

```python
execution_plan = await planner.plan(query, image_metadata)
evidence = await dispatcher.execute(execution_plan)
fused_result = await fusion.fuse(evidence)
validated_result = await validator.validate(fused_result)
```

### Preprocessing Pipeline (preprocessing/geo_pipeline.py)

Standardizes diverse geospatial inputs:

- **Format Detection**: GeoTIFF, SAR, PNG, JPEG
- **Projection Handling**: Reproject to EPSG:4326 (WGS84)
- **Tiling**: 256x256 or 512x512 tiles for model input
- **Normalization**: Standardize bands, handle outliers
- **Caching**: Store preprocessed tiles for reuse

### Tool Registry (agent/registry.py)

Dynamically loads and validates available models:

```yaml
models:
  rsvqa_hr:
    path: data/models/rsvqa_hr/model.pth
    type: vqa
    input_modalities: [RGB, Multispectral]
  changeformer:
    path: data/models/changeformer/model.pth
    type: change_detection
    input_modalities: [SAR, Multispectral]
```

### Fusion & Validation (fusion/)

Combines predictions from multiple models:

1. **Evidence Collection**: Gather outputs from all executed tools
2. **Confidence Estimation**: Compute per-model confidence
3. **Weighted Fusion**: Combine results with learned weights
4. **Validation**: Check answer coherence and metadata

## Data Flow

### Query Processing Flow

```
User Query
    ↓
[API: /query endpoint]
    ↓
[Upload validation]
    ↓
[Preprocessing pipeline]
    ├→ Detect format/modality
    ├→ Load geospatial metadata
    ├→ Normalize & tile
    └→ Cache preprocessed data
    ↓
[Planner: Generate execution plan]
    ├→ Analyze query intent
    ├→ Match to available tools
    └→ Order execution sequence
    ↓
[Dispatcher: Execute tools]
    ├→ Load model weights
    ├→ Prepare input batches
    ├→ Run inference
    └→ Collect outputs + metadata
    ↓
[Fusion: Combine evidence]
    ├→ Weight predictions
    ├→ Estimate confidence
    └→ Generate fused answer
    ↓
[Validator: Check quality]
    ├→ Verify coherence
    ├→ Check confidence threshold
    └→ Decide final answer
    ↓
[Storage: Persist trace]
    ├→ Save execution log
    ├→ Store results
    └→ Compress trace data
    ↓
Job Result → Frontend
```

### Storage Schema

**Jobs Table** (SQLite)
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'processing',  -- queued, processing, completed, failed
    result_json TEXT,
    error_message TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

**Traces Table** (JSON files in data/traces/)
```json
{
  "job_id": "uuid",
  "timestamp": "ISO-8601",
  "upload_id": "uuid",
  "query": "What changes between these dates?",
  "planning": {
    "intent": "change_detection",
    "selected_tools": ["changeformer", "cdvqa"]
  },
  "execution": {
    "tool_results": [
      {
        "tool": "changeformer",
        "status": "success",
        "output": {...},
        "confidence": 0.85,
        "execution_time_ms": 245
      }
    ]
  },
  "fusion": {
    "fused_answer": "...",
    "confidence_score": 0.87
  },
  "validation": {
    "passed": true,
    "quality_score": 0.91
  }
}
```

## API Endpoints

### POST /upload
- **Body**: multipart/form-data with image file
- **Response**: `{upload_id: uuid, modality: "RGB", format: "GeoTIFF", metadata: {...}}`
- **Status**: 200, 413 (too large), 415 (unsupported format)

### POST /query
- **Body**: `{upload_id: uuid, query: string, parameters: {...}}`
- **Response**: `{job_id: uuid, status: "queued"}`
- **Status**: 200, 400 (invalid query), 404 (upload not found)

### GET /job/{id}/status
- **Response**: `{job_id: uuid, status: "processing", progress: 0.75}`
- **Status**: 200, 404 (job not found)

### GET /job/{id}/result
- **Response**: `{result: {...}, execution_time_ms: 1250, confidence: 0.87}`
- **Status**: 200, 202 (still processing), 404, 500

### GET /job/{id}/trace
- **Response**: Full execution trace JSON
- **Status**: 200, 404

## Model Integration

Each tool is a self-contained module implementing a common interface:

```python
class ToolBase:
    async def load_model(self) -> None:
        """Load model weights and initialize."""
    
    async def infer(
        self, 
        image: np.ndarray,
        params: ToolParams
    ) -> ToolOutput:
        """Run inference on preprocessed image."""
    
    def get_metadata(self) -> ToolMetadata:
        """Return model capability metadata."""
```

Supported tools:
- **RSVQA_HR**: Remote Sensing Visual Question Answering (high-res)
- **ChangeFormer**: Change detection in multi-temporal SAR
- **GeoChat**: Conversational remote sensing understanding
- **ChangeVLP**: Vision-language for change detection
- **CDVQA**: Change detection VQA
- **SAM**: Segment Anything for segmentation
- **RemoteCLIP**: Remote sensing CLIP embeddings
- **Optical-SAR Fusion**: Joint optical/SAR model

## Deployment Architecture

### Development (local)
- FastAPI dev server (reload on file changes)
- Vite dev server (HMR)
- SQLite database

### Production (Docker)
- Multi-stage build: Node → Python base
- Uvicorn ASGI server (4 workers)
- Static frontend serving from FastAPI
- SQLite or PostgreSQL (configurable)
- Volume mounts for data persistence

### Scaling (Multiple Replicas)
- PostgreSQL for shared state
- S3/MinIO for object storage (results, caches)
- Redis for job queue + caching
- Load balancer (nginx) with sticky sessions
- Async task queue (Celery) for long jobs

## Performance Considerations

- **Preprocessing**: Cached to `data/cache/` to avoid re-processing
- **Model Loading**: Lazy-loaded on first use, cached in memory
- **Batch Processing**: Queue requests, process in batches when possible
- **Tiling**: Large images automatically split into tiles
- **Streaming**: Results streamed to client via WebSocket (future)

## Security

- **API Key**: Optional X-API-Key header for protected deployments
- **CORS**: Configurable allowed origins
- **Input Validation**: Pydantic schemas validate all inputs
- **File Uploads**: Size limits, format validation, virus scanning (optional)
- **Environment Secrets**: Use .env, never commit secrets

## Testing Strategy

- **Unit Tests**: Individual functions (>80% coverage)
- **Integration Tests**: Full pipeline with mock models
- **E2E Tests**: API endpoints with sample data
- **Performance Tests**: Load testing, inference benchmarks

## Future Enhancements

- WebSocket streaming of progress updates
- Multi-GPU inference with distributed inference
- Real-time collaborative queries
- Custom model upload and fine-tuning
- Advanced caching strategies (Redis)
- Observability: Prometheus metrics + Grafana dashboards
