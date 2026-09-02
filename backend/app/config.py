import os
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent  # satquery/backend/


def _normalize_database_url(url: str) -> str:
    if not url.startswith(("postgres://", "postgresql://")):
        return url

    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.pop("sslmode", None) == "require":
        query["ssl"] = "require"
    query.pop("channel_binding", None)
    return urlunsplit(
        ("postgresql+asyncpg", parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _default_data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", BASE_DIR.parent / "data"))


def _parse_cors_origins(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [origin.strip() for origin in value.split(",")]
    if isinstance(parsed, str):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(origin, str) for origin in parsed):
        return parsed
    raise ValueError("CORS_ORIGINS must be a URL, comma-separated URLs, or a JSON list.")


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path(os.getenv("DATA_DIR", BASE_DIR.parent / "data"))
    upload_dir: Path = BASE_DIR.parent / "data" / "uploads"
    cache_dir: Path = BASE_DIR.parent / "data" / "cache"
    results_dir: Path = BASE_DIR.parent / "data" / "results"
    traces_dir: Path = BASE_DIR.parent / "data" / "traces"
    registry_path: Path = BASE_DIR / "configs" / "registry.yaml"
    models_dir: Path = BASE_DIR.parent / "data" / "models"
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR.parent / 'data' / 'satquery.db'}"

    # LLM orchestrator
    orchestrator_model: str = "mistralai/Mistral-7B-Instruct-v0.2"
    orchestrator_device: str = "auto"
    orchestrator_load_in_4bit: bool = True

    # Inference
    default_device: str = "cpu"
    tile_size: int = 512
    tile_overlap: int = 64
    max_image_bytes: int = 500 * 1024 * 1024  # 500 MB
    max_image_pixels: int = 100_000_000

    # Public map-click imagery (Earth Search Sentinel-2 COGs; no credentials)
    imagery_stac_url: str = "https://earth-search.aws.element84.com/v1/search"
    imagery_collection: str = "sentinel-2-l2a"
    imagery_days_back: int = 90
    imagery_max_cloud_cover: float = 30.0
    imagery_tile_size: int = 256

    # API
    cors_origins: str | list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
    ]
    max_concurrent_jobs: int = 1
    api_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

    @model_validator(mode="before")
    @classmethod
    def derive_storage_paths(cls, values):
        values = dict(values or {})
        if values.get("database_url"):
            values["database_url"] = _normalize_database_url(values["database_url"])
        data_dir = Path(values.get("data_dir") or _default_data_dir())
        values["data_dir"] = data_dir
        values.setdefault("upload_dir", data_dir / "uploads")
        values.setdefault("cache_dir", data_dir / "cache")
        values.setdefault("results_dir", data_dir / "results")
        values.setdefault("traces_dir", data_dir / "traces")
        values.setdefault("models_dir", data_dir / "models")
        values.setdefault("database_url", f"sqlite+aiosqlite:///{data_dir / 'satquery.db'}")
        return values

    @property
    def cors_origin_list(self) -> list[str]:
        return _parse_cors_origins(self.cors_origins)


settings = Settings()

# Ensure directories exist
for d in [
    settings.upload_dir,
    settings.cache_dir,
    settings.results_dir,
    settings.traces_dir,
    settings.models_dir,
]:
    d.mkdir(parents=True, exist_ok=True)
