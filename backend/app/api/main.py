"""
SatQuery AI — FastAPI Backend
Endpoints: /upload, /query, /map/analyze, /job/{id}/status, /job/{id}/result, /job/{id}/trace
"""
from __future__ import annotations
import hashlib
import logging
import uuid
from pathlib import Path

import aiofiles
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.staticfiles import StaticFiles

from app.agent.controller import get_controller
from app.config import settings
from app.models.schemas import (
    InputFormat, InputModality, JobResultResponse, JobStatus,
    JobStatusResponse, MapAnalysisRequest, QueryRequest, UploadResponse,
)
from app.preprocessing.geo_pipeline import detect_format, detect_modality, ingest
from app.services.imagery import ImageryUnavailable, fetch_sentinel_tile
from app.storage import trace_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await trace_store.init_db()
    controller = get_controller()
    await controller.initialize()
    logger.info("SatQuery AI backend started")
    yield


app = FastAPI(
    title="SatQuery AI",
    description="Agentic Vision-Language Assistant for Remote Sensing Imagery",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://([a-z0-9-]+\.)*vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require X-API-Key when API_KEY is configured for a public deployment."""
    if settings.api_key and request.url.path not in {"/", "/health", "/docs", "/openapi.json", "/redoc"}:
        if request.headers.get("X-API-Key") != settings.api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key."})
    return await call_next(request)


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.post("/upload", response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """
    Upload a satellite image (GeoTIFF/TIFF primary; PNG/JPEG for benchmarks).
    Returns an upload_id used to reference the image in /query.
    """
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".tif", ".tiff", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(415, "Unsupported file format. Use GeoTIFF, PNG, or JPEG.")
    if file.size and file.size > settings.max_image_bytes:
        raise HTTPException(413, f"File too large. Max {settings.max_image_bytes // (1024*1024)} MB.")

    upload_id = str(uuid.uuid4())
    save_path = settings.upload_dir / f"{upload_id}{suffix}"

    # Stream to disk
    h = hashlib.sha256()
    size = 0
    async with aiofiles.open(save_path, "wb") as f:
        while chunk := await file.read(65536):
            size += len(chunk)
            if size > settings.max_image_bytes:
                await file.close()
                save_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large. Max {settings.max_image_bytes // (1024*1024)} MB.")
            await f.write(chunk)
            h.update(chunk)

    file_hash = h.hexdigest()
    fmt = detect_format(save_path)

    # Quick metadata extraction (non-blocking for large files)
    quick_meta = {}
    modality = InputModality.UNKNOWN
    try:
        import rasterio
        with rasterio.open(save_path) as ds:
            modality = detect_modality(ds)
            bbox_wgs84 = None
            if ds.crs:
                from rasterio.warp import transform_bounds

                bounds = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
                bbox_wgs84 = {
                    "minx": bounds[0],
                    "miny": bounds[1],
                    "maxx": bounds[2],
                    "maxy": bounds[3],
                    "crs": "EPSG:4326",
                }
            quick_meta = {
                "bands": ds.count,
                "width": ds.width,
                "height": ds.height,
                "crs": ds.crs.to_string() if ds.crs else None,
                "dtype": str(ds.dtypes[0]),
                "has_georef": ds.transform is not None,
                "bbox_wgs84": bbox_wgs84,
            }
    except Exception:
        pass  # PNG/JPEG — no rasterio metadata

    if fmt == InputFormat.UNKNOWN:
        save_path.unlink(missing_ok=True)
        raise HTTPException(415, "Unsupported file format. Use GeoTIFF, PNG, or JPEG.")
    logger.info(f"Uploaded: {filename} -> {upload_id} ({size} bytes, {fmt.value}, {modality.value})")

    return UploadResponse(
        upload_id=upload_id,
        filename=filename,
        file_hash=file_hash,
        size_bytes=size,
        detected_format=fmt,
        detected_modality=modality,
        quick_metadata=quick_meta,
    )


# ─── Query ────────────────────────────────────────────────────────────────────

@app.post("/query", response_model=JobStatusResponse)
async def submit_query(request: QueryRequest, background_tasks: BackgroundTasks):
    """
    Submit a natural-language query with references to uploaded images.
    Returns a job_id immediately; processing runs in the background.
    """
    # Resolve upload_ids to file paths
    file_paths: dict[str, Path] = {}
    for upload_id in request.image_roles.keys():
        # Find the file with this upload_id prefix
        matches = list(settings.upload_dir.glob(f"{upload_id}.*"))
        if not matches:
            raise HTTPException(404, f"Upload '{upload_id}' not found. Upload the image first.")
        file_paths[upload_id] = matches[0]

    if not file_paths:
        raise HTTPException(400, "No images referenced. Include upload_ids in image_roles.")

    job_id = request.job_id
    try:
        await trace_store.create_job(job_id, request.query)
    except IntegrityError:
        raise HTTPException(409, f"Job '{job_id}' already exists.") from None

    background_tasks.add_task(
        _run_job,
        job_id=job_id,
        query=request.query,
        file_paths=file_paths,
        image_roles=request.image_roles,
    )

    from datetime import datetime
    now = datetime.utcnow().isoformat()
    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        progress_message="Job queued",
        created_at=now,
        updated_at=now,
    )


@app.post("/map/analyze", response_model=JobStatusResponse)
async def analyze_map_location(request: MapAnalysisRequest, background_tasks: BackgroundTasks):
    """Analyze a clicked map point from a recent public Sentinel-2 scene."""
    query = request.query.strip()
    if not query:
        raise HTTPException(422, "Query must not be blank.")
    job_id = request.job_id
    try:
        await trace_store.create_job(job_id, query)
    except IntegrityError:
        raise HTTPException(409, f"Job '{job_id}' already exists.") from None

    background_tasks.add_task(
        _run_map_job,
        job_id=job_id,
        query=query,
        latitude=request.latitude,
        longitude=request.longitude,
    )
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        progress_message="Fetching public Sentinel-2 imagery",
        created_at=now,
        updated_at=now,
    )


async def _run_map_job(job_id: str, query: str, latitude: float, longitude: float):
    """Fetch a point crop, then hand it to the normal agent pipeline."""
    upload_id = f"map-{uuid.uuid4()}"
    image_path = settings.upload_dir / f"{upload_id}.tif"
    try:
        await trace_store.update_job_status(
            job_id, JobStatus.VALIDATING, "Finding recent public Sentinel-2 imagery..."
        )
        imagery_metadata = await fetch_sentinel_tile(
            latitude,
            longitude,
            image_path,
            stac_url=settings.imagery_stac_url,
            collection=settings.imagery_collection,
            days_back=settings.imagery_days_back,
            max_cloud_cover=settings.imagery_max_cloud_cover,
            tile_size=settings.imagery_tile_size,
        )
        await _run_job(
            job_id=job_id,
            query=query,
            file_paths={upload_id: image_path},
            image_roles={upload_id: "PRIMARY"},
            source_metadata=imagery_metadata,
        )
    except ImageryUnavailable as exc:
        image_path.unlink(missing_ok=True)
        await trace_store.update_job_status(
            job_id, JobStatus.FAILED, "Imagery unavailable", str(exc)
        )
    except Exception as exc:
        image_path.unlink(missing_ok=True)
        logger.exception("Map analysis %s failed: %s", job_id, exc)
        await trace_store.update_job_status(job_id, JobStatus.FAILED, "Map analysis failed", str(exc))


async def _run_job(
    job_id: str,
    query: str,
    file_paths: dict,
    image_roles: dict,
    source_metadata: dict | None = None,
):
    controller = get_controller()
    try:
        await controller.process_query(
            job_id, query, file_paths, image_roles, source_metadata=source_metadata
        )
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}")


