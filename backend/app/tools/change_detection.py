"""
CHANGE_DETECTION Tool — ChangeFormer Bi-Temporal Change Detection
Siamese Transformer architecture trained on LEVIR-CD and WHU-CD.
Produces binary change mask + probability map.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np

from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult

logger = logging.getLogger(__name__)


class ChangeDetectionTool(BaseTool):

    def __init__(self, descriptor):
        super().__init__(descriptor)
        self._model = None
        self._device = "cpu"

    def load_model(self) -> None:
        from app.config import settings
        weights_path = settings.models_dir / "changeformer" / "changeformer_levir.pth"
        official_repo = settings.models_dir / "changeformer" / "official"
        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

            # Prefer the official ChangeFormerV6 implementation/checkpoint.
            try:
                from app.tools.changeformer_official import OfficialChangeFormer, discover_checkpoint
                checkpoint = weights_path if weights_path.exists() else discover_checkpoint(official_repo)
                if official_repo.exists() and checkpoint is not None:
                    self._model = OfficialChangeFormer(official_repo, checkpoint, self._device)
                    self._model.load()
                    self._model_loaded = True
                    self.logger.info("Official ChangeFormerV6 loaded from %s", checkpoint)
                    return
            except Exception as e:
                self.logger.warning("Official ChangeFormer adapter unavailable: %s", e)

            if not weights_path.exists():
                self.logger.warning(
                    f"ChangeFormer weights not found at {weights_path}. "
                    "Clone https://github.com/wgcban/ChangeFormer and place weights there."
                )
                self._model_loaded = True
                return

            self._model = _build_changeformer()
            state = torch.load(weights_path, map_location=self._device)
            self._model.load_state_dict(state.get("model", state))
            self._model.eval()
            self._model = self._model.to(self._device)
            self._model_loaded = True
            self.logger.info("ChangeFormer loaded")
        except Exception as e:
            self.logger.warning(f"ChangeFormer load failed ({e}). BASELINE FALLBACK mode.")
            self._model_loaded = True

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        for key in ("image_t1", "image_t2"):
            if key not in inputs:
                return ValidationResult.fail(f"Missing '{key}'")
            arr = inputs[key]
            if not isinstance(arr, np.ndarray) or arr.ndim != 3:
                return ValidationResult.fail(f"'{key}' must be [C, H, W] float32")
        t1, t2 = inputs["image_t1"], inputs["image_t2"]
        if t1.shape != t2.shape:
            return ValidationResult.fail(
                f"T1 shape {t1.shape} != T2 shape {t2.shape}. Images must be spatially aligned."
            )
        return ValidationResult.ok()

    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        if self._model is None:
            from app.tools.classical_baselines import change_mask
            mask, prob, confidence = change_mask(inputs["image_t1"], inputs["image_t2"], params.get("threshold", 0.5))
            return ToolOutput(
                type=OutputType.MASK,
                value={"change_mask": mask.tolist(), "change_prob": prob.tolist(),
                       "change_ratio": float(mask.mean()), "threshold_used": params.get("threshold", 0.5)},
                confidence=confidence,
                metadata={"model": "ClassicalChangeBaseline", "status": "BASELINE",
                          "note": "Real pixel-difference + morphology baseline; replace with trained ChangeFormer for benchmark scores."},
            )

        import torch
        threshold = params.get("threshold", 0.5)

        if hasattr(self._model, "predict"):
            # Official ChangeFormer expects normalized RGB tensors.
            prob = self._model.predict(inputs["image_t1"], inputs["image_t2"])
            change_mask = (prob >= threshold).astype(np.uint8)
            change_ratio = float(change_mask.mean())
            confidence = float(np.mean(np.maximum(prob, 1.0 - prob)))
            return ToolOutput(
                type=OutputType.MASK,
                value={"change_mask": change_mask.tolist(), "change_prob": prob.tolist(),
                       "change_ratio": change_ratio, "threshold_used": threshold},
                confidence=confidence,
                metadata={"model": "ChangeFormerV6", "status": "OFFICIAL_PRETRAINED",
                          "checkpoint": str(self._model.checkpoint)},
            )
        t1 = torch.from_numpy(inputs["image_t1"]).unsqueeze(0).to(self._device)
        t2 = torch.from_numpy(inputs["image_t2"]).unsqueeze(0).to(self._device)

        with torch.no_grad():
            pred = self._model(t1, t2)  # [B, 2, H, W] logits
            prob = torch.softmax(pred, dim=1)[:, 1, :, :].squeeze(0).cpu().numpy()

        change_mask = (prob >= threshold).astype(np.uint8)
        change_ratio = float(change_mask.sum()) / change_mask.size
        confidence = float(np.mean(prob[change_mask == 1])) if change_mask.sum() > 0 else 0.0

        return ToolOutput(
            type=OutputType.MASK,
            value={
                "change_mask": change_mask.tolist(),
                "change_prob": prob.tolist(),
                "change_ratio": change_ratio,
                "threshold_used": threshold,
            },
            confidence=confidence,
            metadata={"model": "ChangeFormer", "changed_pixels": int(change_mask.sum())},
        )


