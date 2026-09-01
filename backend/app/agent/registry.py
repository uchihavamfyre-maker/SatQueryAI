"""
Model / Tool Registry
Loads registry.yaml at startup. The agentic controller queries this registry
to discover available tools. The LLM receives the registry schema in its
system prompt and may only select tools listed here.
"""
from __future__ import annotations
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ToolDescriptor:
    key: str
    display_name: str
    model_name: str
    model_version: str
    fine_tuned: bool
    fine_tune_dataset: str | None
    task: str
    input_modalities: list[str]
    input_formats: list[str]
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    permitted_parameters: list[dict[str, Any]]
    compute: str
    interface_class: str
    enabled: bool
    verification_status: str
    weights_url: str | None
    raw: dict[str, Any] = field(default_factory=dict)

    def permitted_param_names(self) -> list[str]:
        return [p["name"] for p in self.permitted_parameters]

    def default_parameters(self) -> dict[str, Any]:
        return {p["name"]: p.get("default") for p in self.permitted_parameters}

    def to_agent_summary(self) -> dict[str, Any]:
        """Compact representation sent to the LLM in its system prompt."""
        return {
            "key": self.key,
            "display_name": self.display_name,
            "task": self.task,
            "input_modalities": self.input_modalities,
            "input_formats": self.input_formats,
            "output_types": list(self.output_schema.keys()),
            "permitted_parameters": self.permitted_param_names(),
            "enabled": self.enabled,
            "verification_status": self.verification_status,
        }


class ModelRegistry:
    def __init__(self, registry_path: Path):
        self._path = registry_path
        self._tools: dict[str, ToolDescriptor] = {}
        self._load()

    def _load(self) -> None:
        with open(self._path, "r") as f:
            data = yaml.safe_load(f)
        for entry in data.get("tools", []):
            desc = ToolDescriptor(
                key=entry["key"],
                display_name=entry["display_name"],
                model_name=entry["model_name"],
                model_version=entry["model_version"],
                fine_tuned=entry.get("fine_tuned", False),
                fine_tune_dataset=entry.get("fine_tune_dataset"),
                task=entry["task"],
                input_modalities=entry.get("input_modalities", []),
                input_formats=entry.get("input_formats", []),
                input_schema=entry.get("input_schema", {}),
                output_schema=entry.get("output_schema", {}),
                permitted_parameters=entry.get("permitted_parameters", []),
                compute=entry.get("compute", ""),
                interface_class=entry["interface_class"],
                enabled=entry.get("enabled", True),
                verification_status=entry.get("verification_status", "UNKNOWN"),
                weights_url=entry.get("weights_url"),
                raw=entry,
            )
            self._tools[desc.key] = desc
        logger.info(f"Registry loaded: {len(self._tools)} tools")

    def get(self, key: str) -> ToolDescriptor:
        if key not in self._tools:
            raise KeyError(f"Tool '{key}' not found in registry")
        return self._tools[key]

    def all_enabled(self) -> list[ToolDescriptor]:
        return [t for t in self._tools.values() if t.enabled]

    def keys(self) -> list[str]:
        return list(self._tools.keys())

    def agent_summary(self) -> list[dict[str, Any]]:
        """Full registry summary for LLM system prompt."""
        return [t.to_agent_summary() for t in self.all_enabled()]


    def status(self) -> list[dict[str, Any]]:
        """Return deployment-facing metadata without instantiating heavyweight models."""
        from app.config import settings
        out = []
        for t in self.all_enabled():
            out.append({
                "key": t.key,
                "model": t.model_name,
                "task": t.task,
                "verification_status": t.verification_status,
                "weights_url": t.weights_url,
                "compute": t.compute,
                "configured": _tool_configured(t, settings.models_dir),
            })
        return out

    def instantiate_tool(self, key: str) -> "BaseTool":
        """Dynamically import and instantiate the tool class for a registry key."""
        desc = self.get(key)
        module_path, class_name = desc.interface_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(descriptor=desc)


# Singleton — loaded once at startup
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        from app.config import settings
        _registry = ModelRegistry(settings.registry_path)
    return _registry


def _tool_configured(desc: ToolDescriptor, models_dir: Path) -> bool:
    key = desc.key
    if key == "RS_VQA":
        import os
        return bool(os.getenv("RSVQA_MODEL_ID")) or (models_dir / "rsvqa_hr").exists()
    if key in {"RS_CAPTION", "RS_GROUNDING"}:
        return (models_dir / "geochat" / "official").exists() and (models_dir / "geochat" / "weights").exists()
    if key == "CHANGE_DETECTION":
        return (models_dir / "changeformer" / "official").exists()
    if key in {"CHANGE_CAPTION", "CHANGE_VQA"}:
        return (models_dir / "deltavlm" / "official").exists() and (models_dir / "deltavlm" / "pretrained").exists()
    if key == "RS_EMBED":
        return (models_dir / "remoteclip").exists()
    return True
