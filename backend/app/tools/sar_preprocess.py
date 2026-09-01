"""
SAR_PREPROCESS Tool — Classical SAR preprocessing (speckle filter + calibration).
RS_EMBED Tool — RemoteCLIP image-text embedding for RS imagery.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np

from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult
from app.preprocessing.geo_pipeline import normalize_sar

logger = logging.getLogger(__name__)


# ─── SAR Preprocessing ───────────────────────────────────────────────────────

class SARPreprocessTool(BaseTool):
    """
    Classical SAR preprocessing pipeline.
    No neural network — always available, no weights required.
    """

    def load_model(self) -> None:
        self._model_loaded = True  # No model to load

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        if "sar_array" not in inputs:
            return ValidationResult.fail("Missing 'sar_array' [C, H, W] float32")
        arr = inputs["sar_array"]
        if not isinstance(arr, np.ndarray) or arr.ndim != 3:
            return ValidationResult.fail("'sar_array' must be [C, H, W] float32")
        return ValidationResult.ok()

    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        sar = inputs["sar_array"].astype(np.float32)
        filter_type = params.get("filter_type", "lee")
        filter_size = params.get("filter_size", 7)

        processed = normalize_sar(sar, filter_type=filter_type, filter_size=filter_size)

        return ToolOutput(
            type=OutputType.MASK,  # reusing MASK type for array outputs
            value={"filtered_array": processed.tolist()},
            confidence=1.0,
            metadata={
                "filter_type": filter_type,
                "filter_size": filter_size,
                "input_shape": list(sar.shape),
                "output_range": [float(processed.min()), float(processed.max())],
            },
        )


# ─── RemoteCLIP Embedding ─────────────────────────────────────────────────────

class RSEmbedTool(BaseTool):
    """
    RemoteCLIP: CLIP model fine-tuned on RS5M remote-sensing dataset.
    Provides RS-adapted image and text embeddings.
    Used for query routing, evidence scoring, and zero-shot classification.
    """

    def __init__(self, descriptor):
        super().__init__(descriptor)
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = "cpu"

    def load_model(self) -> None:
        from app.config import settings
        weights_path = settings.models_dir / "remoteclip"
        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            # RemoteCLIP is available on HuggingFace: chendelong/RemoteCLIP
            model_id = str(weights_path) if weights_path.exists() else "chendelong/RemoteCLIP"
            from transformers import CLIPModel, CLIPProcessor
            self._model = CLIPModel.from_pretrained(model_id).to(self._device)
            self._preprocess = CLIPProcessor.from_pretrained(model_id)
            self._model.eval()
            self._model_loaded = True
            self.logger.info("RemoteCLIP loaded")
        except Exception as e:
            self.logger.warning(f"RemoteCLIP not available ({e}). BASELINE FALLBACK mode.")
            self._model_loaded = True

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        if "image" not in inputs and "text" not in inputs:
            return ValidationResult.fail("At least one of 'image' or 'text' must be provided")
        return ValidationResult.ok()

    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        if self._model is None:
            # Transparent, deterministic fallback: compact color/texture embedding.
            # This is not claimed to be RemoteCLIP and is marked BASELINE.
            arr = np.asarray(inputs.get("image"), dtype=np.float32) if "image" in inputs else None
            if arr is None:
                return ToolOutput(
                    type=OutputType.EMBEDDING,
                    value={},
                    confidence=0.0,
                    metadata={"model": "RemoteSensingStatisticalEmbedding", "status": "BASELINE", "note": "Image input required for baseline embedding."},
                )
            if arr.ndim != 3:
                raise ValueError("image must be [C,H,W]")
            x = np.clip(arr, 0.0, 1.0)
            parts = []
            for c in range(min(x.shape[0], 3)):
                band = x[c]
                parts.extend([float(band.mean()), float(band.std()), *np.percentile(band, [5, 25, 50, 75, 95]).astype(float).tolist()])
            while len(parts) < 21:
                parts.append(0.0)
            emb = np.asarray(parts[:21], dtype=np.float32)
            emb = emb / max(float(np.linalg.norm(emb)), 1e-8)
            result = {"image_embedding": emb.tolist()}
            if "text" in inputs:
                # Text is intentionally not embedded by the baseline.
                result["text_embedding"] = None
            return ToolOutput(
                type=OutputType.EMBEDDING,
                value=result,
                confidence=0.45,
                metadata={"model": "RemoteSensingStatisticalEmbedding", "status": "BASELINE", "note": "Install chendelong/RemoteCLIP for RS-adapted embeddings."},
            )

        import torch
        from PIL import Image as PILImage

        result = {}

        if "image" in inputs:
            arr = inputs["image"]  # [3, H, W] float32 [0,1]
            pil_img = _array_to_pil(arr)
            enc = self._preprocess(images=pil_img, return_tensors="pt").to(self._device)
            with torch.no_grad():
                img_emb = self._model.get_image_features(**enc)
                img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
            result["image_embedding"] = img_emb.squeeze(0).cpu().numpy().tolist()

        if "text" in inputs:
            enc = self._preprocess(text=inputs["text"], return_tensors="pt", padding=True).to(self._device)
            with torch.no_grad():
                txt_emb = self._model.get_text_features(**enc)
                txt_emb = txt_emb / txt_emb.norm(dim=-1, keepdim=True)
            result["text_embedding"] = txt_emb.squeeze(0).cpu().numpy().tolist()

        if "image_embedding" in result and "text_embedding" in result:
            import numpy as np
            sim = float(np.dot(result["image_embedding"], result["text_embedding"]))
            result["similarity"] = sim

        return ToolOutput(
            type=OutputType.EMBEDDING,
            value=result,
            confidence=1.0,
            metadata={"model": "RemoteCLIP"},
        )


def _array_to_pil(array: np.ndarray):
    from PIL import Image as PILImage
    rgb = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    return PILImage.fromarray(np.transpose(rgb, (1, 2, 0)), mode="RGB")
