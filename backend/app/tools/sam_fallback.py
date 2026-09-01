"""
SAM Fallback Tool — Segment Anything Model for mask refinement.
Takes bounding boxes from RS_GROUNDING and produces pixel-level masks.
Uses SAM-ViT-B for student hardware compatibility.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np
import cv2

from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult

logger = logging.getLogger(__name__)

SAM_CHECKPOINT_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"


class SAMFallbackTool(BaseTool):

    def __init__(self, descriptor):
        super().__init__(descriptor)
        self._predictor = None

    def load_model(self) -> None:
        from app.config import settings
        checkpoint = settings.models_dir / "sam" / "sam_vit_b_01ec64.pth"
        try:
            from segment_anything import sam_model_registry, SamPredictor
            import torch
            if not checkpoint.exists():
                self.logger.warning(
                    f"SAM weights not found at {checkpoint}. "
                    f"Download from: {SAM_CHECKPOINT_URL}"
                )
                self._model_loaded = True
                return
            sam = sam_model_registry["vit_b"](checkpoint=str(checkpoint))
            device = "cuda" if torch.cuda.is_available() else "cpu"
            sam.to(device)
            self._predictor = SamPredictor(sam)
            self._model_loaded = True
            self.logger.info("SAM-ViT-B loaded")
        except ImportError:
            self.logger.warning("segment_anything not installed. pip install segment-anything")
            self._model_loaded = True

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        if "image" not in inputs:
            return ValidationResult.fail("Missing 'image' (uint8 [H,W,3])")
        if "boxes" not in inputs or not inputs["boxes"]:
            return ValidationResult.fail("Missing 'boxes' — list of {x1,y1,x2,y2}")
        return ValidationResult.ok()

    def _run(self, inputs: dict[str, Any], params: dict[str, Any]) -> ToolOutput:
        if self._predictor is None:
            # Real classical refinement: GrabCut initialized from each grounding box.
            image_hw3 = inputs["image"]
            masks_out, scores_out = [], []
            h, w = image_hw3.shape[:2]
            for box in inputs["boxes"]:
                x1,y1,x2,y2=[int(max(0,v)) for v in (box["x1"],box["y1"],box["x2"],box["y2"])]
                x2=min(w-1,x2); y2=min(h-1,y2)
                if x2<=x1 or y2<=y1: continue
                rect=(x1,y1,x2-x1,y2-y1)
                gc=np.zeros((h,w),np.uint8); bgd=np.zeros((1,65),np.float64); fgd=np.zeros((1,65),np.float64)
                try:
                    cv2.grabCut(image_hw3, gc, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
                    mask=np.where((gc==2)|(gc==0),0,1).astype(bool)
                except Exception:
                    mask=np.zeros((h,w),bool); mask[y1:y2,x1:x2]=True
                masks_out.append(mask.tolist()); scores_out.append(float(min(.9,max(.45,box.get("score",.5)))))
            return ToolOutput(type=OutputType.MASK, value={"masks":masks_out,"scores":scores_out},
                              confidence=float(np.mean(scores_out)) if scores_out else .45,
                              metadata={"model":"GrabCutGroundingRefiner", "status":"BASELINE"})

        import torch
        image_hw3 = inputs["image"]  # uint8 [H, W, 3]
        boxes = inputs["boxes"]

        self._predictor.set_image(image_hw3)
        masks_out = []
        scores_out = []

        for box in boxes:
            box_arr = np.array([[box["x1"], box["y1"], box["x2"], box["y2"]]])
            box_tensor = torch.tensor(box_arr, device=self._predictor.device)
            transformed_box = self._predictor.transform.apply_boxes_torch(
                box_tensor, image_hw3.shape[:2]
            )
            masks, scores, _ = self._predictor.predict_torch(
                point_coords=None,
                point_labels=None,
                boxes=transformed_box,
                multimask_output=params.get("multimask_output", False),
            )
            best_idx = scores.argmax().item()
            masks_out.append(masks[0, best_idx].cpu().numpy().astype(bool))
            scores_out.append(float(scores[0, best_idx].cpu()))

        return ToolOutput(
            type=OutputType.MASK,
            value={
                "masks": [m.tolist() for m in masks_out],  # serializable
                "scores": scores_out,
            },
            confidence=float(np.mean(scores_out)) if scores_out else 0.0,
            metadata={"model": "SAM-ViT-B", "num_masks": len(masks_out)},
        )
