"""
Input Validator
Validates uploaded images against task requirements before any model inference.
Checks format, modality, spatial overlap, CRS compatibility, and band counts.
"""
from __future__ import annotations
import logging
from pathlib import Path
import numpy as np

from app.models.schemas import (
    InputFormat, InputMetadata, InputModality, InputRole,
    TaskType, ValidationStatus,
)
from app.preprocessing.geo_pipeline import (
    GeoImage, check_spatial_overlap, detect_format, ingest,
    geo_image_to_metadata,
)

logger = logging.getLogger(__name__)

# Minimum spatial overlap IoU for bi-temporal / cross-modal pairs
MIN_OVERLAP_IOU = 0.3
# Maximum resolution ratio between paired images (e.g., 10m vs 30m = 3x — acceptable)
MAX_RESOLUTION_RATIO = 10.0


class ValidationError(Exception):
    pass


def validate_and_ingest(
    file_paths: dict[str, Path],  # {upload_id: path}
    image_roles: dict[str, str],  # {upload_id: role string}
    task: TaskType,
) -> dict[str, tuple[GeoImage, InputMetadata]]:
    """
    Ingest all uploaded files, detect modality, validate against task requirements.
    Returns a dict of {upload_id: (GeoImage, InputMetadata)}.
    Raises ValidationError with a user-friendly message on failure.
    """
    if not file_paths:
        raise ValidationError("No images uploaded.")

    # ── Ingest all files ──────────────────────────────────────────────────────
    ingested: dict[str, tuple[GeoImage, InputMetadata]] = {}
    for uid, path in file_paths.items():
        fmt = detect_format(path)
        if fmt == InputFormat.UNKNOWN:
            raise ValidationError(f"Unsupported file format: {path.suffix}. Use GeoTIFF, PNG, or JPEG.")

        # Raster formats are supported by single-image and paired-image pipelines.
        if fmt in (InputFormat.PNG, InputFormat.JPEG) and task not in (
            TaskType.SINGLE_VQA,
            TaskType.SINGLE_CAPTION,
            TaskType.SINGLE_GROUNDING,
            TaskType.BITEMPORAL_CHANGE_DETECT,
            TaskType.BITEMPORAL_CHANGE_VQA,
            TaskType.CROSS_MODAL_ANALYSIS,
        ):
            raise ValidationError(
                f"{fmt.value} inputs are not supported for {task.value}. "
                "Use a supported raster format for this task."
            )

        try:
            geo = ingest(path)
        except Exception as e:
            raise ValidationError(f"Failed to read image '{path.name}': {e}")

        role_str = image_roles.get(uid, "PRIMARY")
        try:
            role = InputRole(role_str)
        except ValueError:
            raise ValidationError(f"Unknown image role '{role_str}'. Valid: PRIMARY, T1, T2, OPTICAL, SAR.")

        meta = geo_image_to_metadata(geo, role, path.name)
        ingested[uid] = (geo, meta)

    # ── Task-specific validation ──────────────────────────────────────────────
    geos = {uid: g for uid, (g, _) in ingested.items()}
    metas = {uid: m for uid, (_, m) in ingested.items()}

    if task in (TaskType.SINGLE_VQA, TaskType.SINGLE_CAPTION, TaskType.SINGLE_GROUNDING):
        _validate_single_image(geos, metas)

    elif task in (TaskType.BITEMPORAL_CHANGE_DETECT, TaskType.BITEMPORAL_CHANGE_VQA):
        _validate_bitemporal(geos, metas)

    elif task == TaskType.CROSS_MODAL_ANALYSIS:
        _validate_cross_modal(geos, metas)

    return ingested


def _validate_single_image(geos: dict, metas: dict) -> None:
    if len(geos) != 1:
        raise ValidationError(
            f"Single-image task requires exactly 1 image. Got {len(geos)}."
        )
    geo = list(geos.values())[0]
    meta = list(metas.values())[0]

    if geo.modality == InputModality.SAR:
        logger.warning("Single-image task received SAR input — VQA/captioning models expect optical imagery.")
        meta.validation_notes.append(
            "WARNING: SAR input for single-image task. Results may be degraded."
        )
        meta.validation_status = ValidationStatus.WARNING

    if geo.bands == 0:
        raise ValidationError("Image has no readable bands.")
    if geo.width < 32 or geo.height < 32:
        raise ValidationError("Image is too small for reliable remote-sensing analysis (minimum 32×32 pixels).")
    finite_ratio = float(np.isfinite(geo.array).mean()) if geo.array.size else 0.0
    if finite_ratio < 0.98:
        meta.validation_notes.append(f"WARNING: only {finite_ratio*100:.1f}% of pixels are finite.")
        meta.validation_status = ValidationStatus.WARNING


