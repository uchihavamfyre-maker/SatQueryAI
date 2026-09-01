"""Remote-sensing captioning via official GeoChat, with transparent baseline fallback."""
from __future__ import annotations
import logging
from typing import Any
import numpy as np
from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult

logger=logging.getLogger(__name__)
_CAPTION_PROMPT='Describe this remote-sensing scene. Identify major land-cover types, structures, roads, water, vegetation and other visible features. Be concise and evidence-based.'

def _array_to_pil(array: np.ndarray):
    from PIL import Image
    x=np.asarray(array,np.float32)
    if x.shape[0]>3: x=x[:3]
    if x.shape[0]==1: x=np.repeat(x,3,axis=0)
    elif x.shape[0]==2: x=np.stack([x[0],x[1],x[0]],axis=0)
    x=np.transpose(x,(1,2,0)); vals=x[np.isfinite(x)]
    lo,hi=np.percentile(vals,[2,98]) if vals.size else (0,1)
    x=np.clip((x-lo)/max(float(hi-lo),1e-6),0,1)
    return Image.fromarray((x*255).astype(np.uint8),'RGB')

class RSCaptionTool(BaseTool):
    def __init__(self,descriptor): super().__init__(descriptor)
    def load_model(self): self._model_loaded=True
    def validate_inputs(self,inputs:dict[str,Any])->ValidationResult:
        if 'image' not in inputs:return ValidationResult.fail("Missing 'image'")
        if not isinstance(inputs['image'],np.ndarray) or inputs['image'].ndim!=3:return ValidationResult.fail("'image' must be CHW")
        return ValidationResult.ok()
    def _run(self,inputs,params):
        from app.config import settings
        try:
            from app.tools.research_vlm import geochat
            text=geochat(settings.models_dir/'geochat',inputs['image'],inputs.get('prompt',_CAPTION_PROMPT),'caption',params.get('max_new_tokens',256))
            return ToolOutput(type=OutputType.TEXT,value={'caption':text},confidence=.82,metadata={'model':'GeoChat-7B','status':'REAL_MODEL'})
        except Exception as e:
            from app.tools.classical_baselines import scene_caption
            text=scene_caption(inputs['image'])
            return ToolOutput(type=OutputType.TEXT,value={'caption':text},confidence=.58,metadata={'model':'RemoteSensingSceneBaseline','status':'BASELINE','fallback_reason':str(e)[:500]})
