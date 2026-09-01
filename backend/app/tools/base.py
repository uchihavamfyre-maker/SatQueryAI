"""
Base Tool Interface
Every specialist model in the registry must implement this interface.
The agentic controller only calls tools through this contract.
"""
from __future__ import annotations
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from app.models.schemas import OutputType, ToolOutput, ValidationStatus

if TYPE_CHECKING:
    from app.agent.registry import ToolDescriptor

logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self, status: ValidationStatus, notes: list[str] | None = None):
        self.status = status
        self.notes = notes or []

    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.PASSED

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(ValidationStatus.PASSED)

    @classmethod
    def fail(cls, reason: str) -> "ValidationResult":
        return cls(ValidationStatus.FAILED, [reason])

    @classmethod
    def warn(cls, reason: str) -> "ValidationResult":
        return cls(ValidationStatus.WARNING, [reason])


class BaseTool(ABC):
    """
    Standard interface for all SatQuery AI specialist tools.
    Subclasses implement validate_inputs, _run, and optionally load_model.
    """

    def __init__(self, descriptor: "ToolDescriptor"):
        self.descriptor = descriptor
        self.key = descriptor.key
        self._model_loaded = False
        self.logger = logging.getLogger(f"tool.{self.key}")

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def load_model(self) -> None:
        """
        Load model weights into memory. Called lazily on first use.
        Subclasses override this to load their specific model.
        """
        self._model_loaded = True

    def is_loaded(self) -> bool:
        return self._model_loaded

    def health_check(self) -> bool:
        """Return True if the tool is ready to accept requests."""
        try:
            if not self._model_loaded:
                self.load_model()
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    # ── Validation ────────────────────────────────────────────────────────────

    @abstractmethod
    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        """
        Validate that inputs conform to the tool's input_schema.
        Called before any preprocessing or model inference.
        """

    def _validate_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Enforce permitted_parameters. Strip unknown keys, apply defaults.
        The LLM may only set parameters listed in the registry.
        """
        permitted = {p["name"]: p for p in self.descriptor.permitted_parameters}
        validated = {}
        for name, spec in permitted.items():
            if name in params:
                value = params[name]
                # Range check for numeric types
                if "range" in spec and isinstance(value, (int, float)):
                    lo, hi = spec["range"]
                    value = max(lo, min(hi, value))
                # Choices check
                if "choices" in spec and value not in spec["choices"]:
                    value = spec.get("default")
                validated[name] = value
            else:
                validated[name] = spec.get("default")
        return validated

    # ── Execution ─────────────────────────────────────────────────────────────

    @abstractmethod
    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        """
        Core inference logic. Receives preprocessed inputs and validated params.
        Must return a ToolOutput.
        """

    def run(self, inputs: dict[str, Any], params: dict[str, Any] | None = None) -> ToolOutput:
        """
        Public entry point. Validates inputs, enforces parameters, times execution.
        """
        params = params or {}
        validated_params = self._validate_parameters(params)

        validation = self.validate_inputs(inputs)
        if not validation.passed:
            return ToolOutput(
                type=OutputType.TEXT,
                value={"error": "; ".join(validation.notes)},
                confidence=0.0,
                latency_ms=0,
            )

        if not self._model_loaded:
            self.load_model()

        t0 = time.perf_counter()
        try:
            output = self._run(inputs, validated_params)
        except Exception as e:
            self.logger.exception(f"Tool {self.key} failed: {e}")
            output = ToolOutput(
                type=OutputType.TEXT,
                value={"error": str(e)},
                confidence=0.0,
                latency_ms=0,
            )
        output.latency_ms = int((time.perf_counter() - t0) * 1000)
        self.logger.info(f"{self.key} completed in {output.latency_ms}ms, confidence={output.confidence:.3f}")
        return output

    # ── Stub fallback ─────────────────────────────────────────────────────────

    def _stub_output(self, message: str) -> ToolOutput:
        """
        Returns a clearly-labeled stub output when model weights are unavailable.
        Used during development before weights are downloaded.
        """
        return ToolOutput(
            type=OutputType.TEXT,
            value={
                "answer": f"[STUB — {self.descriptor.model_name} weights not loaded] {message}",
                "stub": True,
            },
            confidence=0.0,
            metadata={"model": self.descriptor.model_name, "status": "STUB"},
        )
