from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import cv2
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.dispatcher import ToolDispatcher, _build_role_map
from app.agent.registry import get_registry
from app.agent.validator import ValidationError, validate_and_ingest
from app.models.schemas import (
    ExecutionPlan,
    InputFormat,
    InputMetadata,
    InputModality,
    InputRole,
    QueryInfo,
    TaskType,
)


def _plan(*metas: InputMetadata, task: TaskType) -> ExecutionPlan:
    return ExecutionPlan(
        job_id="test-job",
        query=QueryInfo(raw_text="test", classified_task=task),
        inputs=list(metas),
    )


def _metadata(path: str, role: InputRole, modality: InputModality) -> InputMetadata:
    return InputMetadata(
        role=role,
        modality=modality,
        format=InputFormat.JPEG if path.endswith(".jpg") else InputFormat.PNG,
        file_path=path,
        file_hash=path,
        original_filename=Path(path).name,
        width=64,
        height=64,
        bands=3,
    )


def _geo(path: str, modality: InputModality) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=path,
        modality=modality,
        array=np.ones((3, 64, 64), dtype=np.float32),
        crs="PIXEL",
        transform=None,
        bbox_wgs84=None,
        bbox_native=None,
        bands=3,
        width=64,
        height=64,
        dtype_original="float32",
        nodata=None,
        file_hash=path,
        metadata={},
    )


def _write_raster(path: Path, width: int = 64, height: int = 64) -> None:
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        image = np.full((height, width, 3), 128, dtype=np.uint8)
        assert cv2.imwrite(str(path), image)
        return
    data = np.full((3, height, width), 128, dtype=np.uint8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype=data.dtype,
        transform=from_origin(0, height, 1, 1),
    ) as dataset:
        dataset.write(data)


@pytest.mark.parametrize("extension", [".jpg", ".png", ".tif"])
def test_bitemporal_pair_accepts_supported_raster_formats(tmp_path: Path, extension: str) -> None:
    t1_path = tmp_path / f"t1{extension}"
    t2_path = tmp_path / f"t2{extension}"
    _write_raster(t1_path)
    _write_raster(t2_path)

    ingested = validate_and_ingest(
        {"t1-upload": t1_path, "t2-upload": t2_path},
        {"t1-upload": "T1", "t2-upload": "T2"},
        TaskType.BITEMPORAL_CHANGE_DETECT,
    )

    assert len(ingested) == 2
    assert {metadata.role for _, metadata in ingested.values()} == {InputRole.T1, InputRole.T2}
    assert all(geo.width == 64 and geo.height == 64 for geo, _ in ingested.values())


def test_bitemporal_rejects_missing_t2_role(tmp_path: Path) -> None:
    t1_path = tmp_path / "t1.jpg"
    second_path = tmp_path / "unassigned.jpg"
    _write_raster(t1_path)
    _write_raster(second_path)

    with pytest.raises(ValidationError, match="Missing T2"):
        validate_and_ingest(
            {"t1-upload": t1_path, "second-upload": second_path},
            {"t1-upload": "T1", "second-upload": "PRIMARY"},
            TaskType.BITEMPORAL_CHANGE_DETECT,
        )


def test_bitemporal_rejects_incompatible_dimensions(tmp_path: Path) -> None:
    t1_path = tmp_path / "t1.png"
    t2_path = tmp_path / "t2.png"
    _write_raster(t1_path, width=64, height=64)
    _write_raster(t2_path, width=32, height=64)

    with pytest.raises(ValidationError, match="compatible dimensions"):
        validate_and_ingest(
            {"t1-upload": t1_path, "t2-upload": t2_path},
            {"t1-upload": "T1", "t2-upload": "T2"},
            TaskType.BITEMPORAL_CHANGE_DETECT,
        )


def test_primary_optical_resolves_for_rs_vqa() -> None:
    meta = _metadata("image.jpg", InputRole.PRIMARY, InputModality.OPTICAL)
    plan = _plan(meta, task=TaskType.SINGLE_VQA)
    geo = _geo("image.jpg", InputModality.OPTICAL)
    dispatcher = ToolDispatcher(get_registry())

    inputs = dispatcher._prepare_inputs(
        "RS_VQA", _build_role_map(plan, {"upload-id": geo}), {}, "What land cover type dominates this image?"
    )

    assert inputs["image"].shape == (3, 512, 512)


