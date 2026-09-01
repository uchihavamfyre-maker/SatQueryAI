"""
Tool Dispatcher
Executes an ExecutionPlan by routing preprocessed image data to each
registered tool in sequence. Manages tool lifecycle and collects outputs.
"""
from __future__ import annotations
import logging
import numpy as np
from pathlib import Path
from typing import Any

from app.agent.registry import ModelRegistry
from app.models.schemas import (
    ExecutionPlan, InputModality, InputRole, TaskType,
    ToolCall, ToolCallStatus, ToolOutput,
)
from app.preprocessing.geo_pipeline import (
    GeoImage, align_to_reference, prepare_optical_tensor,
    prepare_sar_tensor, resize_array,
)
from app.config import settings

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """
    Routes execution plan tool calls to instantiated tool objects.
    Handles input preparation per tool type.
    """

    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._tool_instances: dict[str, Any] = {}

    def _get_tool(self, key: str):
        if key not in self._tool_instances:
            self._tool_instances[key] = self.registry.instantiate_tool(key)
        return self._tool_instances[key]

    def execute(
        self,
        plan: ExecutionPlan,
        geo_images: dict[str, GeoImage],  # {input_id: GeoImage}
        query: str,
    ) -> ExecutionPlan:
        """
        Execute all tool calls in the plan sequentially.
        Updates plan.tool_calls in-place with outputs.
        Returns the updated plan.
        """
        # Build role → GeoImage mapping
        role_map = _build_role_map(plan, geo_images)

        # Track intermediate outputs for chaining (e.g., change mask → change VQA)
        intermediate: dict[str, Any] = {"query": query}

        for tc in plan.tool_calls:
            tc.status = ToolCallStatus.RUNNING
            try:
                inputs = self._prepare_inputs(tc.tool_key, role_map, intermediate, query)
                tool = self._get_tool(tc.tool_key)
                output: ToolOutput = tool.run(inputs, tc.parameters)
                tc.output = output
                tc.status = ToolCallStatus.COMPLETED
                # Store output for downstream tools
                intermediate[tc.tool_key] = output
                logger.info(f"Tool {tc.tool_key} completed: confidence={output.confidence:.3f}")
            except Exception as e:
                logger.exception(f"Tool {tc.tool_key} raised exception: {e}")
                tc.status = ToolCallStatus.FAILED
                tc.error = str(e)

        return plan

    def _prepare_inputs(
        self,
        tool_key: str,
        role_map: dict[str, GeoImage],
        intermediate: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        """
        Build the input dict for a specific tool based on its key.
        Each tool has a defined input contract (see registry.yaml input_schema).
        """
        size = settings.tile_size

        if tool_key == "RS_VQA":
            geo = _require_role(
                role_map,
                [InputRole.PRIMARY, InputRole.OPTICAL],
                modalities={InputModality.OPTICAL, InputModality.MULTISPECTRAL},
            )
            return {
                "image": prepare_optical_tensor(geo, size),
                "question": query,
            }

        if tool_key == "RS_CAPTION":
            geo = _require_role(
                role_map,
                [InputRole.PRIMARY, InputRole.OPTICAL],
                modalities={InputModality.OPTICAL, InputModality.MULTISPECTRAL},
            )
            arr = prepare_optical_tensor(geo, size)
            # Denormalize from ImageNet for GeoChat (expects [0,1])
            arr = _denormalize_imagenet(arr)
            return {"image": arr, "prompt": query}

        if tool_key == "RS_GROUNDING":
            geo = _require_role(
                role_map,
                [InputRole.PRIMARY, InputRole.OPTICAL],
                modalities={InputModality.OPTICAL, InputModality.MULTISPECTRAL},
            )
            arr = prepare_optical_tensor(geo, size)
            arr = _denormalize_imagenet(arr)
            return {"image": arr, "query": query}

        if tool_key == "RS_GROUNDING_FALLBACK":
            geo = _require_role(
                role_map,
                [InputRole.PRIMARY, InputRole.OPTICAL],
                modalities={InputModality.OPTICAL, InputModality.MULTISPECTRAL},
            )
            # SAM needs uint8 HWC
            arr = prepare_optical_tensor(geo, size)
            arr = _denormalize_imagenet(arr)
            hw3 = (np.transpose(np.clip(arr, 0, 1), (1, 2, 0)) * 255).astype(np.uint8)
            # Get boxes from upstream RS_GROUNDING output
            grounding_out = intermediate.get("RS_GROUNDING")
            boxes = grounding_out.value.get("bboxes", []) if grounding_out else []
            return {"image": hw3, "boxes": boxes}

        if tool_key == "SAR_PREPROCESS":
            geo = _require_role(role_map, [InputRole.SAR])
            return {"sar_array": geo.array.astype(np.float32)}

        if tool_key == "CHANGE_DETECTION":
            t1 = _require_role(role_map, [InputRole.T1])
            t2 = _require_role(role_map, [InputRole.T2])
            # Align T2 to T1 spatial grid
            t2_aligned = align_to_reference(t2, t1)
            return {
                "image_t1": prepare_optical_tensor(t1, size),
                "image_t2": prepare_optical_tensor(t2_aligned, size),
            }

        if tool_key == "CHANGE_CAPTION":
            t1 = _require_role(role_map, [InputRole.T1])
            t2 = _require_role(role_map, [InputRole.T2])
            t2_aligned = align_to_reference(t2, t1)
            change_out = intermediate.get("CHANGE_DETECTION")
            change_mask = None
            if change_out and "change_mask" in change_out.value:
                change_mask = np.array(change_out.value["change_mask"])
            inp = {
                "image_t1": prepare_optical_tensor(t1, size),
                "image_t2": prepare_optical_tensor(t2_aligned, size),
            }
            if change_mask is not None:
                inp["change_mask"] = change_mask
            return inp

        if tool_key == "CHANGE_VQA":
            t1 = _require_role(role_map, [InputRole.T1])
            t2 = _require_role(role_map, [InputRole.T2])
            t2_aligned = align_to_reference(t2, t1)
            return {
                "image_t1": prepare_optical_tensor(t1, size),
                "image_t2": prepare_optical_tensor(t2_aligned, size),
                "question": query,
            }

        if tool_key == "OPTICAL_SAR_ANALYZER":
            opt = _require_role(role_map, [InputRole.OPTICAL])
            sar = _require_role(role_map, [InputRole.SAR])
            # Align SAR to optical grid
            sar_aligned = align_to_reference(sar, opt)
            # Use SAR preprocessed output if available
            sar_preprocess_out = intermediate.get("SAR_PREPROCESS")
            if sar_preprocess_out and "filtered_array" in sar_preprocess_out.value:
                sar_arr = np.array(sar_preprocess_out.value["filtered_array"])
                sar_arr = resize_array(sar_arr, size, size)
            else:
                sar_arr = prepare_sar_tensor(sar_aligned, size)
            opt_arr = prepare_optical_tensor(opt, size)
            # Denormalize optical for fusion model (expects [0,1])
            opt_arr = _denormalize_imagenet(opt_arr)
            return {
                "optical": opt_arr,
                "sar": sar_arr,
                "resolution_m": opt.metadata.get("resolution_m", 10.0),
            }

        if tool_key == "RS_EMBED":
            geo = _require_role(
                role_map,
                [InputRole.PRIMARY, InputRole.OPTICAL],
                modalities={InputModality.OPTICAL, InputModality.MULTISPECTRAL},
            )
            arr = prepare_optical_tensor(geo, size)
            arr = _denormalize_imagenet(arr)
            return {"image": arr, "text": query}

        raise ValueError(f"No input preparation defined for tool '{tool_key}'")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_role_map(plan: ExecutionPlan, geo_images: dict[str, GeoImage]) -> dict[InputRole, GeoImage]:
    role_map: dict[InputRole, GeoImage] = {}
    geo_by_path = {
        str(Path(geo.file_path).resolve()): geo
        for geo in geo_images.values()
    }
    for meta in plan.inputs:
        geo = geo_images.get(meta.input_id)
        if geo is None:
            geo = geo_by_path.get(str(Path(meta.file_path).resolve()))
        if geo is None:
            continue
        role_map[meta.role] = geo
        # PRIMARY is a semantic role; modality is a separate property of the
        # same image. Expose the modality as an alias for single-image tools.
        if meta.role == InputRole.PRIMARY and geo.modality in (
            InputModality.OPTICAL,
            InputModality.MULTISPECTRAL,
            InputModality.SAR,
        ):
            role_map[InputRole(geo.modality.value)] = geo
    return role_map


def _require_role(
    role_map: dict[InputRole, GeoImage],
    roles: list[InputRole],
    modalities: set[InputModality] | None = None,
) -> GeoImage:
    for role in roles:
        geo = role_map.get(role)
        if geo is not None and (modalities is None or geo.modality in modalities):
            return geo
    required = ", ".join(role.value for role in roles)
    if modalities:
        required += f" with modality {[modality.value for modality in modalities]}"
    raise ValueError(f"Required image role(s) {required} not found in inputs.")


def _denormalize_imagenet(array: np.ndarray) -> np.ndarray:
    """Reverse ImageNet normalization → [0, 1] range."""
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
    return np.clip(array * std + mean, 0.0, 1.0)
