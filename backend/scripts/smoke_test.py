"""Fast no-weights smoke test for the SIH26167 demo pipeline."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from pathlib import Path
import numpy as np
import cv2

from app.tools.classical_baselines import change_mask, answer_vqa, grounding, multisource_segmentation


def main():
    h=w=256
    t1=np.zeros((3,h,w),np.float32); t1[0]=.35; t1[1]=.45; t1[2]=.20
    t2=t1.copy(); t2[:,80:170,90:190]=.9
    mask,prob,conf=change_mask(t1,t2)
    assert mask.mean()>0.01
    ans,vqa_conf=answer_vqa(t1,'What land cover dominates this image?')
    assert ans and vqa_conf>0
    boxes=grounding(t1,'bright built region')
    sar=np.stack([np.full((h,w),.2,np.float32),np.full((h,w),.4,np.float32)])
    seg,probs,areas,seg_conf=multisource_segmentation(t1,sar)
    assert seg.shape==(h,w) and probs.shape[1:]==(h,w)
    print('PASS change_ratio=',round(float(mask.mean()),4),'change_conf=',round(conf,3))
    print('PASS vqa=',ans)
    print('PASS grounding_boxes=',len(boxes))
    print('PASS optical_sar_conf=',round(seg_conf,3),'classes=',areas)

if __name__=='__main__': main()
