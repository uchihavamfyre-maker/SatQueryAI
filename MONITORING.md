# Monitoring, Logging & Observability

## Overview

This guide covers logging, monitoring, metrics, and alerting for SatQuery AI.

## Structured Logging

### Python JSON Logging

**Setup structured logging:**
```python
import logging
import json
from pythonjsonlogger import jsonlogger

# Configure JSON logger
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)
```

**Usage:**
```python
# Log with structured context
logger.info("Query processed", extra={
    "job_id": job_id,
    "query": query,
    "status": "completed",
    "execution_time_ms": 1234,
    "confidence": 0.87,
    "user_id": user_id,
})

# Log errors with full context
logger.error("Query processing failed", extra={
    "job_id": job_id,
    "error": str(exception),
    "error_type": type(exception).__name__,
    "traceback": traceback.format_exc(),
}, exc_info=True)
```

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Development, detailed diagnostics |
| INFO | Normal operations, state changes |
| WARNING | Recoverable issues, degraded operation |
| ERROR | Failures that need attention |
| CRITICAL | System failures, immediate action needed |

### Log Retention

**Local Logging:**
```python
# Rotate logs to avoid disk space issues
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'app.log',
    maxBytes=104857600,  # 100 MB
    backupCount=10,      # Keep 10 files
)
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)
```

**Centralized Logging:**
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- DataDog
- AWS CloudWatch

```python
# Send logs to CloudWatch
import watchtower

handler = watchtower.CloudWatchLogHandler(
    log_group='/aws/satquery/backend',
    stream_name='production',
)
logger.addHandler(handler)
```

## Metrics & Monitoring

### Application Metrics

**Track key performance indicators:**
```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Counters
query_counter = Counter('satquery_queries_total', 'Total queries processed')
error_counter = Counter('satquery_errors_total', 'Total errors', ['error_type'])
upload_counter = Counter('satquery_uploads_total', 'Total uploads')

# Histograms (for timing)
query_duration = Histogram(
    'satquery_query_duration_seconds',
    'Query processing duration',
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0)
)
model_inference_time = Histogram(
    'satquery_model_inference_ms',
    'Model inference time',
    ['model_name']
)

# Gauges (for current values)
active_jobs = Gauge('satquery_active_jobs', 'Currently processing jobs')
model_cache_size = Gauge('satquery_cache_size_bytes', 'Model cache size')
```

**Instrument endpoints:**
```python
@app.post("/query")
async def query(request: QueryRequest):
    query_counter.inc()
    active_jobs.inc()
    
    start = time.time()
    try:
        result = await process_query(request)
        query_duration.observe(time.time() - start)
        return result
    except Exception as e:
        error_counter.labels(error_type=type(e).__name__).inc()
        raise
    finally:
        active_jobs.dec()
```

**Expose metrics endpoint:**
```python
from prometheus_client import make_asgi_app

# Prometheus metrics at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

### Resource Metrics

**Monitor system resources:**
```python
import psutil
from prometheus_client import Gauge

cpu_percent = Gauge('system_cpu_percent', 'CPU usage percentage')
memory_percent = Gauge('system_memory_percent', 'Memory usage percentage')
disk_percent = Gauge('system_disk_percent', 'Disk usage percentage')

async def collect_system_metrics():
    """Collect system metrics periodically."""
    while True:
        cpu_percent.set(psutil.cpu_percent(interval=1))
        memory_percent.set(psutil.virtual_memory().percent)
        disk_percent.set(psutil.disk_usage('/').percent)
        await asyncio.sleep(60)
```

## Error Tracking

### Sentry Integration

**Setup Sentry for error tracking:**
```bash
pip install sentry-sdk
```

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn="https://your-sentry-dsn@sentry.io/project-id",
    integrations=[
        FastApiIntegration(),
        SqlalchemyIntegration(),
    ],
    traces_sample_rate=0.1,
    environment=settings.environment,
)
```

**Capture events:**
```python
try:
    # Processing code
    result = await process_image(image)
except Exception as e:
    sentry_sdk.capture_exception(e)
    # Or manually capture
    sentry_sdk.capture_message(f"Processing failed: {e}", level="error")
```

