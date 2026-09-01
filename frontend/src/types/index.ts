// ─── Enumerations ─────────────────────────────────────────────────────────────

export type TaskType =
  | "SINGLE_VQA"
  | "SINGLE_CAPTION"
  | "SINGLE_GROUNDING"
  | "BITEMPORAL_CHANGE_DETECT"
  | "BITEMPORAL_CHANGE_VQA"
  | "CROSS_MODAL_ANALYSIS"
  | "UNKNOWN";

export type InputRole = "PRIMARY" | "T1" | "T2" | "OPTICAL" | "SAR";
export type InputFormat = "GEOTIFF" | "PNG" | "JPEG" | "UNKNOWN";
export type InputModality = "OPTICAL" | "MULTISPECTRAL" | "SAR" | "UNKNOWN";
export type JobStatus =
  | "PENDING"
  | "VALIDATING"
  | "PLANNING"
  | "RUNNING"
  | "FUSING"
  | "COMPLETED"
  | "FAILED";

// ─── Upload ───────────────────────────────────────────────────────────────────

export interface UploadResponse {
  upload_id: string;
  filename: string;
  file_hash: string;
  size_bytes: number;
  detected_format: InputFormat;
  detected_modality: InputModality;
  quick_metadata: Record<string, unknown>;
}

// ─── Query ────────────────────────────────────────────────────────────────────

export interface QueryRequest {
  job_id: string;
  query: string;
  image_roles: Record<string, InputRole>; // upload_id → role
}

// ─── Job ──────────────────────────────────────────────────────────────────────

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress_message: string;
  created_at: string;
  updated_at: string;
}

// ─── Evidence ─────────────────────────────────────────────────────────────────

export interface BoundingBox {
  minx: number;
  miny: number;
  maxx: number;
  maxy: number;
  crs: string;
}

export interface DetectedRegion {
  label: string;
  bbox_pixels: [number, number, number, number] | null;
  bbox_geo: BoundingBox | null;
  mask_path: string | null;
  area_km2: number | null;
  score: number;
}

export interface EvidenceObject {
  evidence_id: string;
  job_id: string;
  answer: string;
  confidence: number;
  confidence_rationale: string;
  task: TaskType;
  detected_regions: DetectedRegion[];
  change_map_path: string | null;
  overlay_path: string | null;
  supporting_text: string[];
  models_used: string[];
  execution_plan: ExecutionPlan | null;
  created_at: string;
}

export interface JobResultResponse {
  job_id: string;
  status: JobStatus;
  evidence: EvidenceObject | null;
  error: string | null;
}

// ─── Execution Plan (for trace viewer) ───────────────────────────────────────

export interface ToolOutput {
  type: string;
  value: Record<string, unknown>;
  confidence: number;
  metadata: Record<string, unknown>;
  latency_ms: number;
}

export interface ToolCall {
  call_id: string;
  tool_key: string;
  model_name: string;
  model_version: string;
  parameters: Record<string, unknown>;
  status: string;
  output: ToolOutput | null;
  error: string | null;
}

export interface ExecutionPlan {
  schema_version: string;
  job_id: string;
  timestamp: string;
  query: {
    raw_text: string;
    classified_task: TaskType;
    task_confidence: number;
    task_rationale: string;
  };
  tool_calls: ToolCall[];
  fusion: {
    aggregated_confidence: number;
    confidence_rationale: string;
  } | null;
  final_answer: string;
}

// ─── UI State ─────────────────────────────────────────────────────────────────

export interface UploadedImage {
  uploadId: string;
  filename: string;
  modality: InputModality;
  format: InputFormat;
  role: InputRole;
  previewUrl: string | null;
  metadata: Record<string, unknown>;
}
