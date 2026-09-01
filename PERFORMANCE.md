# Performance & Optimization Guide

## Benchmarking

### Setup Benchmarking Tools

```bash
# Install benchmarking tools
pip install locust pytest-benchmark memory-profiler
npm install -g autocannon  # For frontend
```

### Backend Benchmarking

**Pytest-benchmark for unit tests:**
```python
# tests/test_performance.py
import pytest

def test_image_preprocessing_speed(benchmark, sample_geotiff):
    """Benchmark image preprocessing."""
    from app.preprocessing.geo_pipeline import ingest
    
    result = benchmark(ingest, sample_geotiff)
    assert result is not None

def test_model_inference_speed(benchmark, mock_model, sample_image):
    """Benchmark model inference."""
    result = benchmark(mock_model.infer, sample_image)
    assert result.confidence > 0
```

**Load testing with Locust:**
```python
# load_tests/locustfile.py
from locust import HttpUser, task, between

class SatQueryUser(HttpUser):
    wait_time = between(1, 5)
    
    @task
    def upload_and_query(self):
        # Upload
        with open('sample.tif', 'rb') as f:
            response = self.client.post(
                '/upload',
                files={'file': f}
            )
        
        if response.status_code == 200:
            upload_id = response.json()['upload_id']
            
            # Query
            self.client.post('/query', json={
                'upload_id': upload_id,
                'query': 'What do you see?'
            })
```

**Run load tests:**
```bash
locust -f load_tests/locustfile.py --host=http://localhost:8000 -u 100 -r 10
```

### Memory Profiling

```python
# Profile memory usage
from memory_profiler import profile

@profile
def process_large_image(image_path):
    """Track memory usage during processing."""
    image = load_image(image_path)
    processed = preprocess(image)
    result = infer(processed)
    return result
```

**Run profiler:**
```bash
python -m memory_profiler script.py
```

### CPU Profiling

```python
import cProfile
import pstats

# Profile CPU usage
profiler = cProfile.Profile()
profiler.enable()

# ... code to profile ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

## Performance Optimization

### Image Preprocessing

**Optimize tile sizes:**
```python
# Smaller tiles = faster, more memory efficient
TILE_SIZE_SMALL = 256   # For lightweight models
TILE_SIZE_LARGE = 512   # For heavy models
TILE_SIZE_XLARGE = 1024 # For powerful GPUs

# Benchmark different sizes
for size in [256, 512, 1024]:
    tiles = generate_tiles(image, size)
    t = time.time()
    results = model.infer(tiles)
    print(f"Tile size {size}: {time.time()-t:.2f}s")
```

**Caching strategy:**
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=128)
def get_cached_preprocessing(image_hash):
    """Cache preprocessed images."""
    return preprocess_image(image_hash)

def get_image_hash(image_path):
    """Generate cache key."""
    with open(image_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()
```

### Model Optimization

**Use model quantization:**
```python
import torch

# Quantize model for faster inference
model = torch.quantization.quantize_dynamic(
    original_model,
    {torch.nn.Linear},
    dtype=torch.qint8
)

# Benchmark improvement
# Before: 500ms per inference
# After: 150ms per inference (3.3x faster)
```

**Batch inference:**
```python
async def batch_infer(images: List[np.ndarray], batch_size=32):
    """Process multiple images efficiently."""
    results = []
    for i in range(0, len(images), batch_size):
        batch = images[i:i+batch_size]
        batch_results = model.infer_batch(batch)
        results.extend(batch_results)
    return results
```

**Model serving optimization:**
```python
# Use TorchServe or NVIDIA Triton for optimized serving
# - Model caching
# - Automatic batching
# - GPU memory management
# - Request queuing
```

### Database Optimization

**Add indexes:**
```sql
-- Frequently queried columns
CREATE INDEX idx_jobs_upload_id ON jobs(upload_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE INDEX idx_results_job_id ON results(job_id);

-- Composite indexes for common filters
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
```

**Query optimization:**
```python
# ❌ Slow: N+1 queries
jobs = session.query(Job).all()
for job in jobs:
    print(job.results)  # Separate query for each job!

# ✅ Fast: Single query with join
jobs = session.query(Job).options(
    joinedload(Job.results)
).all()

# Even better: Select only needed columns
jobs = session.query(Job.id, Job.status, Job.created_at).all()
```