def test_exact_primary_optical_jpeg_reaches_vqa_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RSVQA_BACKEND", "baseline")
    image_path = tmp_path / "image.jpg"
    cv2.imwrite(str(image_path), np.full((64, 64, 3), 128, dtype=np.uint8))
    ingested = validate_and_ingest(
        {"upload-id": image_path}, {"upload-id": "PRIMARY"}, TaskType.SINGLE_VQA
    )
    geo, meta = next(iter(ingested.values()))
    plan = _plan(meta, task=TaskType.SINGLE_VQA)
    dispatcher = ToolDispatcher(get_registry())

    from app.models.schemas import ToolCall
    plan.tool_calls = [ToolCall(
        tool_key="RS_VQA",
        model_name="test",
        model_version="test",
        input_artifacts=[meta.input_id],
    )]
    executed = dispatcher.execute(
        plan,
        {"upload-id": geo},
        "What land cover type dominates this image?",
    )

    call = executed.tool_calls[0]
    assert call.status.value == "COMPLETED"
    assert call.output is not None
    assert call.output.metadata["status"] == "BASELINE"
    assert call.output.value["answer"]


@pytest.mark.parametrize("tool_key", ["RS_CAPTION", "RS_GROUNDING", "RS_GROUNDING_FALLBACK"])
def test_primary_optical_resolves_for_single_image_tools(tool_key: str) -> None:
    meta = _metadata("image.jpg", InputRole.PRIMARY, InputModality.OPTICAL)
    plan = _plan(meta, task=TaskType.SINGLE_GROUNDING)
    geo = _geo("image.jpg", InputModality.OPTICAL)
    dispatcher = ToolDispatcher(get_registry())

    inputs = dispatcher._prepare_inputs(tool_key, _build_role_map(plan, {"upload-id": geo}), {}, "find buildings")

    if tool_key == "RS_GROUNDING_FALLBACK":
        assert inputs["image"].shape == (512, 512, 3)
    else:
        assert inputs["image"].shape == (3, 512, 512)


def test_primary_without_required_optical_modality_fails() -> None:
    meta = _metadata("image.jpg", InputRole.PRIMARY, InputModality.SAR)
    plan = _plan(meta, task=TaskType.SINGLE_VQA)
    geo = _geo("image.jpg", InputModality.SAR)
    dispatcher = ToolDispatcher(get_registry())

    with pytest.raises(ValueError, match="Required image role"):
        dispatcher._prepare_inputs("RS_VQA", _build_role_map(plan, {"upload-id": geo}), {}, "land cover")


def test_t1_t2_change_detection_resolves_both_inputs() -> None:
    t1_meta = _metadata("t1.png", InputRole.T1, InputModality.OPTICAL)
    t2_meta = _metadata("t2.png", InputRole.T2, InputModality.OPTICAL)
    plan = _plan(t1_meta, t2_meta, task=TaskType.BITEMPORAL_CHANGE_DETECT)
    geo_images = {
        "t1-upload": _geo("t1.png", InputModality.OPTICAL),
        "t2-upload": _geo("t2.png", InputModality.OPTICAL),
    }
    dispatcher = ToolDispatcher(get_registry())

    inputs = dispatcher._prepare_inputs(
        "CHANGE_DETECTION", _build_role_map(plan, geo_images), {}, "what changed?"
    )

    assert inputs["image_t1"].shape == (3, 512, 512)
    assert inputs["image_t2"].shape == (3, 512, 512)


def test_optical_sar_fusion_resolves_both_modalities() -> None:
    optical_meta = _metadata("optical.tif", InputRole.OPTICAL, InputModality.OPTICAL)
    sar_meta = _metadata("sar.tif", InputRole.SAR, InputModality.SAR)
    plan = _plan(optical_meta, sar_meta, task=TaskType.CROSS_MODAL_ANALYSIS)
    geo_images = {
        "optical-upload": _geo("optical.tif", InputModality.OPTICAL),
        "sar-upload": _geo("sar.tif", InputModality.SAR),
    }
    dispatcher = ToolDispatcher(get_registry())

    inputs = dispatcher._prepare_inputs(
        "OPTICAL_SAR_ANALYZER", _build_role_map(plan, geo_images), {}, "classify land cover"
    )

    assert inputs["optical"].shape == (3, 512, 512)
    assert inputs["sar"].shape == (3, 512, 512)