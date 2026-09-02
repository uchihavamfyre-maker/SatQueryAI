"""
RS_VQA Tool — Remote Sensing Visual Question Answering
Wraps RSVQA-HR (fine-tuned on BigEarthNet-derived QA pairs).
Falls back to a transparent remote-sensing heuristic baseline when weights are unavailable.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult

logger = logging.getLogger(__name__)


class RSVQATool(BaseTool):
    """
    RSVQA-HR model for single-image remote-sensing VQA.
    Architecture: dual-encoder (ResNet visual + BERT text) with classification head.
    Fine-tuned on RSVQA-HR dataset + BigEarthNet-derived QA pairs.
    """

    def __init__(self, descriptor):
        super().__init__(descriptor)
        self._model = None
        self._tokenizer = None
        self._feature_extractor = None
        self._answer_vocab: list[str] = []
        self._backend = "classification"
        self._pg_model = None
        self._pg_processor = None
        self._device = "cpu"

    def load_model(self) -> None:
        """
        Load RSVQA-HR weights from HuggingFace or local path.
        Model: visual encoder (ResNet-50) + text encoder (BERT-base) + MLP classifier.
        """
        from app.config import settings
        weights_path = settings.models_dir / "rsvqa_hr"

        try:
            import torch
            from transformers import BertTokenizer, BertModel
            import torchvision.models as tv_models

            self.logger.info("Loading RSVQA-HR model...")

            # Preferred production path: Google's PaliGemma RSVQA-HR checkpoint.
            # It is explicitly fine-tuned on RSVQA-HR (224px) and gives a real
            # generative VQA model instead of a randomly initialized classifier.
            import os
            # Keep the free deployment fast; heavyweight VLM loading is opt-in.
            if os.getenv("RSVQA_BACKEND", "baseline").lower() == "paligemma":
                try:
                    from transformers import AutoProcessor, PaliGemmaForConditionalGeneration
                    model_id = os.getenv("RSVQA_MODEL_ID", "google/paligemma-3b-ft-rsvqa-hr-224")
                    device = _get_device()
                    dtype = torch.float16 if device == "cuda" else torch.float32
                    self._pg_processor = AutoProcessor.from_pretrained(model_id)
                    self._pg_model = PaliGemmaForConditionalGeneration.from_pretrained(
                        model_id, torch_dtype=dtype, device_map=device
                    ).eval()
                    self._device = device
                    self._backend = "paligemma"
                    self._model_loaded = True
                    self.logger.info("PaliGemma RSVQA-HR loaded: %s", model_id)
                    return
                except Exception as e:
                    self.logger.warning("PaliGemma RSVQA-HR unavailable: %s", e)

            # Check for local fine-tuned weights first
            checkpoint_path = weights_path / "rsvqa_hr_finetuned.pth"
            if not checkpoint_path.exists():
                self.logger.warning(
                    f"RSVQA-HR weights not found at {checkpoint_path}. "
                    "Running in BASELINE FALLBACK mode. Download weights and place at the path above."
                )
                self._model_loaded = True  # Baseline fallback is intentionally explicit
                return

            self._tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
            checkpoint = torch.load(checkpoint_path, map_location="cpu")
            self._answer_vocab = checkpoint.get("answer_vocab", [])

            # Build model architecture matching the checkpoint
            self._model = _RSVQAModel(
                num_answers=len(self._answer_vocab),
                visual_backbone="resnet50",
            )
            self._model.load_state_dict(checkpoint["model_state_dict"])
            self._model.eval()

            device = _get_device()
            self._model = self._model.to(device)
            self._device = device
            self._model_loaded = True
            self.logger.info("RSVQA-HR loaded successfully")

        except ImportError as e:
            self.logger.error(f"Missing dependency: {e}")
            self._model_loaded = True  # Baseline mode

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        if "image" not in inputs:
            return ValidationResult.fail("Missing required input: 'image'")
        if "question" not in inputs:
            return ValidationResult.fail("Missing required input: 'question'")
        img = inputs["image"]
        if not isinstance(img, np.ndarray) or img.ndim != 3:
            return ValidationResult.fail("'image' must be a 3D numpy array [C, H, W]")
        if len(inputs["question"].strip()) == 0:
            return ValidationResult.fail("'question' must not be empty")
        return ValidationResult.ok()

    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        import os
        if self._model is None and self._pg_model is None:
            from app.tools.classical_baselines import answer_vqa
            answer, confidence = answer_vqa(inputs["image"], inputs["question"])
            return ToolOutput(type=OutputType.TEXT, value={"answer": answer}, confidence=confidence,
                              metadata={"model":"RemoteSensingHeuristicVQA", "status":"BASELINE"})

        import torch

        if self._backend == "paligemma" and self._pg_model is not None:
            from PIL import Image
            arr = inputs["image"]
            # Dispatcher provides ImageNet-normalized CHW; undo it for the processor.
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
            arr = np.clip(arr * std + mean, 0, 1)
            hwc = (np.transpose(arr, (1, 2, 0)) * 255).astype(np.uint8)
            image = Image.fromarray(hwc, mode="RGB")
            question = inputs["question"].strip()
            prompt = f"answer en {question}"
            model_inputs = self._pg_processor(text=prompt, images=image, return_tensors="pt")
            model_inputs = {k: v.to(self._pg_model.device) if hasattr(v, "to") else v for k, v in model_inputs.items()}
            input_len = model_inputs["input_ids"].shape[-1]
            with torch.inference_mode():
                generated = self._pg_model.generate(**model_inputs, max_new_tokens=int(params.get("max_answer_length", 32)), do_sample=False)
            answer = self._pg_processor.decode(generated[0][input_len:], skip_special_tokens=True).strip()
            return ToolOutput(
                type=OutputType.TEXT,
                value={"answer": answer, "top_answers": [{"answer": answer, "score": 1.0}]},
                confidence=0.92,
                metadata={"model": os.getenv("RSVQA_MODEL_ID", "google/paligemma-3b-ft-rsvqa-hr-224"), "status": "PRETRAINED_RS_VQA"},
            )

        image_array = inputs["image"]  # [3, H, W] float32, ImageNet-normalized
        question = inputs["question"]
        top_k = params.get("top_k", 1)

        # Tokenize question
        encoding = self._tokenizer(
            question,
            return_tensors="pt",
            max_length=64,
            padding="max_length",
            truncation=True,
        )
        input_ids = encoding["input_ids"].to(self._device)
        attention_mask = encoding["attention_mask"].to(self._device)

        # Prepare image tensor
        img_tensor = torch.from_numpy(image_array).unsqueeze(0).to(self._device)

        with torch.no_grad():
            logits = self._model(img_tensor, input_ids, attention_mask)
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()

        top_indices = np.argsort(probs)[::-1][:top_k]
        top_answers = [
            {"answer": self._answer_vocab[i], "score": float(probs[i])}
            for i in top_indices
            if i < len(self._answer_vocab)
        ]

        return ToolOutput(
            type=OutputType.TEXT,
            value={
                "answer": top_answers[0]["answer"] if top_answers else "unknown",
                "top_answers": top_answers,
            },
            confidence=float(top_answers[0]["score"]) if top_answers else 0.0,
            metadata={"model": "RSVQA-HR", "question": question},
        )


# ─── Model Architecture ───────────────────────────────────────────────────────

class _RSVQAModel:
    """
    RSVQA dual-encoder architecture.
    Visual: ResNet-50 → 2048-d feature
    Text: BERT-base [CLS] → 768-d feature
    Fusion: concat → MLP → num_answers
    """
    def __new__(cls, num_answers: int, visual_backbone: str = "resnet50"):
        import torch.nn as nn
        import torchvision.models as tv_models

        class _Model(nn.Module):
            def __init__(self):
                super().__init__()
                backbone = tv_models.resnet50(weights=None)
                self.visual_encoder = nn.Sequential(*list(backbone.children())[:-1])  # → [B, 2048, 1, 1]
                from transformers import BertModel
                self.text_encoder = BertModel.from_pretrained("bert-base-uncased")
                self.classifier = nn.Sequential(
                    nn.Linear(2048 + 768, 1024),
                    nn.ReLU(),
                    nn.Dropout(0.3),
                    nn.Linear(1024, num_answers),
                )

            def forward(self, image, input_ids, attention_mask):
                import torch
                vis = self.visual_encoder(image).squeeze(-1).squeeze(-1)  # [B, 2048]
                txt = self.text_encoder(input_ids=input_ids, attention_mask=attention_mask)
                txt_feat = txt.last_hidden_state[:, 0, :]  # [CLS] token → [B, 768]
                fused = torch.cat([vis, txt_feat], dim=1)
                return self.classifier(fused)

        return _Model()


def _get_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
