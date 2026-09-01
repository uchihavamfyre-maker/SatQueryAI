# API Reference

## Overview

SatQuery AI provides a RESTful API for processing satellite imagery queries. All requests should include the `X-API-Key` header if API key authentication is enabled.

### Base URL
```
http://localhost:8000  (Development)
https://api.satquery.ai  (Production - example)
```

### Authentication
Include the API key in the request header:
```
X-API-Key: your-api-key-here
```

### Response Format
All responses are JSON-encoded:
```json
{
  "status": "success|error",
  "data": {},
  "error": null,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## Endpoints

### 1. Upload Image

**Endpoint:** `POST /upload`

**Description:** Upload a satellite image for processing.

**Request:**
- **Method:** POST
- **Content-Type:** multipart/form-data
- **Parameters:**
  - `file` (required): Binary image file
    - Supported formats: `.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`
    - Max size: 100 MB (configurable)
    - Recommended: GeoTIFF with geospatial metadata

**Response (200 OK):**
```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "image.tif",
  "file_size": 2048576,
  "format": "GeoTIFF",
  "modality": "Multispectral",
  "metadata": {
    "width": 512,
    "height": 512,
    "crs": "EPSG:4326",
    "bounds": [67.5, 25.2, 68.5, 26.2],
    "bands": 11,
    "datatype": "uint16"
  }
}
```

**Error Responses:**
- **400 Bad Request:** Invalid request format
- **413 Payload Too Large:** File exceeds max size
- **415 Unsupported Media Type:** Invalid file format
- **422 Unprocessable Entity:** File cannot be processed

**Example:**
```bash
curl -X POST -F "file=@image.tif" \
  -H "X-API-Key: your-key" \
  http://localhost:8000/upload
```

---

### 2. Query Image

**Endpoint:** `POST /query`

**Description:** Submit a query about an uploaded image.

**Request:**
```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "What are the land cover types in this image?",
  "parameters": {
    "confidence_threshold": 0.7,
    "return_visualization": true
  }
}
```

**Parameters:**
- `upload_id` (required): UUID from /upload response
- `query` (required): Natural language question about the image
- `parameters` (optional):
  - `confidence_threshold` (number, 0-1): Minimum confidence for results (default: 0.5)
  - `return_visualization` (boolean): Include visual outputs (default: true)
  - `timeout_seconds` (number): Max processing time (default: 300)

**Response (200 OK):**
```json
{
  "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "estimated_wait_seconds": 15,
  "query_id": "query-abc123"
}
```

**Error Responses:**
- **400 Bad Request:** Invalid query format
- **404 Not Found:** upload_id doesn't exist
- **422 Unprocessable Entity:** Validation failed
- **429 Too Many Requests:** Rate limit exceeded

**Example:**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "upload_id": "550e8400-e29b-41d4-a716-446655440000",
    "query": "What land use types are visible?"
  }' \
  http://localhost:8000/query
```

---

### 3. Get Job Status

**Endpoint:** `GET /job/{job_id}/status`

**Description:** Poll the status of a processing job.

**Parameters:**
- `job_id` (path, required): Job ID from /query response

**Response (200 OK):**
```json
{
  "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 0.65,
  "progress_details": {
    "current_step": "Running change detection model",
    "total_steps": 5,
    "elapsed_seconds": 12
  },
  "estimated_completion_seconds": 8
}
```

**Status Values:**
- `queued`: Waiting to be processed
- `processing`: Currently running
- `completed`: Finished successfully
- `failed`: Error during processing
- `cancelled`: Job was cancelled

