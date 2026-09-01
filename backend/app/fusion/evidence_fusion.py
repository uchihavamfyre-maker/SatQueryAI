"""
Evidence Fusion + Confidence Estimation
Combines outputs from multiple tools into a single EvidenceObject.
Generates georeferenced overlays for the map viewer.
"""
from __future__ import annotations
import json
import logging
import uuid
from pathlib import Path

import numpy as np

from app.models.schemas import (
    DetectedRegion, EvidenceObject, ExecutionPlan, FusionResult,
    OutputType, TaskType, ToolOutput,
)
from app.preprocessing.geo_pipeline import GeoImage
from app.config import settings

logger = logging.getLogger(__name__)

# Per-tool confidence weights (higher = more trusted for final confidence)
_TOOL_WEIGHTS = {
    "RS_VQA": 0.85,
    "RS_CAPTION": 0.70,
    "RS_GROUNDING": 0.75,
    "RS_GROUNDING_FALLBACK": 0.80,
    "CHANGE_DETECTION": 0.85,
    "CHANGE_CAPTION": 0.70,
    "CHANGE_VQA": 0.80,
    "OPTICAL_SAR_ANALYZER": 0.80,
    "SAR_PREPROCESS": 1.0,
    "RS_EMBED": 0.65,
}


def fuse_and_build_evidence(
    plan: ExecutionPlan,
    geo_images: dict[str, GeoImage],
    llm_synthesizer=None,
) -> EvidenceObject:
    """
    Collect all tool outputs from the plan, fuse them into a coherent
    EvidenceObject with answer, confidence, spatial overlays, and trace.
    """
    completed_calls = [tc for tc in plan.tool_calls if tc.output is not None]
    task = plan.query.classified_task

    text_parts: list[str] = []
    detected_regions: list[DetectedRegion] = []
    change_map_path: str | None = None
    overlay_path: str | None = None
    geojson_path: str | None = None
    models_used: list[str] = []
    weighted_confidences: list[tuple[float, float]] = []  # (confidence, weight)

    for tc in completed_calls:
        out = tc.output
        models_used.append(f"{tc.tool_key}:{tc.model_name}")
        weight = _TOOL_WEIGHTS.get(tc.tool_key, 0.5)

        if out.confidence > 0:
            weighted_confidences.append((out.confidence, weight))

        # ── Text outputs ──────────────────────────────────────────────────────
        if out.type == OutputType.TEXT:
            val = out.value
            if "answer" in val and not val.get("stub"):
                text_parts.append(val["answer"])
            if "caption" in val:
                text_parts.append(val["caption"])

        # ── Bounding box outputs ──────────────────────────────────────────────
        elif out.type == OutputType.BBOX:
            for bbox in out.value.get("bboxes", []):
                detected_regions.append(DetectedRegion(
                    label=bbox.get("label", "region"),
                    bbox_pixels=[bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]],
                    score=bbox.get("score", 0.0),
                ))

        # ── Mask outputs (change detection) ──────────────────────────────────
        elif out.type == OutputType.MASK and tc.tool_key == "CHANGE_DETECTION":
            change_mask_arr = np.array(out.value.get("change_mask", []))
            change_ratio = out.value.get("change_ratio", 0.0)
            if change_mask_arr.size > 0:
                change_map_path = _save_change_map(change_mask_arr, plan.job_id, geo_images, plan)
                geojson_path = _save_change_geojson(change_mask_arr, plan.job_id, geo_images, plan)
                changed_area_km2 = _estimate_mask_area_km2(change_mask_arr, geo_images, plan)
                # Give the map viewer a geographic extent even when no object detector produced boxes.
                primary_geo = next((geo_images[m.input_id] for m in plan.inputs if m.input_id in geo_images), None)
                if primary_geo is not None:
                    detected_regions.append(DetectedRegion(
                        label="changed_area",
                        bbox_geo=primary_geo.bbox_wgs84,
                        area_km2=changed_area_km2,
                        score=float(out.confidence),
                    ))
                text_parts.append(f"Change detected in {change_ratio * 100:.1f}% of the scene area" + (f" ({changed_area_km2:.3f} km²)." if changed_area_km2 is not None else "."))

        # ── Segmentation outputs (optical+SAR) ────────────────────────────────
        elif out.type == OutputType.SEGMENTATION:
            seg_mask = np.array(out.value.get("segmentation_mask", []))
            class_areas = out.value.get("class_areas_km2", {})
            classes = out.value.get("classes", [])
            if seg_mask.size > 0:
                overlay_path = _save_segmentation_overlay(
                    seg_mask, classes, plan.job_id
                )
            # Build text summary
            area_summary = ", ".join(
                f"{cls}: {area:.2f} km²"
                for cls, area in class_areas.items()
                if area > 0
            )
            if area_summary:
                text_parts.append(f"Land cover analysis — {area_summary}.")
            # Add detected regions for dominant classes
            for i, cls_name in enumerate(classes):
                area = class_areas.get(cls_name, 0)
                conf = out.value.get("class_confidences", {}).get(cls_name, 0.0)
                if area > 0:
                    detected_regions.append(DetectedRegion(
                        label=cls_name,
                        area_km2=area,
                        score=conf,
                    ))

    # ── Aggregate confidence ──────────────────────────────────────────────────
    agg_confidence, rationale = _aggregate_confidence(weighted_confidences, completed_calls)

    # ── Synthesize final answer ───────────────────────────────────────────────
    final_answer = _synthesize_answer(text_parts, task, plan.query.raw_text, llm_synthesizer)

    # ── Georeference bounding boxes ───────────────────────────────────────────
    detected_regions = _georeference_regions(detected_regions, geo_images, plan)

    quality = _build_input_quality(plan)
    fusion = FusionResult(
        text_outputs=text_parts,
        spatial_output_paths=[p for p in [change_map_path, overlay_path, geojson_path] if p],
        aggregated_confidence=agg_confidence,
        confidence_rationale=rationale,
    )
    plan.fusion = fusion

    # Baseline results are intentionally capped to avoid presenting heuristic confidence as model confidence.
    if any(tc.output and tc.output.metadata.get("status") == "BASELINE" for tc in completed_calls):
        agg_confidence = min(agg_confidence, 0.69)
        rationale += " Baseline-only result: confidence capped at 0.69 until a trained checkpoint is loaded."
    if any(m.validation_status.value == "WARNING" for m in plan.inputs):
        agg_confidence = min(agg_confidence, 0.75)
        rationale += " Input validation warning present: confidence capped at 0.75."

    return EvidenceObject(
        job_id=plan.job_id,
        answer=final_answer,
        confidence=agg_confidence,
        confidence_rationale=rationale,
        task=task,
        detected_regions=detected_regions,
        change_map_path=change_map_path,
        overlay_path=overlay_path,
        geojson_path=geojson_path,
        report_url=f"/job/{plan.job_id}/report",
        input_quality=quality,
        supporting_text=text_parts,
        models_used=models_used,
        execution_plan=plan,
    )



