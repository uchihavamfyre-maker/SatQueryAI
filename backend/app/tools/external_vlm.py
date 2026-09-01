"""Optional adapters for official remote-sensing VLM repositories.

The SatQuery API remains dependency-light. Heavy research models are executed in
an isolated subprocess after their official repositories/checkpoints are installed.
This avoids pretending that a generic transformers model is GeoChat/DeltaVLM.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image


def save_rgb(array: np.ndarray, path: Path) -> None:
    x = np.asarray(array, np.float32)
    if x.ndim != 3:
        raise ValueError("Expected CHW image")
    if x.shape[0] == 1:
        x = np.repeat(x, 3, axis=0)
    elif x.shape[0] == 2:
        x = np.stack([x[0], x[1], x[0]], axis=0)
    elif x.shape[0] > 3:
        x = x[:3]
    x = np.transpose(x, (1, 2, 0))
    finite = np.isfinite(x)
    vals = x[finite]
    lo, hi = (np.percentile(vals, [2, 98]) if vals.size else (0, 1))
    x = np.clip((x-lo)/max(float(hi-lo),1e-6),0,1)
    Image.fromarray((x*255).astype(np.uint8)).save(path)


def run_json(command: list[str], cwd: Path, timeout: int = 600, env: dict | None = None) -> dict:
    p = subprocess.run(command, cwd=str(cwd), env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-8000:])
    # Prefer a JSON object emitted by an adapter script.
    for line in reversed(p.stdout.splitlines()):
        line=line.strip()
        if line.startswith("{") and line.endswith("}"):
            try: return json.loads(line)
            except Exception: pass
    return {"text": p.stdout[-8000:]}


def delta_vlm(repo: Path, checkpoint: Path, llm: Path, bert: Path,
              t1: np.ndarray, t2: np.ndarray, prompt: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="satquery_delta_") as td:
        td=Path(td); a=td/"A.png"; b=td/"B.png"; out=td/"result.json"
        save_rgb(t1,a); save_rgb(t2,b)
        cmd=[sys.executable, "scripts/predict.py", "--image_A", str(a), "--image_B", str(b),
             "--checkpoint", str(checkpoint), "--llm_model", str(llm), "--bert_model", str(bert),
             "--prompt", prompt, "--output", str(out)]
        # Some released revisions expose only the positional prompt; retry without
        # optional prompt/output flags if the first invocation rejects them.
        try:
            result=run_json(cmd,repo,timeout=900)
            if result: return result
        except Exception as first:
            cmd2=[sys.executable,"scripts/predict.py","--image_A",str(a),"--image_B",str(b),
                  "--checkpoint",str(checkpoint),"--llm_model",str(llm),"--bert_model",str(bert)]
            result=run_json(cmd2,repo,timeout=900)
            if result: return result
            raise first
        if out.exists(): return json.loads(out.read_text())
        raise RuntimeError("DeltaVLM adapter produced no result")
