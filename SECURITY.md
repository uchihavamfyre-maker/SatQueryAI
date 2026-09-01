# Security Guide

## Overview

This guide covers security best practices for developing, deploying, and operating SatQuery AI.

## Table of Contents
1. [Development Security](#development-security)
2. [Deployment Security](#deployment-security)
3. [API Security](#api-security)
4. [Data Security](#data-security)
5. [Vulnerability Management](#vulnerability-management)
6. [Incident Response](#incident-response)

## Development Security

### Secret Management

**Never commit secrets to version control:**

```bash
# .gitignore
.env
.env.local
.env.*.local
secrets/
*.key
*.pem
```

**Use environment variables:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str  # Required, error if missing
    database_url: str = "sqlite:///./data/satquery.db"
    
    class Config:
        env_file = ".env"
```

**For local development, use .env.example as template:**
```bash
# .env.example
API_KEY=your-api-key-here
DATABASE_URL=sqlite:///./data/satquery.db
DEBUG=False
```

### Dependency Management

**Regular vulnerability scans:**
```bash
# Check for known vulnerabilities
pip-audit

# Update dependencies
pip list --outdated
pip-compile requirements.txt  # with pip-tools
```

**Lock dependency versions:**
```bash
# Generate lock file
pip freeze > requirements.lock
```

**Automated scanning with GitHub:**
Add Dependabot to catch vulnerabilities:
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Code Review

- All code changes require review before merge
- Security reviewers for sensitive areas
- Use CODEOWNERS file to enforce reviews:
```
# .github/CODEOWNERS
/backend/app/api/ @security-team
/backend/app/storage/ @database-team
```

## Deployment Security

### HTTPS & TLS

**Always use HTTPS in production:**
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/api.satquery.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.satquery.ai/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
}
```

**Use Let's Encrypt for free certificates:**
```bash
certbot certonly --standalone -d api.satquery.ai
```

### Container Security

**Scan Docker images:**
```bash
# Using Trivy
trivy image satquery-ai:latest

# Using Grype
grype ghcr.io/satquery-ai/satquery:latest
```

**Security best practices in Dockerfile:**
```dockerfile
# Use specific version tags
FROM python:3.12-slim

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Don't use --no-cache-dir globally (slows builds)
# Use explicit requirements versions
RUN pip install --no-cache-dir -r requirements.txt

# Scan the final image
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
```

### Network Security

**Firewall configuration:**
```bash
# Allow only required ports
ufw allow 22/tcp    # SSH
ufw allow 443/tcp   # HTTPS
ufw allow 80/tcp    # HTTP (for redirect only)
ufw default deny incoming
ufw enable
```

**VPC & Network Policies:**
- Run database in private subnet
- Use security groups to restrict traffic
- Implement network segmentation

## API Security

### Authentication & Authorization

**API Key Management:**
```python
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
```

**Rate Limiting:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/query")
@limiter.limit("10/minute")
async def query(request: Request, ...):
    ...
```

### Input Validation

**Always validate & sanitize inputs:**
```python
from pydantic import BaseModel, Field, validator

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    upload_id: str = Field(..., regex=r"^[a-f0-9\-]{36}$")
    
    @validator('query')
    def query_no_sql_injection(cls, v):
        if any(word in v.lower() for word in ['select', 'drop', 'delete']):
            raise ValueError('Invalid query syntax')
        return v
```

### CORS Configuration

**Restrict CORS origins:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(','),
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "X-API-Key"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
)
```

### Error Handling

**Don't expose internal details:**
```python
# ❌ Bad: exposes internal error
raise HTTPException(500, detail=str(exception))

# ✅ Good: generic message to client
logger.error(f"Query failed: {exception}")
raise HTTPException(500, detail="Internal server error")
```

## Data Security

### File Upload Security

**Validate file uploads:**
```python
import magic

@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    # Check file size
    if file.size and file.size > settings.max_image_bytes:
        raise HTTPException(413, "File too large")
    
    # Check MIME type
    contents = await file.read()
    mime = magic.from_buffer(contents, mime=True)
    if mime not in ['image/tiff', 'image/png', 'image/jpeg']:
        raise HTTPException(415, "Unsupported file type")
    
    # Scan for malware (optional)
    # if scan_for_malware(contents):
    #     raise HTTPException(400, "File rejected")
    
    # Save with random name
    safe_filename = secrets.token_hex(16) + ".tif"
    ...
```

### Database Security

**Connection encryption:**
```python
# PostgreSQL with SSL
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require

# MySQL with SSL
DATABASE_URL=mysql+pymysql://user:pass@host/db?ssl_ca=/path/to/ca.pem
```

**SQL Injection Prevention:**
```python
# ✅ Use parameterized queries (SQLAlchemy ORM)
job = session.query(Job).filter(Job.id == user_id).first()

# ❌ Never concatenate strings
# job = session.execute(f"SELECT * FROM jobs WHERE id = '{user_id}'")
```

### Data Encryption

**Encrypt sensitive data:**
```python
from cryptography.fernet import Fernet

cipher_suite = Fernet(settings.encryption_key)

# Encrypt
encrypted_data = cipher_suite.encrypt(b"sensitive data")

# Decrypt
decrypted_data = cipher_suite.decrypt(encrypted_data)
```

### Data Retention & Deletion

```python
# Auto-delete old uploads
from datetime import datetime, timedelta

async def cleanup_old_uploads():
    cutoff = datetime.now() - timedelta(days=30)
    old_uploads = session.query(Upload).filter(
        Upload.created_at < cutoff
    ).all()
    
    for upload in old_uploads:
        os.remove(upload.file_path)
        session.delete(upload)
    
    session.commit()
```

## Vulnerability Management

### Dependency Scanning

**Automated with GitHub Actions:**
```yaml
# .github/workflows/security.yml
name: Security Scan
on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Bandit
        run: bandit -r app/
      - name: Run pip-audit
        run: pip-audit
```

### OWASP Top 10 Compliance

| Vulnerability | Mitigation |
|---|---|
| A1: Broken Authentication | Use strong API keys, rate limiting |
| A2: Broken Access Control | Validate permissions on every request |
| A3: Injection | Use parameterized queries, input validation |
| A4: Insecure Design | Follow secure design principles |
| A5: Security Misconfiguration | Security headers, minimal privileges |
| A6: Vulnerable Components | Dependency scanning, updates |
| A7: Authentication Failures | Strong passwords, MFA support |
| A8: Insecure Data Transport | HTTPS only, TLS 1.2+ |
| A9: Logging & Monitoring | Comprehensive audit logs |
| A10: SSRF | Validate URLs, whitelist hosts |

### Security Headers

```python
# Add security headers to responses
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

## Incident Response

### Security Contact

```
security@satquery.ai
PGP Key: https://satquery.ai/security.pgp
```

### Vulnerability Disclosure

1. **Do not** open public issues for security vulnerabilities
2. Email `security@satquery.ai` with details
3. Include affected versions and reproduction steps
4. Allow 90 days for patch before public disclosure
5. Credit will be given to researchers

### Incident Response Plan

1. **Detection:** Monitor logs and alerts
2. **Containment:** Isolate affected systems
3. **Investigation:** Determine scope and root cause
4. **Remediation:** Apply fixes
5. **Communication:** Notify affected users
6. **Recovery:** Restore service
7. **Post-Incident:** Review and improve

### Logging & Monitoring

**Log security events:**
```python
import logging

security_logger = logging.getLogger("security")

# Log authentication failures
security_logger.warning(f"Failed login attempt from {ip_address}")

# Log permission denials
security_logger.warning(f"Unauthorized access attempt: {user} → {resource}")

# Log suspicious patterns
security_logger.error(f"Multiple failed attempts from {ip_address}")
```

## Compliance

### GDPR Compliance
- Data retention policies
- User data export/deletion capabilities
- Privacy policy documentation
- Data processing agreements

### Security Checklist

- [ ] All dependencies scanned for vulnerabilities
- [ ] API keys stored securely (env vars, not code)
- [ ] HTTPS/TLS enabled
- [ ] Input validation on all endpoints
- [ ] Rate limiting enabled
- [ ] Security headers configured
- [ ] Logging and monitoring active
- [ ] Database encrypted at rest and in transit
- [ ] Regular backups tested
- [ ] Security audit performed
- [ ] Incident response plan documented
- [ ] Team trained on security practices

## References

- [OWASP Security Cheat Sheet](https://cheatsheetseries.owasp.org/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Python Security Guide](https://python.readthedocs.io/en/stable/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
