"""Remote-sensing grounding via official GeoChat plus a deterministic fallback."""
from __future__ import annotations
import logging,re
from typing import Any
import numpy as np
from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult
logger=logging.getLogger(__name__)
class RSGroundingTool(BaseTool):
    def __init__(self,descriptor): super().__init__(descriptor)
    def load_model(self): self._model_loaded=True
    def validate_inputs(self,inputs):
        for k in ('image','query'):
            if k not in inputs:return ValidationResult.fail(f"Missing '{k}'")
        return ValidationResult.ok()
    def _run(self,inputs,params):
        from app.config import settings
        try:
            from app.tools.research_vlm import geochat
            raw=geochat(settings.models_dir/'geochat',inputs['image'],'Locate and ground '+inputs['query']+'. Return object locations as [x1,y1,x2,y2] normalized to 0..1.','grounding',256)
            boxes=_parse(raw,inputs['image'].shape[2],inputs['image'].shape[1],params.get('confidence_threshold',.3),inputs['query'])
            if boxes:
                return ToolOutput(type=OutputType.BBOX,value={'bboxes':boxes,'query':inputs['query']},confidence=float(np.mean([b['score'] for b in boxes])),metadata={'model':'GeoChat-7B','status':'REAL_MODEL','raw_output':raw[:500]})
            raise RuntimeError('GeoChat returned no parseable bounding boxes')
        except Exception as e:
            from app.tools.classical_baselines import grounding
            boxes=grounding(inputs['image'],inputs['query'])
            return ToolOutput(type=OutputType.BBOX,value={'bboxes':boxes,'query':inputs['query']},confidence=float(np.mean([b['score'] for b in boxes])) if boxes else .45,metadata={'model':'ColorSemanticGroundingBaseline','status':'BASELINE','fallback_reason':str(e)[:500]})
def _parse(text,w,h,threshold,label):
    out=[]
    for m in re.findall(r'\[?\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\]?',text):
        vals=list(map(float,m));
        if max(vals)<=1: vals=[vals[0]*w,vals[1]*h,vals[2]*w,vals[3]*h]
        x1,y1,x2,y2=vals
        if x2>x1 and y2>y1: out.append({'x1':x1,'y1':y1,'x2':x2,'y2':y2,'score':.72,'label':label[:80]})
    return out
