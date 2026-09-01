from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from app.tools.external_vlm import save_rgb

def geochat(model_root: Path, image: np.ndarray, prompt: str, mode='caption', max_tokens=256) -> str:
    repo=model_root/'official'; model=model_root/'weights'
    if not repo.exists() or not model.exists(): raise FileNotFoundError('GeoChat is not installed; run python scripts/setup_models.py --geochat')
    with tempfile.TemporaryDirectory(prefix='satquery_geo_') as td:
        img=Path(td)/'image.png'; save_rgb(image,img)
        p=subprocess.run([sys.executable,str(Path(__file__).parents[2]/'scripts'/'geochat_infer.py'),'--repo',str(repo),'--model',str(model),'--image',str(img),'--prompt',prompt,'--mode',mode,'--max-new-tokens',str(max_tokens)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        if p.returncode: raise RuntimeError(p.stdout[-8000:])
        line=next((x for x in reversed(p.stdout.splitlines()) if x.strip().startswith('{')),None)
        if not line: raise RuntimeError(p.stdout[-4000:])
        return json.loads(line)['text']

def deltavlm(model_root: Path, t1: np.ndarray, t2: np.ndarray, prompt: str) -> str:
    root=model_root/'pretrained'; repo=model_root/'official'
    ck=root/'deltavlm'/'checkpoint_best.pth'
    if not ck.exists():
        # HF may place the checkpoint one directory deeper.
        found=list((root/'deltavlm').rglob('checkpoint_best.pth'))
        if found: ck=found[0]
    if not repo.exists() or not ck.exists(): raise FileNotFoundError('DeltaVLM is not installed; run python scripts/setup_models.py --deltavlm')
    with tempfile.TemporaryDirectory(prefix='satquery_delta_') as td:
        td=Path(td); a=td/'A.png'; b=td/'B.png'; save_rgb(t1,a); save_rgb(t2,b)
        p=subprocess.run([sys.executable,str(Path(__file__).parents[2]/'scripts'/'deltavlm_infer.py'),'--repo',str(repo),'--checkpoint',str(ck),'--llm',str(root/'vicuna-7b-v1.5'),'--bert',str(root/'bert-base-uncased'),'--image-a',str(a),'--image-b',str(b),'--prompt',prompt],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        if p.returncode: raise RuntimeError(p.stdout[-8000:])
        line=next((x for x in reversed(p.stdout.splitlines()) if x.strip().startswith('{')),None)
        return json.loads(line)['text'] if line else p.stdout[-8000:]
