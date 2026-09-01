"""Bi-temporal change captioning via official DeltaVLM."""
from __future__ import annotations
from typing import Any
import numpy as np
from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult
class ChangeVLPTool(BaseTool):
    def __init__(self,descriptor): super().__init__(descriptor)
    def load_model(self): self._model_loaded=True
    def validate_inputs(self,inputs):
        for k in ('image_t1','image_t2'):
            if k not in inputs:return ValidationResult.fail(f"Missing '{k}'")
        return ValidationResult.ok()
    def _run(self,inputs,params):
        from app.config import settings
        prompt='Describe the meaningful changes between the pre-event and post-event remote-sensing images. Mention what changed and where, without inventing details.'
        try:
            from app.tools.research_vlm import deltavlm
            text=deltavlm(settings.models_dir/'deltavlm',inputs['image_t1'],inputs['image_t2'],prompt)
            return ToolOutput(type=OutputType.TEXT,value={'caption':text},confidence=.80,metadata={'model':'DeltaVLM','status':'REAL_MODEL'})
        except Exception as e:
            from app.tools.classical_baselines import change_caption
            mask=inputs.get('change_mask'); mask=np.asarray(mask) if mask is not None else None
            text,conf=change_caption(inputs['image_t1'],inputs['image_t2'],mask)
            return ToolOutput(type=OutputType.TEXT,value={'caption':text},confidence=conf,metadata={'model':'ClassicalChangeBaseline','status':'BASELINE','fallback_reason':str(e)[:500]})
