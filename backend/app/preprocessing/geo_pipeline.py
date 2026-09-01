"""
Geospatial Preprocessing Pipeline
Handles GeoTIFF ingestion, CRS normalization, band selection,
SAR detection, spatial alignment, tiling, and tensor conversion.
All geospatial metadata is preserved and propagated.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import Window
from scipy.ndimage import uniform_filter
import cv2

from app.models.schemas import (
    BoundingBox, InputFormat, InputMetadata, InputModality, InputRole,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

TARGET_CRS = "EPSG:4326"
MODEL_INPUT_SIZE = 512


# ─── Geospatial Image Container ───────────────────────────────────────────────

@dataclass
class GeoImage:
    """Carries image data alongside its full geospatial context."""
    array: np.ndarray          # [C, H, W] float32
    crs: str
    transform: Any             # rasterio Affine
    bbox_wgs84: BoundingBox
    bbox_native: BoundingBox
    modality: InputModality
    bands: int
    width: int
    height: int
    dtype_original: str
    nodata: float | None
    file_path: str
    file_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── File Utilities ───────────────────────────────────────────────────────────

def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_format(path: Path) -> InputFormat:
    suffix = path.suffix.lower()
    if suffix in (".tif", ".tiff"):
        return InputFormat.GEOTIFF
    if suffix == ".png":
        return InputFormat.PNG
    if suffix in (".jpg", ".jpeg"):
        return InputFormat.JPEG
    return InputFormat.UNKNOWN


def detect_modality(dataset: rasterio.DatasetReader) -> InputModality:
    """
    Heuristic modality detection from band count, dtype, and tag metadata.
    SAR images are typically single/dual band float32 with backscatter values.
    """
    tags = {k.lower(): v for k, v in dataset.tags().items()}
    # Explicit tag check
    if any("sar" in str(v).lower() or "backscatter" in str(v).lower() for v in tags.values()):
        return InputModality.SAR
    if any("sentinel-1" in str(v).lower() or "risat" in str(v).lower() for v in tags.values()):
        return InputModality.SAR

    band_count = dataset.count
    dtype = dataset.dtypes[0]

    # SAR heuristic: 1-2 bands, float32, values typically in linear or dB range
    if band_count <= 2 and dtype in ("float32", "float64"):
        sample = dataset.read(1, out_shape=(1, 64, 64), resampling=Resampling.nearest).astype(np.float32)
        valid = sample[np.isfinite(sample)]
        if len(valid) > 0:
            # Linear backscatter: very small positive values (0.0001 – 1.0)
            # dB backscatter: negative values (-30 to 0 dB)
            if valid.max() < 2.0 or valid.min() < -5.0:
                return InputModality.SAR

    if band_count >= 3:
        return InputModality.MULTISPECTRAL if band_count > 3 else InputModality.OPTICAL

    return InputModality.UNKNOWN


# ─── Core Ingestion ───────────────────────────────────────────────────────────

def ingest_geotiff(path: Path) -> GeoImage:
    """
    Read a GeoTIFF, reproject to WGS84, return a GeoImage.
    Preserves original CRS and transform alongside WGS84 equivalents.
    """
    file_hash = compute_file_hash(path)

    with rasterio.open(path) as ds:
        modality = detect_modality(ds)
        native_crs = ds.crs.to_string() if ds.crs else None
        native_transform = ds.transform
        native_bbox = BoundingBox(
            minx=ds.bounds.left, miny=ds.bounds.bottom,
            maxx=ds.bounds.right, maxy=ds.bounds.top,
            crs=native_crs or "UNKNOWN",
        )

        # Reproject to WGS84 for bounding box
        if ds.crs and ds.crs.to_epsg() != 4326:
            transform_wgs84, w_wgs84, h_wgs84 = calculate_default_transform(
                ds.crs, CRS.from_epsg(4326), ds.width, ds.height, *ds.bounds
            )
            from rasterio.warp import transform_bounds
            bounds_wgs84 = transform_bounds(ds.crs, CRS.from_epsg(4326), *ds.bounds)
        else:
            bounds_wgs84 = ds.bounds
            transform_wgs84 = native_transform

        bbox_wgs84 = BoundingBox(
            minx=bounds_wgs84[0], miny=bounds_wgs84[1],
            maxx=bounds_wgs84[2], maxy=bounds_wgs84[3],
            crs="EPSG:4326",
        )

        # Compute resolution in meters (approximate for geographic CRS)
        res_x, res_y = ds.res
        if ds.crs and ds.crs.is_geographic:
            # degrees → meters approximation at equator
            resolution_m = res_x * 111320.0
        else:
            resolution_m = res_x

        # Read all bands as float32
        array = ds.read().astype(np.float32)  # [C, H, W]
        nodata = ds.nodata

        return GeoImage(
            array=array,
            crs=native_crs or "UNKNOWN",
            transform=native_transform,
            bbox_wgs84=bbox_wgs84,
            bbox_native=native_bbox,
            modality=modality,
            bands=ds.count,
            width=ds.width,
            height=ds.height,
            dtype_original=str(ds.dtypes[0]),
            nodata=nodata,
            file_path=str(path),
            file_hash=file_hash,
            metadata={
                "resolution_m": resolution_m,
                "driver": ds.driver,
                "tags": dict(ds.tags()),
            },
        )


def ingest_png_jpeg(path: Path) -> GeoImage:
    """Ingest PNG/JPEG (benchmark datasets). No georeferencing available."""
    file_hash = compute_file_hash(path)
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    if img.ndim == 2:
        img = img[:, :, np.newaxis]
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    array = np.transpose(img, (2, 0, 1)).astype(np.float32)  # [C, H, W]
    h, w = array.shape[1], array.shape[2]
    dummy_bbox = BoundingBox(minx=0, miny=0, maxx=w, maxy=h, crs="PIXEL")
    return GeoImage(
        array=array,
        crs="PIXEL",
        transform=None,
        bbox_wgs84=dummy_bbox,
        bbox_native=dummy_bbox,
        modality=InputModality.OPTICAL,
        bands=array.shape[0],
        width=w,
        height=h,
        dtype_original=str(img.dtype),
        nodata=None,
        file_path=str(path),
        file_hash=file_hash,
    )


def ingest(path: Path) -> GeoImage:
    fmt = detect_format(path)
    if fmt == InputFormat.GEOTIFF:
        return ingest_geotiff(path)
    if fmt in (InputFormat.PNG, InputFormat.JPEG):
        return ingest_png_jpeg(path)
    raise ValueError(f"Unsupported format: {path.suffix}")


# ─── Band Selection ───────────────────────────────────────────────────────────

def select_rgb_bands(geo: GeoImage) -> np.ndarray:
    """
    Extract 3-band RGB-equivalent from multispectral image.
    Assumes standard band ordering: B, G, R, NIR, ... for Sentinel-2 style.
    Returns [3, H, W] float32.
    """
    c = geo.array.shape[0]
    if c == 1:
        return np.repeat(geo.array, 3, axis=0)
    if c == 2:
        return np.stack([geo.array[0], geo.array[1], geo.array[0]], axis=0)
    if c == 3:
        return geo.array
    # Multispectral: pick bands 3, 2, 1 (0-indexed) → R, G, B for Sentinel-2
    return geo.array[[3, 2, 1], :, :]  # Sentinel-2 true color


# ─── Normalization ────────────────────────────────────────────────────────────

def normalize_optical(array: np.ndarray, nodata: float | None = None) -> np.ndarray:
    """Per-band min-max normalization to [0, 1]."""
    out = array.copy()
    for i in range(out.shape[0]):
        band = out[i]
        if nodata is not None:
            mask = band != nodata
        else:
            mask = np.isfinite(band)
        if mask.sum() == 0:
            continue
        lo, hi = band[mask].min(), band[mask].max()
        if hi > lo:
            out[i] = np.where(mask, (band - lo) / (hi - lo), 0.0)
        else:
            out[i] = np.where(mask, 0.0, 0.0)
    return out.astype(np.float32)


def normalize_imagenet(array: np.ndarray) -> np.ndarray:
    """ImageNet mean/std normalization for models expecting it. Input [3,H,W] in [0,1]."""
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
    return (array - mean) / std


# ─── SAR Preprocessing ───────────────────────────────────────────────────────

def lee_filter(array: np.ndarray, size: int = 7) -> np.ndarray:
    """
    Lee speckle filter for SAR imagery.
    Applied per-band on linear-scale backscatter.
    """
    out = np.zeros_like(array)
    for i in range(array.shape[0]):
        band = array[i].astype(np.float64)
        mean = uniform_filter(band, size)
        mean_sq = uniform_filter(band ** 2, size)
        variance = mean_sq - mean ** 2
        # Noise variance estimate (ENL-based approximation)
        overall_var = np.var(band[np.isfinite(band)])
        noise_var = overall_var / max(overall_var, 1e-10)
        weight = variance / (variance + noise_var + 1e-10)
        out[i] = (mean + weight * (band - mean)).astype(np.float32)
    return out.astype(np.float32)


def to_db(array: np.ndarray) -> np.ndarray:
    """Convert linear backscatter to dB scale. Clips negative/zero values."""
    clipped = np.clip(array, 1e-10, None)
    return (10.0 * np.log10(clipped)).astype(np.float32)


def normalize_sar(array: np.ndarray, filter_type: str = "lee", filter_size: int = 7) -> np.ndarray:
    """Full SAR preprocessing: speckle filter → dB → normalize to [0,1]."""
    if filter_type == "lee":
        filtered = lee_filter(array, size=filter_size)
    elif filter_type == "median":
        from scipy.ndimage import median_filter
        filtered = np.stack([median_filter(array[i], size=filter_size) for i in range(array.shape[0])])
    else:
        filtered = array.copy()
    db = to_db(filtered)
    # Normalize dB range (typically -30 to 0 dB) to [0, 1]
    db_min, db_max = -30.0, 5.0
    normalized = np.clip((db - db_min) / (db_max - db_min), 0.0, 1.0)
    return normalized.astype(np.float32)


# ─── Resize / Tiling ─────────────────────────────────────────────────────────

def resize_array(array: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Resize [C, H, W] array to target spatial dimensions."""
    c = array.shape[0]
    out = np.zeros((c, target_h, target_w), dtype=np.float32)
    for i in range(c):
        out[i] = cv2.resize(array[i], (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    return out


def tile_image(array: np.ndarray, tile_size: int = 512, overlap: int = 64) -> list[dict]:
    """
    Tile a large [C, H, W] array into overlapping patches.
    Returns list of {array, row_start, col_start, row_end, col_end}.
    """
    _, h, w = array.shape
    stride = tile_size - overlap
    tiles = []
    for r in range(0, h, stride):
        for c in range(0, w, stride):
            r_end = min(r + tile_size, h)
            c_end = min(c + tile_size, w)
            r_start = max(0, r_end - tile_size)
            c_start = max(0, c_end - tile_size)
            tiles.append({
                "array": array[:, r_start:r_end, c_start:c_end],
                "row_start": r_start, "col_start": c_start,
                "row_end": r_end, "col_end": c_end,
            })
    return tiles


def stitch_tiles(tiles: list[dict], full_h: int, full_w: int, n_classes: int = 1) -> np.ndarray:
    """Stitch tiled predictions back into a full [n_classes, H, W] array using averaging."""
    output = np.zeros((n_classes, full_h, full_w), dtype=np.float32)
    count = np.zeros((full_h, full_w), dtype=np.float32)
    for tile in tiles:
        r0, c0, r1, c1 = tile["row_start"], tile["col_start"], tile["row_end"], tile["col_end"]
        pred = tile["prediction"]  # [n_classes, tile_h, tile_w]
        output[:, r0:r1, c0:c1] += pred
        count[r0:r1, c0:c1] += 1.0
    count = np.maximum(count, 1.0)
    return output / count[np.newaxis, :, :]


# ─── Spatial Alignment ────────────────────────────────────────────────────────

def check_spatial_overlap(geo1: GeoImage, geo2: GeoImage, min_iou: float = 0.3) -> tuple[bool, float]:
    """Check bounding box IoU between two images in WGS84."""
    b1, b2 = geo1.bbox_wgs84, geo2.bbox_wgs84
    ix1 = max(b1.minx, b2.minx)
    iy1 = max(b1.miny, b2.miny)
    ix2 = min(b1.maxx, b2.maxx)
    iy2 = min(b1.maxy, b2.maxy)
    if ix2 <= ix1 or iy2 <= iy1:
        return False, 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area1 = (b1.maxx - b1.minx) * (b1.maxy - b1.miny)
    area2 = (b2.maxx - b2.minx) * (b2.maxy - b2.miny)
    union = area1 + area2 - intersection
    iou = intersection / max(union, 1e-10)
    return iou >= min_iou, iou


def align_to_reference(
    source: GeoImage,
    reference: GeoImage,
    resampling: Resampling = Resampling.bilinear,
) -> GeoImage:
    """
    Reproject and resample source image to match reference image's
    CRS, transform, and spatial dimensions exactly.
    """
    if source.crs == "PIXEL" or reference.crs == "PIXEL":
        # No georeferencing — resize to match reference dimensions
        aligned = resize_array(source.array, reference.height, reference.width)
        return GeoImage(
            array=aligned,
            crs=reference.crs,
            transform=reference.transform,
            bbox_wgs84=reference.bbox_wgs84,
            bbox_native=reference.bbox_native,
            modality=source.modality,
            bands=source.bands,
            width=reference.width,
            height=reference.height,
            dtype_original=source.dtype_original,
            nodata=source.nodata,
            file_path=source.file_path,
            file_hash=source.file_hash,
        )

    src_crs = CRS.from_string(source.crs)
    dst_crs = CRS.from_string(reference.crs)
    c = source.array.shape[0]
    aligned = np.zeros((c, reference.height, reference.width), dtype=np.float32)

    for band_idx in range(c):
        reproject(
            source=source.array[band_idx],
            destination=aligned[band_idx],
            src_transform=source.transform,
            src_crs=src_crs,
            dst_transform=reference.transform,
            dst_crs=dst_crs,
            resampling=resampling,
        )

    return GeoImage(
        array=aligned,
        crs=reference.crs,
        transform=reference.transform,
        bbox_wgs84=reference.bbox_wgs84,
        bbox_native=reference.bbox_native,
        modality=source.modality,
        bands=source.bands,
        width=reference.width,
        height=reference.height,
        dtype_original=source.dtype_original,
        nodata=source.nodata,
        file_path=source.file_path,
        file_hash=source.file_hash,
    )


# ─── Metadata → Schema ───────────────────────────────────────────────────────

def geo_image_to_metadata(geo: GeoImage, role: InputRole, original_filename: str) -> InputMetadata:
    return InputMetadata(
        role=role,
        file_path=geo.file_path,
        file_hash=geo.file_hash,
        original_filename=original_filename,
        format=detect_format(Path(geo.file_path)),
        modality=geo.modality,
        crs=geo.crs,
        resolution_m=geo.metadata.get("resolution_m"),
        bands=geo.bands,
        width=geo.width,
        height=geo.height,
        dtype=geo.dtype_original,
        nodata=geo.nodata,
        has_georef=geo.crs not in ("PIXEL", "UNKNOWN", None),
        bbox_native=geo.bbox_native,
        bbox_wgs84=geo.bbox_wgs84,
        validation_status=ValidationStatus.PASSED,
    )


# ─── Prepare Model Input ─────────────────────────────────────────────────────

def prepare_optical_tensor(geo: GeoImage, size: int = MODEL_INPUT_SIZE) -> np.ndarray:
    """
    Full optical preprocessing pipeline:
    select RGB → normalize → resize → ImageNet normalize.
    Returns [3, size, size] float32.
    """
    rgb = select_rgb_bands(geo)
    rgb = normalize_optical(rgb, geo.nodata)
    rgb = resize_array(rgb, size, size)
    rgb = normalize_imagenet(rgb)
    return rgb


def prepare_sar_tensor(
    geo: GeoImage,
    size: int = MODEL_INPUT_SIZE,
    filter_type: str = "lee",
    filter_size: int = 7,
) -> np.ndarray:
    """
    Full SAR preprocessing pipeline:
    speckle filter → dB → normalize → resize.
    Returns [C, size, size] float32.
    """
    processed = normalize_sar(geo.array, filter_type=filter_type, filter_size=filter_size)
    return resize_array(processed, size, size)