**Connection pooling:**
```python
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # Persistent connections
    max_overflow=40,        # Additional connections under load
    pool_pre_ping=True,     # Verify connections before use
    pool_recycle=3600,      # Recycle connections every hour
)
```

### API Optimization

**Pagination:**
```python
@app.get("/jobs")
async def list_jobs(skip: int = 0, limit: int = 10):
    """Paginate results to reduce memory/network."""
    jobs = session.query(Job).offset(skip).limit(limit).all()
    return jobs
```

**Response compression:**
```python
from fastapi.middleware.gzip import GZIPMiddleware

app.add_middleware(GZIPMiddleware, minimum_size=1000)
```

**Caching headers:**
```python
from fastapi.responses import FileResponse

@app.get("/results/{result_id}")
async def get_result(result_id: str):
    """Cache result files for 1 hour."""
    file_path = f"data/results/{result_id}.png"
    return FileResponse(
        file_path,
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": hashlib.md5(open(file_path, 'rb').read()).hexdigest(),
        }
    )
```

### Frontend Optimization

**Code splitting:**
```typescript
// React lazy loading
const ImageUpload = lazy(() => import('./ImageUpload'));
const ResultsPanel = lazy(() => import('./ResultsPanel'));

<Suspense fallback={<Loading />}>
  <ImageUpload />
  <ResultsPanel />
</Suspense>
```

**Bundle analysis:**
```bash
# Analyze bundle size
npm run build -- --analyze
# Identify and remove unused dependencies
```

**Image optimization:**
```typescript
// Use next-gen formats
<picture>
  <source srcSet="image.webp" type="image/webp" />
  <img src="image.png" alt="satellite" />
</picture>
```

## Performance Baselines

Document performance expectations:

```yaml
# PERFORMANCE_TARGETS.yaml
endpoints:
  upload:
    latency_p95: 2000ms  # 2 seconds for 50MB image
    throughput: 100/min  # 100 uploads/minute
  
  query:
    latency_p50: 1500ms  # Median: 1.5 seconds
    latency_p95: 5000ms  # 95th percentile: 5 seconds
    latency_p99: 10000ms # 99th percentile: 10 seconds
    throughput: 10/min   # 10 queries/minute per user

models:
  rsvqa_hr:
    inference_time: 200-500ms
    memory: 2GB
    
  changeformer:
    inference_time: 300-800ms
    memory: 3GB

system:
  cpu_target: <70%
  memory_target: <80%
  disk_target: <85%
  database_connection_pool: 20
```

## Monitoring Performance

**Track metrics in production:**
```python
# Record benchmark results over time
metrics = {
    "timestamp": datetime.now(),
    "endpoint": "/query",
    "latency_ms": response_time,
    "model": "rsvqa_hr",
    "inference_ms": model_time,
    "database_ms": db_time,
}

# Store in monitoring system
save_metric_to_prometheus(metrics)
```

**Create performance dashboards:**
- Query latency trends
- Throughput trends
- Model inference times
- Cache hit rates
- Database query times

## Scaling Strategies

### Vertical Scaling (More Powerful Hardware)
- Larger GPUs for model inference
- More CPU cores for preprocessing
- More memory for batch processing
- Faster storage (NVMe SSDs)

### Horizontal Scaling
- Multiple API servers behind load balancer
- Distributed job queue (Redis + Celery)
- Read replicas for database queries
- Shared storage (S3, MinIO)

### Caching Layers
```python
# Redis caching
import redis

cache = redis.Redis(host='redis.example.com', port=6379)

@app.get("/results/{job_id}")
async def get_result(job_id: str):
    # Check cache first
    cached = cache.get(f"result:{job_id}")
    if cached:
        return json.loads(cached)
    
    # Get from database
    result = session.query(Result).filter(Result.job_id == job_id).first()
    
    # Cache for 1 hour
    cache.setex(f"result:{job_id}", 3600, json.dumps(result.dict()))
    
    return result
```

## References

- [Python Performance Optimization](https://docs.python.org/3/library/profile.html)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/deployment/concepts/)
- [SQLAlchemy Performance](https://docs.sqlalchemy.org/en/20/faq/performance.html)
- [PostgreSQL Performance](https://www.postgresql.org/docs/current/performance.html)
- [Web Performance Tips](https://web.dev/performance/)