**Error Responses:**
- **404 Not Found:** Job doesn't exist
- **410 Gone:** Job has expired

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  http://localhost:8000/job/job-550e8400-e29b-41d4-a716-446655440000/status
```

---

### 4. Get Job Result

**Endpoint:** `GET /job/{job_id}/result`

**Description:** Retrieve the final result of a completed job.

**Parameters:**
- `job_id` (path, required): Job ID from /query response

**Response (200 OK):**
```json
{
  "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "query": "What changed between these dates?",
  "answer": "Significant agricultural expansion in the northwestern region...",
  "confidence_score": 0.87,
  "evidence": [
    {
      "tool": "ChangeFormer",
      "confidence": 0.91,
      "output": "Change detected in 15.2% of area"
    },
    {
      "tool": "CDVQA",
      "confidence": 0.83,
      "output": "Cropland increased by ~12,000 hectares"
    }
  ],
  "visualizations": {
    "change_map": "data/results/job-550e8400.png",
    "heatmap": "data/results/job-550e8400-heatmap.png"
  },
  "execution_time_ms": 2340,
  "created_at": "2024-01-01T10:00:00Z",
  "completed_at": "2024-01-01T10:00:02.340Z"
}
```

**Error Responses:**
- **202 Accepted:** Job still processing
- **404 Not Found:** Job doesn't exist
- **500 Internal Server Error:** Processing failed

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  http://localhost:8000/job/job-550e8400-e29b-41d4-a716-446655440000/result
```

---

### 5. Get Execution Trace

**Endpoint:** `GET /job/{job_id}/trace`

**Description:** Retrieve detailed execution trace for debugging.

**Parameters:**
- `job_id` (path, required): Job ID from /query response

**Response (200 OK):**
```json
{
  "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-01T10:00:00Z",
  "query": "What land cover types are visible?",
  "planning": {
    "intent": "land_cover_classification",
    "selected_tools": ["geochat", "rsvqa_hr"],
    "execution_order": ["geochat", "rsvqa_hr"],
    "reasoning": "Multiple tools selected for robust classification"
  },
  "execution": [
    {
      "step": 1,
      "tool": "geochat",
      "status": "completed",
      "input": {...},
      "output": {...},
      "confidence": 0.85,
      "execution_time_ms": 1200,
      "error": null
    }
  ],
  "fusion": {
    "method": "weighted_average",
    "weights": {"geochat": 0.6, "rsvqa_hr": 0.4},
    "fused_result": {...},
    "confidence": 0.83
  },
  "validation": {
    "passed": true,
    "quality_score": 0.88,
    "checks": [
      {"name": "coherence", "passed": true},
      {"name": "confidence_threshold", "passed": true}
    ]
  },
  "total_execution_time_ms": 2340
}
```

**Error Responses:**
- **404 Not Found:** Job or trace doesn't exist

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  http://localhost:8000/job/job-550e8400-e29b-41d4-a716-446655440000/trace
```

---

### 6. Health Check

**Endpoint:** `GET /health`

**Description:** Check if the API is available and healthy.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T10:00:00Z",
  "version": "1.0.0",
  "models_available": 7,
  "database": "connected",
  "cache": "connected"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | OK - Request successful |
| 202 | Accepted - Processing in progress |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Missing/invalid API key |
| 404 | Not Found - Resource doesn't exist |
| 413 | Payload Too Large - File exceeds size limit |
| 415 | Unsupported Media Type - Invalid file format |
| 422 | Unprocessable Entity - Validation failed |
| 429 | Too Many Requests - Rate limited |
| 500 | Internal Server Error - Server error |
| 503 | Service Unavailable - Server overloaded |

---

## Rate Limiting

API requests are rate-limited based on your plan:
- **Free**: 10 requests/minute per API key
- **Pro**: 100 requests/minute per API key
- **Enterprise**: Custom limits

Rate limit information is included in response headers:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1609502400
```

---

## Webhooks (Optional)

Receive notifications when jobs complete:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "webhook_url": "https://your-server.com/callback",
    "events": ["job.completed", "job.failed"]
  }' \
  http://localhost:8000/webhooks/subscribe
```

---

## SDKs & Examples

### Python
```python
import satquery

client = satquery.Client(api_key="your-key")

# Upload image
upload = client.upload("path/to/image.tif")

# Submit query
job = client.query(upload.id, "What changed here?")

# Wait for result
result = job.wait()
print(result.answer)
```

### cURL
See examples above for each endpoint.

### JavaScript/TypeScript
```typescript
import { SatQueryClient } from 'satquery-js';

const client = new SatQueryClient({
  apiKey: 'your-key',
});

const upload = await client.upload('image.tif');
const job = await client.query(upload.id, 'What changed here?');
const result = await job.wait();
console.log(result.answer);
```

---

## Support

- **Documentation**: https://docs.satquery.ai
- **Issues**: https://github.com/yourusername/satquery-ai/issues
- **Email**: support@satquery.ai
- **Discord**: https://discord.gg/satquery
