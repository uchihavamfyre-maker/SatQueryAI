FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
COPY backend/requirements-lite.txt ./backend/requirements-lite.txt
ARG INSTALL_HEAVY_MODELS=false
RUN pip install --upgrade pip && pip install -r backend/requirements-lite.txt && \
    if [ "$INSTALL_HEAVY_MODELS" = "true" ]; then pip install -r backend/requirements.txt; fi

COPY backend/app ./backend/app
COPY backend/configs ./backend/configs
COPY backend/run.py ./backend/run.py
COPY --from=frontend-build /frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 8000
CMD ["python", "run.py"]