def _build_input_quality(plan: ExecutionPlan) -> dict[str, Any]:
    """Create a compact, judge-friendly preflight/quality summary."""
    warnings = []
    for m in plan.inputs:
        warnings.extend(m.validation_notes)
    georef = sum(1 for m in plan.inputs if m.has_georef)
    return {
        "inputs": len(plan.inputs),
        "georeferenced": georef,
        "georeference_complete": georef == len(plan.inputs),
        "warnings": warnings,
        "status": "WARNING" if warnings else "PASSED",
    }


def _estimate_mask_area_km2(mask: np.ndarray, geo_images: dict[str, GeoImage], plan: ExecutionPlan) -> float | None:
    """Estimate area from the primary/T1 raster transform without assuming a fixed resolution."""
    if mask.size == 0:
        return None
    geo = None
    for m in plan.inputs:
        if m.input_id in geo_images:
            geo = geo_images[m.input_id]
            break
    if geo is None or geo.transform is None or geo.crs == "PIXEL":
        return None
    changed = int((mask > 0).sum())
    if changed == 0:
        return 0.0
    try:
        from pyproj import Geod
        t = geo.transform
        if geo.crs.upper() == "EPSG:4326" or "4326" in geo.crs:
            lat = float(geo.bbox_wgs84.miny + geo.bbox_wgs84.maxy) / 2
            width_m = abs(t.a) * 111320.0 * max(0.1, np.cos(np.deg2rad(lat)))
            height_m = abs(t.e) * 110574.0
            return changed * width_m * height_m / 1e6
        return changed * abs(t.a * t.e) / 1e6
    except Exception:
        res = geo.metadata.get("resolution_m")
        return changed * (float(res) ** 2) / 1e6 if res else None