def _validate_bitemporal(geos: dict, metas: dict) -> None:
    if len(geos) != 2:
        raise ValidationError(
            f"Bi-temporal task requires exactly 2 images (T1 and T2). Got {len(geos)}."
        )

    roles = {uid: m.role for uid, m in metas.items()}
    t1_uid = _find_by_role(roles, InputRole.T1)
    t2_uid = _find_by_role(roles, InputRole.T2)

    if (t1_uid is None) != (t2_uid is None):
        missing = InputRole.T1.value if t1_uid is None else InputRole.T2.value
        raise ValidationError(
            f"Bi-temporal task requires both T1 and T2 image roles. Missing {missing}."
        )

    if t1_uid is None and t2_uid is None:
        # Fall back to upload order if roles not explicitly set
        uids = list(geos.keys())
        t1_uid, t2_uid = uids[0], uids[1]
        logger.warning("T1/T2 roles not set — assuming upload order: first=T1, second=T2.")
        for uid, meta in metas.items():
            meta.role = InputRole.T1 if uid == t1_uid else InputRole.T2
            meta.validation_notes.append("Role inferred from upload order.")

    t1, t2 = geos[t1_uid], geos[t2_uid]

    if (t1.width, t1.height) != (t2.width, t2.height):
        raise ValidationError(
            "T1 and T2 images must have compatible dimensions. "
            f"Got T1={t1.width}x{t1.height}, T2={t2.width}x{t2.height}."
        )

    # Modality check — both should be optical for change detection
    if t1.modality == InputModality.SAR or t2.modality == InputModality.SAR:
        metas[t1_uid].validation_notes.append(
            "WARNING: SAR input detected for bi-temporal task. "
            "ChangeFormer expects optical imagery."
        )
        metas[t1_uid].validation_status = ValidationStatus.WARNING

    # Spatial overlap check
    if t1.crs != "PIXEL" and t2.crs != "PIXEL":
        overlaps, iou = check_spatial_overlap(t1, t2, min_iou=MIN_OVERLAP_IOU)
        if not overlaps:
            raise ValidationError(
                f"T1 and T2 images have insufficient spatial overlap (IoU={iou:.3f} < {MIN_OVERLAP_IOU}). "
                "Ensure both images cover the same geographic area."
            )
        logger.info(f"Bi-temporal spatial overlap IoU: {iou:.3f}")

    # Resolution compatibility
    r1 = t1.metadata.get("resolution_m", 0)
    r2 = t2.metadata.get("resolution_m", 0)
    if r1 > 0 and r2 > 0:
        ratio = max(r1, r2) / min(r1, r2)
        if ratio > MAX_RESOLUTION_RATIO:
            metas[t1_uid].validation_notes.append(
                f"WARNING: Large resolution mismatch (T1={r1:.1f}m, T2={r2:.1f}m, ratio={ratio:.1f}x). "
                "Resampling will be applied."
            )
            metas[t1_uid].validation_status = ValidationStatus.WARNING


def _validate_cross_modal(geos: dict, metas: dict) -> None:
    if len(geos) != 2:
        raise ValidationError(
            f"Cross-modal task requires exactly 2 images (optical + SAR). Got {len(geos)}."
        )

    roles = {uid: m.role for uid, m in metas.items()}
    opt_uid = _find_by_role(roles, InputRole.OPTICAL)
    sar_uid = _find_by_role(roles, InputRole.SAR)

    if opt_uid is None or sar_uid is None:
        # Auto-detect from modality
        for uid, geo in geos.items():
            if geo.modality == InputModality.SAR:
                sar_uid = uid
                metas[uid].role = InputRole.SAR
            else:
                opt_uid = uid
                metas[uid].role = InputRole.OPTICAL

    if opt_uid is None or sar_uid is None:
        raise ValidationError(
            "Could not identify optical and SAR images. "
            "Please label images with roles OPTICAL and SAR."
        )

    opt, sar = geos[opt_uid], geos[sar_uid]

    # Spatial overlap check
    if opt.crs != "PIXEL" and sar.crs != "PIXEL":
        overlaps, iou = check_spatial_overlap(opt, sar, min_iou=MIN_OVERLAP_IOU)
        if not overlaps:
            raise ValidationError(
                f"Optical and SAR images have insufficient spatial overlap (IoU={iou:.3f}). "
                "Ensure images are co-registered over the same area."
            )
        logger.info(f"Optical-SAR spatial overlap IoU: {iou:.3f}")

    # Warn if not georeferenced (co-registration cannot be verified)
    if not opt.metadata.get("has_georef", False) or not sar.metadata.get("has_georef", False):
        metas[opt_uid].validation_notes.append(
            "WARNING: One or both images lack georeferencing. "
            "Co-registration quality cannot be verified."
        )
        metas[opt_uid].validation_status = ValidationStatus.WARNING


def _find_by_role(roles: dict[str, InputRole], target: InputRole) -> str | None:
    for uid, role in roles.items():
        if role == target:
            return uid
    return None