# ─── Job Status / Result / Trace ──────────────────────────────────────────────

@app.get("/job/{job_id}/status", response_model=JobStatusResponse)
async def get_status(job_id: str):
    data = await trace_store.get_job_status(job_id)
    if not data:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    return JobStatusResponse(**data)


@app.get("/job/{job_id}/result", response_model=JobResultResponse)
async def get_result(job_id: str):
    data = await trace_store.get_job_result(job_id)
    if not data:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    return JobResultResponse(**data)


@app.get("/job/{job_id}/trace")
async def get_trace(job_id: str):
    data = await trace_store.get_job_trace(job_id)
    if not data:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    return data


@app.get("/job/{job_id}/report", response_class=HTMLResponse)
async def get_report(job_id: str):
    """Render a self-contained, judge-friendly analysis report."""
    from html import escape
    record = await trace_store.get_job_result(job_id)
    trace = await trace_store.get_job_trace(job_id)
    if not record or not record.get("evidence"):
        raise HTTPException(404, f"Job '{job_id}' has no completed evidence.")
    ev = record["evidence"]
    plan = ev.execution_plan
    rows = []
    if plan:
        for tc in plan.tool_calls:
            status = tc.output.metadata.get("status", "UNKNOWN") if tc.output else tc.status.value
            rows.append(f"<tr><td>{escape(tc.tool_key)}</td><td>{escape(tc.model_name)}</td><td>{escape(status)}</td><td>{tc.output.confidence:.2f}</td></tr>" if tc.output else f"<tr><td>{escape(tc.tool_key)}</td><td>{escape(tc.model_name)}</td><td>{escape(str(tc.status.value))}</td><td>—</td></tr>")
    quality = ev.input_quality or {}
    warnings = "".join(f"<li>{escape(str(w))}</li>" for w in quality.get("warnings", [])) or "<li>None</li>"
    regions = "".join(f"<li><b>{escape(r.label)}</b>" + (f" — {r.area_km2:.3f} km²" if r.area_km2 is not None else "") + (f" — {r.score*100:.0f}%" if r.score else "") + "</li>" for r in ev.detected_regions) or "<li>None</li>"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>SatQuery Report {escape(job_id)}</title><style>body{{font-family:system-ui;margin:0;background:#f8fafc;color:#0f172a}}main{{max-width:1000px;margin:32px auto;padding:0 18px}}section{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:18px;margin:14px 0}}h1{{margin-bottom:4px}}.score{{font-size:28px;font-weight:800}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:13px}}code{{background:#f1f5f9;padding:2px 5px;border-radius:4px}}</style></head><body><main><h1>🛰️ SatQuery AI Analysis Report</h1><p>Auditable remote-sensing analysis · SIH26167</p><section><h2>Query</h2><p>{escape(ev.execution_plan.query.raw_text if ev.execution_plan else '')}</p><div class='score'>{ev.confidence*100:.0f}% confidence</div><p>{escape(ev.confidence_rationale)}</p></section><section><h2>Answer</h2><p>{escape(ev.answer)}</p></section><section><h2>Input Quality</h2><p>Status: <b>{escape(str(quality.get('status','UNKNOWN')))}</b> · Georeferenced: {quality.get('georeferenced',0)}/{quality.get('inputs',0)}</p><ul>{warnings}</ul></section><section><h2>Detected Regions</h2><ul>{regions}</ul></section><section><h2>Execution Trace</h2><table><tr><th>Tool</th><th>Model</th><th>Status</th><th>Confidence</th></tr>{''.join(rows)}</table></section><section><h2>Spatial Evidence</h2><p>Change map: <code>{escape(ev.change_map_path or 'none')}</code></p><p>GeoJSON: <code>{escape(ev.geojson_path or 'none')}</code></p><p>Overlay: <code>{escape(ev.overlay_path or 'none')}</code></p></section></main></body></html>""")


# ─── Overlay / Map Assets ─────────────────────────────────────────────────────

@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Serve generated overlay images (change maps, segmentation masks)."""
    path = (settings.results_dir / Path(filename).name).resolve()
    results_root = settings.results_dir.resolve()
    if path.parent != results_root or not path.is_file():
        raise HTTPException(404, "Result file not found.")
    return FileResponse(str(path))


# ─── Frontend ────────────────────────────────────────────────────────────────

_FRONTEND = settings.frontend_dist / "index.html"
_LEGACY_FRONTEND = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "index.html"

if settings.frontend_dist.is_dir():
    _frontend_assets = settings.frontend_dist / "assets"
    if _frontend_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_frontend_assets), name="assets")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the SatQuery AI frontend."""
    frontend = _FRONTEND if _FRONTEND.exists() else _LEGACY_FRONTEND
    if not frontend.exists():
        return HTMLResponse("<h2>Frontend build not found.</h2>", 404)
    return FileResponse(frontend)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    controller = get_controller()
    return {"status": "ok", "service": "SatQuery AI", "initialized": controller._initialized}


@app.get("/models/status")
async def model_status():
    """Expose which specialist checkpoints are configured without loading them."""
    return {"models": get_controller().registry.status()}