def _save_change_geojson(mask: np.ndarray, job_id: str, geo_images: dict[str, GeoImage], plan: ExecutionPlan) -> str | None:
    """Polygonize the change mask into a compact GeoJSON evidence artifact."""
    geo = None
    for m in plan.inputs:
        if m.input_id in geo_images:
            geo = geo_images[m.input_id]
            break
    if geo is None or geo.transform is None or geo.crs == "PIXEL":
        return None
    try:
        from rasterio.features import shapes
        from shapely.geometry import shape, mapping
        from shapely.ops import transform as shp_transform
        import json
        import pyproj
        geoms = []
        for geom, value in shapes(mask.astype(np.uint8), mask=(mask > 0), transform=geo.transform):
            if value != 1:
                continue
            g = shape(geom)
            if g.area > 0:
                geoms.append(g)
        if not geoms:
            return None
        # Convert to WGS84 when source CRS is known.
        if geo.crs and geo.crs != "EPSG:4326":
            transformer = pyproj.Transformer.from_crs(geo.crs, "EPSG:4326", always_xy=True)
            geoms = [shp_transform(transformer.transform, g) for g in geoms]
        # Avoid enormous artifacts: keep the largest 100 polygons.
        geoms = sorted(geoms, key=lambda g: g.area, reverse=True)[:100]
        fc = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"job_id":job_id,"label":"change"},"geometry":mapping(g)} for g in geoms]}
        out = settings.results_dir / f"{job_id}_change.geojson"
        out.write_text(json.dumps(fc, separators=(",",":")), encoding="utf-8")
        return str(out)
    except Exception as e:
        logger.warning("GeoJSON export skipped: %s", e)
        return None

def _aggregate_confidence(
    weighted: list[tuple[float, float]],
    completed_calls,
) -> tuple[float, str]:
    if not weighted:
        return 0.0, "No model confidence scores available."

    total_weight = sum(w for _, w in weighted)
    if total_weight == 0:
        return 0.0, "Zero total weight."

    agg = sum(c * w for c, w in weighted) / total_weight
    model_scores = ", ".join(
        f"{tc.tool_key}={tc.output.confidence:.2f}"
        for tc in completed_calls
        if tc.output and tc.output.confidence > 0
    )
    rationale = f"Weighted average confidence ({agg:.2f}) from: {model_scores}"
    return round(agg, 3), rationale


def _synthesize_answer(
    text_parts: list[str],
    task: TaskType,
    query: str,
    llm_synthesizer=None,
) -> str:
    if not text_parts:
        return "Analysis complete. No textual output was produced by the selected models."

    if len(text_parts) == 1:
        return text_parts[0]

    # If LLM synthesizer is available, use it to merge multiple text outputs
    if llm_synthesizer is not None:
        try:
            return llm_synthesizer.synthesize(query, text_parts)
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}")

    # Fallback: join with newlines
    return " ".join(text_parts)


def _save_change_map(
    mask: np.ndarray,
    job_id: str,
    geo_images: dict[str, GeoImage],
    plan: ExecutionPlan,
) -> str:
    """Save binary change mask as a georeferenced PNG overlay."""
    import cv2
    out_path = settings.results_dir / f"{job_id}_change_map.png"

    # Colorize: changed=red, unchanged=transparent
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask == 1] = [255, 50, 50, 200]   # red with alpha
    rgba[mask == 0] = [0, 0, 0, 0]          # transparent

    cv2.imwrite(str(out_path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    return str(out_path)


def _save_segmentation_overlay(
    seg_mask: np.ndarray,
    classes: list[str],
    job_id: str,
) -> str:
    """Save segmentation mask as a colored PNG overlay."""
    import cv2
    out_path = settings.results_dir / f"{job_id}_segmentation.png"

    # Color palette per class
    palette = [
        [255, 100, 100, 180],   # built_up — red
        [100, 150, 255, 180],   # water — blue
        [100, 200, 100, 180],   # vegetation — green
        [200, 180, 100, 180],   # bare_soil — tan
        [180, 180, 180, 180],   # other — grey
    ]
    h, w = seg_mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for i, color in enumerate(palette[:len(classes)]):
        rgba[seg_mask == i] = color

    cv2.imwrite(str(out_path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    return str(out_path)


def _georeference_regions(
    regions: list[DetectedRegion],
    geo_images: dict[str, GeoImage],
    plan: ExecutionPlan,
) -> list[DetectedRegion]:
    """
    Convert pixel-coordinate bounding boxes to geographic coordinates
    using the primary image's affine transform.
    """
    if not regions:
        return regions

    # Find primary geo image
    primary_geo = None
    for meta in plan.inputs:
        if meta.input_id in geo_images:
            primary_geo = geo_images[meta.input_id]
            break

    if primary_geo is None or primary_geo.transform is None:
        return regions

    from rasterio.transform import xy as rasterio_xy

    for region in regions:
        if region.bbox_pixels is None:
            continue
        x1, y1, x2, y2 = region.bbox_pixels
        # Convert pixel corners to geographic coordinates
        try:
            lon1, lat1 = rasterio_xy(primary_geo.transform, y1, x1, offset="ul")
            lon2, lat2 = rasterio_xy(primary_geo.transform, y2, x2, offset="ul")
            from app.models.schemas import BoundingBox
            region.bbox_geo = BoundingBox(
                minx=min(lon1, lon2), miny=min(lat1, lat2),
                maxx=max(lon1, lon2), maxy=max(lat1, lat2),
                crs=primary_geo.crs,
            )
        except Exception:
            pass  # Non-georeferenced image — skip

    return regions
