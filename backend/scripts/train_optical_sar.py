"""Train SatQuery's lightweight Optical+SAR fusion model.
Works with SEN12MS and BigEarthNet-style folders and is designed for free Colab/Kaggle.
Example: python scripts/train_optical_sar.py --sen12ms_root /data/SEN12MS --epochs 5 --batch_size 4
"""
from __future__ import annotations
import argparse,json,logging,random
from pathlib import Path
import numpy as np, torch
from torch import nn,optim
from torch.utils.data import DataLoader,Dataset,random_split
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s"); log=logging.getLogger("train")
CLASSES=["built_up","water","vegetation","bare_soil","other"]; N=5
MAP={**{i:2 for i in range(1,11)},11:1,12:3,13:0,14:3,15:4,16:3,17:1,18:4,0:4}
SEASONS=["ROIs1158_spring","ROIs1868_summer","ROIs1970_fall","ROIs2017_winter"]

def norm_opt(x):
    x=x.astype(np.float32); out=np.empty_like(x)
    for i in range(x.shape[0]):
        lo,hi=np.percentile(x[i],[2,98]); out[i]=np.clip((x[i]-lo)/(hi-lo+1e-6),0,1)
    return out

def norm_sar(x):
    x=np.maximum(x.astype(np.float32),1e-8); db=10*np.log10(x); return np.clip((db+30)/35,0,1).astype(np.float32)

def resize(x,size,nearest=False):
    import cv2; return np.stack([cv2.resize(c,(size,size),interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_AREA) for c in x])
class SEN12(Dataset):
    def __init__(self,root,size=96,limit=0):
        self.root=Path(root); self.size=size; self.samples=[]
        for season in SEASONS:
            d=self.root/season; s1=d/"s1"; s2=d/"s2"; lc=d/"lc"
            if not s1.exists() or not s2.exists(): continue
            for f in sorted(s1.glob("*.tif")):
                sf=s2/f.name.replace("_s1_","_s2_"); lf=lc/f.name.replace("_s1_","_lc_") if lc.exists() else None
                if sf.exists(): self.samples.append((f,sf,lf))
        if limit: self.samples=self.samples[:limit]
        log.info("SEN12MS samples=%d",len(self.samples))
    def __len__(self): return len(self.samples)
    def __getitem__(self,i):
        import rasterio
        sf,of,lf=self.samples[i]
        with rasterio.open(sf) as d:sar=d.read()
        with rasterio.open(of) as d:opt=d.read()
        if opt.shape[0]>=4: opt=opt[[3,2,1]]
        elif opt.shape[0]<3: opt=np.pad(opt,((0,3-opt.shape[0]),(0,0),(0,0)),mode='edge')[:3]
        sar= sar[:2] if sar.shape[0]>=2 else np.repeat(sar,2,axis=0)
        if lf and lf.exists():
            with rasterio.open(lf) as d: y=np.vectorize(MAP.get)(d.read(1),4).astype(np.int64)
        else: y=np.full(opt.shape[1:],4,np.int64)
        return torch.from_numpy(resize(norm_opt(opt),self.size)),torch.from_numpy(resize(norm_sar(sar),self.size)),torch.from_numpy(resize(y[None],self.size,True)[0])

def metrics(pred,y):
    p=pred.reshape(-1); y=y.reshape(-1); ious=[]; f1=[]
    for c in range(N):
        tp=((p==c)&(y==c)).sum(); fp=((p==c)&(y!=c)).sum(); fn=((p!=c)&(y==c)).sum()
        ious.append(float(tp/(tp+fp+fn+1e-8))); f1.append(float(2*tp/(2*tp+fp+fn+1e-8)))
    return float(np.mean(ious)),float(np.mean(f1)),float((p==y).mean())
def main(a):
    from app.tools.optical_sar import DualEncoderFusion
    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    ds=SEN12(a.sen12ms_root,a.patch_size,a.limit) if a.sen12ms_root else None
    if ds is None or len(ds)<2: raise SystemExit("Need at least 2 SEN12MS paired samples")
    nv=max(1,int(len(ds)*a.val_fraction)); tr,va=random_split(ds,[len(ds)-nv,nv],generator=torch.Generator().manual_seed(a.seed))
    dev=torch.device('cuda' if torch.cuda.is_available() and not a.cpu else 'cpu'); log.info("device=%s train=%d val=%d",dev,len(tr),len(va))
    model=DualEncoderFusion(N).to(dev); opt=optim.AdamW(model.parameters(),lr=a.lr,weight_decay=1e-4); lossfn=nn.CrossEntropyLoss(); best=-1
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); history=[]
    for ep in range(1,a.epochs+1):
        model.train(); tl=0
        for o,s,y in DataLoader(tr,a.batch_size,shuffle=True,num_workers=0):
            o,s,y=o.to(dev),s.to(dev),y.to(dev); opt.zero_grad(); loss=lossfn(model(o,s),y); loss.backward(); opt.step(); tl+=loss.item()
        model.eval(); vl=0; allp=[]; ally=[]
        with torch.no_grad():
            for o,s,y in DataLoader(va,a.batch_size,shuffle=False,num_workers=0):
                z=model(o.to(dev),s.to(dev)); vl+=lossfn(z,y.to(dev)).item(); allp.append(z.argmax(1).cpu().numpy()); ally.append(y.numpy())
        miou,f1,acc=metrics(np.concatenate(allp),np.concatenate(ally)); rec={"epoch":ep,"train_loss":tl/max(1,len(tr)),"val_loss":vl/max(1,len(va)),"mIoU":miou,"mF1":f1,"accuracy":acc}; history.append(rec); log.info("%s",rec)
        if miou>best:
            best=miou; torch.save({"model_state_dict":model.state_dict(),"classes":CLASSES,"epoch":ep,"mIoU":miou,"mF1":f1,"accuracy":acc,"model":"LightweightDualEncoderFusion"},out/"dual_encoder_fused.pth")
    (out/"training_metrics.json").write_text(json.dumps({"best_mIoU":best,"history":history},indent=2)); log.info("saved %s",out)
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--sen12ms_root',required=True); p.add_argument('--output_dir',default='data/models/optical_sar_fusion'); p.add_argument('--epochs',type=int,default=5); p.add_argument('--batch_size',type=int,default=4); p.add_argument('--patch_size',type=int,default=96); p.add_argument('--limit',type=int,default=0); p.add_argument('--val_fraction',type=float,default=.2); p.add_argument('--lr',type=float,default=3e-4); p.add_argument('--seed',type=int,default=42); p.add_argument('--cpu',action='store_true'); main(p.parse_args())
