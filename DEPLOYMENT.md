# Production Deployment

## Docker Compose

1. Copy `backend/.env.example` to `backend/.env`.
2. Set `CORS_ORIGINS` to the public origin that will serve the app.
3. Set a long random `API_KEY` for a private deployment, and build the frontend with the matching `VITE_API_KEY`.
4. Start the service:

```bash
docker compose up --build -d
```

The application is available at `http://localhost:8000`. Put it behind an HTTPS reverse proxy before exposing it publicly.

The default Docker image installs `backend/requirements-lite.txt` for the CPU/baseline path. Heavy PyTorch and Transformers dependencies are optional; enable them only for a suitable host with `docker build --build-arg INSTALL_HEAVY_MODELS=true ...`.

For a separately hosted frontend, build it with `VITE_API_URL=https://your-api.example.com` and add that frontend origin to `CORS_ORIGINS`. The default empty value uses same-origin requests when FastAPI serves `frontend/dist`.

The `satquery-data` volume stores the SQLite database, uploads, caches, results, and traces. For multiple replicas, replace SQLite with PostgreSQL and move artifacts to object storage.

## Render Free Tier

The repository includes `render.yaml` for a free Docker web service. Create a new Blueprint in Render from this repository, set `CORS_ORIGINS` to the frontend origin, and set `API_KEY` to a long random value. Render free services sleep when idle and their local filesystem is ephemeral, so uploaded files and SQLite data can be lost on restart; this is suitable for a demo, not durable production data.

## Local Production Build

```bash
cd frontend
npm install
npm run build
cd ../backend
venv\\Scripts\\python.exe run.py
```

The backend serves `frontend/dist` when it exists. Without a frontend build it falls back to the legacy demo page.

## Model Transparency

The default configuration uses the explicit baseline mode. PaliGemma, ChangeFormer, GeoChat, SAM, and fusion checkpoints must be installed and configured separately; the service reports fallback status rather than pretending a missing model ran.