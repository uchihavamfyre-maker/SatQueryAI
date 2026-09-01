"""Evaluate SatQuery's ChangeFormer adapter on a LEVIR-style dataset.

Expected dataset layout:
  root/A/*.png
  root/B/*.png
  root/label/*.png

Reports Precision, Recall, F1, IoU and OA, matching the metrics used by the
official ChangeFormer evaluation. This is for local validation; do not claim
these numbers for your own model until this script has actually been run.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.tools.changeformer_official import OfficialChangeFormer, discover_checkpoint


def load_rgb(p: Path, size=256):
    im = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
    im = cv2.resize(im, (size, size), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
    mean = np.array([0.485,0.456,0.406], dtype=np.float32)[None,None,:]
    std = np.array([0.229,0.224,0.225], dtype=np.float32)[None,None,:]
    im = (im-mean)/std
    return np.transpose(im, (2,0,1))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dataset', required=True)
    ap.add_argument('--threshold', type=float, default=.5)
    ap.add_argument('--limit', type=int, default=0)
    args=ap.parse_args()
    root=Path(args.dataset); aroot=root/'A'; broot=root/'B'; lroot=root/'label'
    ckpt=discover_checkpoint(settings.models_dir/'changeformer'/'official')
    if ckpt is None: raise SystemExit('No ChangeFormer checkpoint. Run setup_models.py --changeformer')
    model=OfficialChangeFormer(settings.models_dir/'changeformer'/'official', ckpt, 'cuda' if __import__('torch').cuda.is_available() else 'cpu')
    model.load()
    files=sorted(aroot.glob('*'))
    if args.limit: files=files[:args.limit]
    tp=tn=fp=fn=0
    for apath in files:
        bpath=broot/apath.name; lpath=lroot/apath.name
        if not bpath.exists() or not lpath.exists(): continue
        p=(model.predict(load_rgb(apath), load_rgb(bpath)) >= args.threshold).astype(np.uint8)
        y=cv2.imread(str(lpath), cv2.IMREAD_GRAYSCALE)
        y=(cv2.resize(y,(p.shape[1],p.shape[0]),interpolation=cv2.INTER_NEAREST)>127).astype(np.uint8)
        tp += int(((p==1)&(y==1)).sum()); tn += int(((p==0)&(y==0)).sum())
        fp += int(((p==1)&(y==0)).sum()); fn += int(((p==0)&(y==1)).sum())
    precision=tp/max(tp+fp,1); recall=tp/max(tp+fn,1); f1=2*precision*recall/max(precision+recall,1e-9); iou=tp/max(tp+fp+fn,1); oa=(tp+tn)/max(tp+tn+fp+fn,1)
    print({'precision':precision,'recall':recall,'f1':f1,'iou':iou,'oa':oa,'samples':len(files)})

if __name__=='__main__': main()