### Error Aggregation

Track error patterns:
```sql
SELECT 
    error_type,
    COUNT(*) as count,
    MAX(timestamp) as last_seen
FROM errors
WHERE timestamp > NOW() - INTERVAL 1 day
GROUP BY error_type
ORDER BY count DESC;
```

## Alerting

### Alert Rules

**Setup alerts for critical issues:**

```yaml
# Prometheus AlertManager config
groups:
  - name: satquery_alerts
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: rate(satquery_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"
      
      # Slow queries
      - alert: SlowQueryPercentile
        expr: histogram_quantile(0.95, satquery_query_duration_seconds) > 5
        for: 10m
        annotations:
          summary: "Queries are slow (p95 > 5s)"
      
      # High memory usage
      - alert: HighMemoryUsage
        expr: system_memory_percent > 80
        for: 5m
        annotations:
          summary: "Memory usage above 80%"
      
      # Low disk space
      - alert: LowDiskSpace
        expr: system_disk_percent > 85
        for: 5m
        annotations:
          summary: "Disk usage above 85%"
```

### Notification Channels

**Send alerts to:**
- Slack: Immediate team notification
- PagerDuty: On-call engineer escalation
- Email: Issue digests
- Webhooks: Custom integrations

```python
# Slack notification example
import aiohttp

async def notify_slack(message: str, severity: str = "warning"):
    """Send alert to Slack."""
    color_map = {
        "critical": "#FF0000",
        "warning": "#FFA500",
        "info": "#0000FF"
    }
    
    payload = {
        "attachments": [{
            "color": color_map.get(severity),
            "title": "SatQuery Alert",
            "text": message,
            "ts": int(time.time())
        }]
    }
    
    async with aiohttp.ClientSession() as session:
        await session.post(
            settings.slack_webhook_url,
            json=payload
        )
```

## Health Checks

### Liveness & Readiness

```python
@app.get("/health/live")
async def liveness():
    """Liveness probe - is service running?"""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    """Readiness probe - is service ready to accept traffic?"""
    try:
        # Check database connectivity
        await check_database()
        # Check required models loaded
        await check_models()
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(503, f"Service not ready: {e}")
```

**Kubernetes configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Performance Tracing

### Distributed Tracing

**Setup OpenTelemetry:**
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger
```

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Export traces to Jaeger
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)
tracer = trace.get_tracer(__name__)
```

**Trace operations:**
```python
with tracer.start_as_current_span("process_query") as span:
    span.set_attribute("query", query)
    
    with tracer.start_as_current_span("planning"):
        plan = await planner.plan(query)
    
    with tracer.start_as_current_span("execution"):
        results = await dispatcher.execute(plan)
    
    span.set_attribute("confidence", confidence)
```

## Dashboards

### Grafana Dashboards

**Key metrics to visualize:**
- Query throughput (QPS)
- Query latency (p50, p95, p99)
- Error rate
- Model cache hit rate
- Database connection pool usage
- System resources (CPU, memory, disk)
- Active jobs
- Upload processing rate

**Example dashboard query:**
```promql
# Queries per second (last 5 minutes)
rate(satquery_queries_total[5m])

# Query latency percentiles
histogram_quantile(0.95, rate(satquery_query_duration_seconds_bucket[5m]))

# Error percentage
rate(satquery_errors_total[5m]) / rate(satquery_queries_total[5m]) * 100
```

## Troubleshooting

### Common Issues

**High latency:**
1. Check database query performance
2. Monitor model inference time
3. Review rate limiting settings
4. Analyze memory usage (paging?)

**High error rate:**
1. Check error logs for patterns
2. Review recent code changes
3. Check external dependencies
4. Verify system resources

**High memory usage:**
1. Check model cache size
2. Review job queue length
3. Look for memory leaks
4. Monitor batch processing

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)
- [OpenTelemetry](https://opentelemetry.io/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [Sentry Error Tracking](https://sentry.io/)
