"""Bi-temporal change VQA using DeltaVLM; CDVQA remains a benchmark/data source."""
from __future__ import annotations
from typing import Any
import numpy as np
from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult
class CDVQATool(BaseTool):
    def __init__(self,descriptor): super().__init__(descriptor)
    def load_model(self): self._model_loaded=True
    def validate_inputs(self,inputs):
        for k in ('image_t1','image_t2','question'):
            if k not in inputs:return ValidationResult.fail(f"Missing '{k}'")
        return ValidationResult.ok()
    def _run(self,inputs,params):
        from app.config import settings
        try:
            from app.tools.research_vlm import deltavlm
            text=deltavlm(settings.models_dir/'deltavlm',inputs['image_t1'],inputs['image_t2'],inputs['question'])
            return ToolOutput(type=OutputType.TEXT,value={'answer':text},confidence=.80,metadata={'model':'DeltaVLM','status':'REAL_MODEL','benchmark_family':'CDVQA'})
        except Exception as e:
            from app.tools.classical_baselines import change_vqa
            mask=inputs.get('change_mask'); mask=np.asarray(mask) if mask is not None else None
            answer,conf=change_vqa(inputs['image_t1'],inputs['image_t2'],inputs['question'],mask)
            return ToolOutput(type=OutputType.TEXT,value={'answer':answer},confidence=conf,metadata={'model':'ClassicalChangeVQABaseline','status':'BASELINE','fallback_reason':str(e)[:500]})
