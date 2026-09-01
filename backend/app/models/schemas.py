from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# ─── Enumerations ────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    SINGLE_VQA = "SINGLE_VQA"
    SINGLE_CAPTION = "SINGLE_CAPTION"
    SINGLE_GROUNDING = "SINGLE_GROUNDING"
    BITEMPORAL_CHANGE_DETECT = "BITEMPORAL_CHANGE_DETECT"
    BITEMPORAL_CHANGE_VQA = "BITEMPORAL_CHANGE_VQA"
    CROSS_MODAL_ANALYSIS = "CROSS_MODAL_ANALYSIS"
    UNKNOWN = "UNKNOWN"


class InputRole(str, Enum):
    PRIMARY = "PRIMARY"
    T1 = "T1"
    T2 = "T2"
    OPTICAL = "OPTICAL"
    SAR = "SAR"


class InputFormat(str, Enum):
    GEOTIFF = "GEOTIFF"
    PNG = "PNG"
    JPEG = "JPEG"
    UNKNOWN = "UNKNOWN"


class InputModality(str, Enum):
    OPTICAL = "OPTICAL"
    MULTISPECTRAL = "MULTISPECTRAL"
    SAR = "SAR"
    UNKNOWN = "UNKNOWN"


class ValidationStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    FUSING = "FUSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ToolCallStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class OutputType(str, Enum):
    TEXT = "TEXT"
    MASK = "MASK"
    BBOX = "BBOX"
    EMBEDDING = "EMBEDDING"
    CLASSIFICATION = "CLASSIFICATION"
    SEGMENTATION = "SEGMENTATION"


# ─── Input Metadata ───────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    minx: float
    miny: float
    maxx: float
    maxy: float
    crs: str = "EPSG:4326"


class InputMetadata(BaseModel):
    input_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: InputRole
    file_path: str
    file_hash: str
    original_filename: str
    format: InputFormat
    modality: InputModality
    crs: str | None = None
    resolution_m: float | None = None
    bands: int = 0
    width: int = 0
    height: int = 0
    dtype: str | None = None
    nodata: float | None = None
    has_georef: bool = False
    bbox_native: BoundingBox | None = None
    bbox_wgs84: BoundingBox | None = None
    validation_status: ValidationStatus = ValidationStatus.PASSED
    validation_notes: list[str] = Field(default_factory=list)


# ─── Preprocessing Step ───────────────────────────────────────────────────────

class PreprocessingStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_ids: list[str]
    output_artifact: str
    latency_ms: int = 0


# ─── Tool Call ────────────────────────────────────────────────────────────────

class ToolOutput(BaseModel):
    type: OutputType
    value: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_key: str
    model_name: str
    model_version: str
    input_artifacts: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    permitted_parameters: list[str] = Field(default_factory=list)
    status: ToolCallStatus = ToolCallStatus.PENDING
    output: ToolOutput | None = None
    error: str | None = None


# ─── Fusion ───────────────────────────────────────────────────────────────────

class FusionResult(BaseModel):
    text_outputs: list[str] = Field(default_factory=list)
    spatial_output_paths: list[str] = Field(default_factory=list)
    aggregated_confidence: float = 0.0
    confidence_rationale: str = ""


# ─── Execution Plan ───────────────────────────────────────────────────────────

class QueryInfo(BaseModel):
    raw_text: str
    classified_task: TaskType = TaskType.UNKNOWN
    task_confidence: float = 0.0
    task_rationale: str = ""


class AgentConstraints(BaseModel):
    llm_may_invoke_tools: list[str] = Field(default_factory=list)
    llm_may_not_execute_code: bool = True
    llm_may_not_invent_tools: bool = True


class ExecutionPlan(BaseModel):
    schema_version: str = "satquery-execution-plan-v1"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    query: QueryInfo
    inputs: list[InputMetadata] = Field(default_factory=list)
    preprocessing_steps: list[PreprocessingStep] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    fusion: FusionResult | None = None
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    final_answer: str = ""
    evidence_object_id: str | None = None


# ─── Evidence Object ──────────────────────────────────────────────────────────

class DetectedRegion(BaseModel):
    label: str
    bbox_pixels: list[float] | None = None       # [x1, y1, x2, y2]
    bbox_geo: BoundingBox | None = None
    mask_path: str | None = None                  # path to georeferenced mask PNG
    area_km2: float | None = None
    score: float = 0.0


class EvidenceObject(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    answer: str
    confidence: float
    confidence_rationale: str
    task: TaskType
    detected_regions: list[DetectedRegion] = Field(default_factory=list)
    change_map_path: str | None = None            # georeferenced change mask
    overlay_path: str | None = None               # PNG overlay for map viewer
    geojson_path: str | None = None               # GeoJSON spatial evidence
    report_url: str | None = None                 # Human-readable analysis report
    input_quality: dict[str, Any] = Field(default_factory=dict)
    supporting_text: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    execution_plan: ExecutionPlan | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ─── API Contracts ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    job_id: str
    query: str
    image_roles: dict[str, str] = Field(
        default_factory=dict,
        description="Map of upload_id → role (PRIMARY/T1/T2/OPTICAL/SAR)"
    )


class MapAnalysisRequest(BaseModel):
    """Analyze a map point using a recent public Sentinel-2 crop."""

    job_id: str
    query: str = Field(
        default="What land cover type dominates this location?",
        min_length=1,
        max_length=1000,
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress_message: str = ""
    created_at: str
    updated_at: str


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    evidence: EvidenceObject | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    file_hash: str
    size_bytes: int
    detected_format: InputFormat
    detected_modality: InputModality
    quick_metadata: dict[str, Any] = Field(default_factory=dict)
