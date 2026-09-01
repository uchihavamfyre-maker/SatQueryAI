"""Lightweight, genuinely trainable optical+SAR fusion model for SatQuery.

The default model is intentionally small enough for free Colab/Kaggle sessions and
CPU development. It accepts Sentinel-2 RGB/NIR (3 channels selected by preprocessing)
and Sentinel-1 VV/VH (2 channels), fuses both streams at multiple resolutions and
returns a 5-class segmentation map.
"""
from __future__ import annotations
import logging
from typing import Any
import numpy as np
from app.models.schemas import OutputType, ToolOutput
from app.tools.base import BaseTool, ValidationResult
logger = logging.getLogger(__name__)
CLASSES = ["built_up", "water", "vegetation", "bare_soil", "other"]
_DEFAULT_RESOLUTION_M = 10.0

class OpticalSARTool(BaseTool):
    def __init__(self, descriptor):
        super().__init__(descriptor); self._model=None; self._device="cpu"
    def load_model(self):
        from app.config import settings
        import torch
        self._device="cuda" if torch.cuda.is_available() else "cpu"
        weights=settings.models_dir/"optical_sar_fusion"/"dual_encoder_fused.pth"
        try:
            if weights.exists():
                self._model=DualEncoderFusion(num_classes=len(CLASSES))
                state=torch.load(weights,map_location=self._device)
                self._model.load_state_dict(state.get("model_state_dict",state),strict=True)
                self._model.to(self._device).eval(); self._model_loaded=True
                self.logger.info("Lightweight DualEncoderFusion loaded")
                return
        except Exception as e:
            self.logger.warning("Optical/SAR checkpoint unavailable: %s",e)
        self._model_loaded=True
    def validate_inputs(self,inputs:dict[str,Any])->ValidationResult:
        for k in ("optical","sar"):
            if k not in inputs or not isinstance(inputs[k],np.ndarray) or inputs[k].ndim!=3:
                return ValidationResult.fail(f"Missing/invalid '{k}' [C,H,W]")
        if inputs["optical"].shape[1:]!=inputs["sar"].shape[1:]:
            return ValidationResult.fail("Optical and SAR must be co-registered")
        return ValidationResult.ok()
    def _run(self,inputs,params):
        resolution_m=float(inputs.get("resolution_m",_DEFAULT_RESOLUTION_M))
        if self._model is None:
            from app.tools.classical_baselines import multisource_segmentation
            seg,probs,fractions,conf=multisource_segmentation(inputs["optical"],inputs["sar"])
            px=(resolution_m/1000)**2
            areas={k:round(v*seg.size*px,4) for k,v in fractions.items()}
            return ToolOutput(type=OutputType.SEGMENTATION,value={"segmentation_mask":seg.tolist(),"class_probs":probs.tolist(),"class_areas_km2":areas,"classes":CLASSES},confidence=float(conf),metadata={"model":"OpticalSARClassicalFusionBaseline","status":"BASELINE"})
        import torch
        import torch.nn.functional as F
        opt=_to_three_channels(inputs["optical"]); sar=_to_two_channels(inputs["sar"])
        with torch.no_grad():
            logits=self._model(torch.from_numpy(opt).unsqueeze(0).to(self._device),torch.from_numpy(sar).unsqueeze(0).to(self._device))
            probs=F.softmax(logits,dim=1).squeeze(0).cpu().numpy()
        seg=np.argmax(probs,axis=0).astype(np.int32); px=(resolution_m/1000)**2
        areas={c:round(int((seg==i).sum())*px,4) for i,c in enumerate(CLASSES)}
        conf=float(np.max(probs,axis=0).mean())
        return ToolOutput(type=OutputType.SEGMENTATION,value={"segmentation_mask":seg.tolist(),"class_probs":probs.tolist(),"class_areas_km2":areas,"classes":CLASSES},confidence=conf,metadata={"model":"LightweightDualEncoderFusion","status":"TRAINED_CHECKPOINT"})

def _to_three_channels(a):
    a=np.asarray(a,dtype=np.float32)
    if a.shape[0]>=4: a=a[[3,2,1]]
    elif a.shape[0]>3: a=a[:3]
    elif a.shape[0]==1: a=np.repeat(a,3,axis=0)
    elif a.shape[0]==2: a=np.concatenate([a,a[:1]],axis=0)
    return a

def _to_two_channels(a):
    a=np.asarray(a,dtype=np.float32)
    if a.shape[0]>=2: return a[:2]
    return np.repeat(a,2,axis=0)

import torch
import torch.nn as nn
import torch.nn.functional as F

class ConvBlock(nn.Module):
    def __init__(self,ci,co):
        super().__init__(); self.net=nn.Sequential(nn.Conv2d(ci,co,3,padding=1,bias=False),nn.BatchNorm2d(co),nn.ReLU(inplace=True),nn.Conv2d(co,co,3,padding=1,bias=False),nn.BatchNorm2d(co),nn.ReLU(inplace=True))
    def forward(self,x): return self.net(x)

class Encoder(nn.Module):
    def __init__(self,ci):
        super().__init__(); self.e1=ConvBlock(ci,24); self.e2=ConvBlock(24,48); self.e3=ConvBlock(48,96); self.e4=ConvBlock(96,128)
    def forward(self,x):
        a=self.e1(x); b=self.e2(F.max_pool2d(a,2)); c=self.e3(F.max_pool2d(b,2)); d=self.e4(F.max_pool2d(c,2)); return a,b,c,d

class DualEncoderFusion(nn.Module):
    """Small U-Net/FPN-style dual encoder; ~1.2M parameters."""
    def __init__(self,num_classes=5):
        super().__init__(); self.opt=Encoder(3); self.sar=Encoder(2)
        self.f4=ConvBlock(256,128); self.f3=ConvBlock(192,96); self.f2=ConvBlock(96,48); self.f1=ConvBlock(48,24); self.head=nn.Conv2d(24,num_classes,1)
    def forward(self,opt,sar):
        o1,o2,o3,o4=self.opt(opt); s1,s2,s3,s4=self.sar(sar)
        x=self.f4(torch.cat([o4,s4],1)); x=F.interpolate(x,size=o3.shape[-2:],mode="bilinear",align_corners=False); x=self.f3(torch.cat([o3,s3],1)+x)
        x=F.interpolate(x,size=o2.shape[-2:],mode="bilinear",align_corners=False); x=self.f2(torch.cat([o2,s2],1)+x)
        x=F.interpolate(x,size=o1.shape[-2:],mode="bilinear",align_corners=False); x=self.f1(torch.cat([o1,s1],1)+x)
        return self.head(F.interpolate(x,size=opt.shape[-2:],mode="bilinear",align_corners=False))
