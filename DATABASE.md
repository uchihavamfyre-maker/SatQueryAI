# Database Guide

## Overview

SatQuery AI uses **SQLite** by default for simplicity in development and single-instance deployments. For **production, multi-instance deployments, high concurrency, or data durability requirements**, PostgreSQL is recommended.

## Development Setup

### SQLite (Default)

SQLite requires no setup:
```python
DATABASE_URL=sqlite:///./data/satquery.db
```

**Advantages:**
- Zero configuration
- No server required
- Good for development/testing
- File-based portability

**Disadvantages:**
- Limited concurrent writes
- No built-in replication
- Ephemeral storage in containerized environments

## Production Setup

### PostgreSQL (Recommended)

**Installation:**
```bash
# Docker
docker run -d \
  --name satquery-postgres \
  -e POSTGRES_PASSWORD=securepassword \
  -e POSTGRES_DB=satquery \
  -v postgres_data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16-alpine
```

**Configuration:**
```python
DATABASE_URL=postgresql://user:password@localhost:5432/satquery
```

**Connection Pooling (recommended):**
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Verify connections before use
    echo_pool=True,  # Log pool events
)
```

**Environment file (.env):**
```bash
DATABASE_URL=postgresql://satquery_user:strong_password@db.example.com:5432/satquery_prod
SQLALCHEMY_ECHO=false
SQLALCHEMY_POOL_SIZE=20
SQLALCHEMY_MAX_OVERFLOW=40
```

## Schema & Migrations

### Schema Overview

```sql
-- Jobs table: tracks processing state
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'queued',  -- queued, processing, completed, failed
    result_json TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (upload_id) REFERENCES uploads(id)
);

-- Uploads table: tracks user uploads
CREATE TABLE uploads (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    format TEXT,
    modality TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Results table: stores processing results
CREATE TABLE results (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    answer TEXT,
    confidence FLOAT,
    evidence_json TEXT,
    visualizations_json TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- Create indexes for common queries
CREATE INDEX idx_jobs_upload_id ON jobs(upload_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE INDEX idx_uploads_created_at ON uploads(created_at);
```

### Database Migrations

Using **Alembic** (SQLAlchemy migrations):

```bash
# Initialize Alembic (one-time)
alembic init migrations

# Create a migration
alembic revision --autogenerate -m "Add results table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

**Migration example (migrations/versions/001_initial.py):**
```python
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('upload_id', sa.String(), nullable=False),
        sa.Column('query', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('jobs')
```

## Backup & Recovery

### SQLite Backups

```bash
# Single file backup
cp data/satquery.db backups/satquery-$(date +%Y%m%d-%H%M%S).db

# Automated daily backup
0 2 * * * cp /app/data/satquery.db /backups/satquery-$(date +\%Y\%m\%d).db
```

### PostgreSQL Backups

```bash
# Full backup
pg_dump -U satquery_user -h db.example.com satquery_prod > backup.sql

# Restore
psql -U satquery_user -h db.example.com satquery_prod < backup.sql

# Automated with pg_basebackup (streaming replication)
pg_basebackup -h db.example.com -D /backups/backup -U replication -v -P
```

### AWS RDS Automated Backups
- Automatic daily snapshots (configurable retention)
- Point-in-time recovery (35 days default)
- Multi-AZ for high availability

## Monitoring & Maintenance

### SQLite Maintenance

```python
# Vacuum and optimize (periodic maintenance)
import sqlite3
conn = sqlite3.connect('data/satquery.db')
conn.execute('VACUUM')
conn.execute('ANALYZE')
conn.close()
```

### PostgreSQL Monitoring

```sql
-- Check database size
SELECT pg_database.datname,
       pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
ORDER BY pg_database_size(pg_database.datname) DESC;

-- Monitor active connections
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Autovacuum status
SELECT datname, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables;
```

### Query Performance

```sql
-- Enable slow query logging
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s

-- Check table bloat
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
```

## Scaling Strategies

### Vertical Scaling
- Increase database server CPU/RAM
- Optimize indexes
- Tune connection pools

### Horizontal Scaling

**Read Replicas:**
```bash
# PostgreSQL streaming replication
Primary DB → Replica 1, Replica 2, Replica 3
# Read queries to replicas, writes to primary
```

**Sharding (for very large deployments):**
```
Shard 1: Jobs {A-M}
Shard 2: Jobs {N-Z}
Application routes based on job ID hash
```

**Caching Layer (Redis):**
```python
# Cache job results to reduce DB queries
import redis
cache = redis.Redis(host='redis.example.com', port=6379)

# Cache result for 1 hour
cache.setex(f'job:{job_id}:result', 3600, json.dumps(result))
```

## Data Retention Policies

### Archive Old Data

```python
from datetime import datetime, timedelta

# Archive jobs older than 90 days
cutoff = datetime.now() - timedelta(days=90)

old_jobs = session.query(Job).filter(Job.created_at < cutoff).all()
for job in old_jobs:
    archive_to_storage(job)  # Move to S3/cold storage
    session.delete(job)

session.commit()
```

### Automated Cleanup

```bash
# Delete expired uploads (in cron or background task)
0 3 * * * python -c "
import os
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=30)
# Delete files from data/uploads older than 30 days
"
```

## Disaster Recovery

### RTO & RPO Goals
- **RTO (Recovery Time Objective):** < 1 hour
- **RPO (Recovery Point Objective):** < 15 minutes

### Disaster Recovery Plan

1. **Backup Strategy:** Daily full backups + hourly incremental
2. **Testing:** Monthly recovery drills
3. **Documentation:** Keep runbook updated
4. **Redundancy:** Multi-region backups for critical data
5. **Monitoring:** Alerts for backup failures

## Troubleshooting

### Connection Issues

```bash
# Check database connectivity
python -c "
from sqlalchemy import create_engine
engine = create_engine('postgresql://user:pass@host/db')
conn = engine.connect()
print('Connected!')
"
```

### Slow Queries

```sql
-- Find slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

### Deadlocks

```sql
-- Monitor deadlocks
SELECT * FROM pg_stat_database
WHERE deadlocks > 0;

-- Identify blocking queries
SELECT * FROM pg_locks
WHERE NOT granted;
```

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Migrations](https://alembic.sqlalchemy.org/)
- [PostgreSQL Administration](https://www.postgresql.org/docs/current/admin.html)
- [AWS RDS Best Practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html)
