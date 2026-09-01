"""Prepare optional official research models for SatQuery.

Core app works without these downloads using transparent baselines. The commands
below install the actual research implementations/checkpoints when a suitable GPU
and the model licenses are available.
"""
from __future__ import annotations
import argparse, os, shutil, subprocess, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODELS=ROOT.parent/"data"/"models"

def git_clone(url: str, target: Path):
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists(): subprocess.check_call(["git","clone","--depth","1",url,str(target)])

def hf(repo: str, local: Path):
    from huggingface_hub import snapshot_download
    local.mkdir(parents=True,exist_ok=True)
    snapshot_download(repo_id=repo, local_dir=str(local), token=os.getenv("HF_TOKEN"), local_dir_use_symlinks=False)

def setup_changeformer():
    target=MODELS/"changeformer"/"official"; git_clone("https://github.com/wgcban/ChangeFormer.git",target)
    url="https://github.com/wgcban/ChangeFormer/releases/download/v0.1.0/CD_ChangeFormerV6_LEVIR_b16_lr0.0001_adamw_train_test_200_linear_ce_multi_train_True_multi_infer_False_shuffle_AB_False_embed_dim_256.zip"
    ck=target/"checkpoints"/"ChangeFormer_LEVIR"/"best_ckpt.pt"; ck.parent.mkdir(parents=True,exist_ok=True)
    if not ck.exists():
        archive=MODELS/"changeformer"/"release.zip"; urllib.request.urlretrieve(url,archive)
        tmp=target/"_release"; tmp.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as z: z.extractall(tmp)
        found=list(tmp.rglob("best_ckpt.pt"))+list(tmp.rglob("*.pth"))+list(tmp.rglob("*.pt"))
        if not found: raise RuntimeError("ChangeFormer archive contained no checkpoint")
        shutil.copy2(found[0],ck); shutil.rmtree(tmp,ignore_errors=True); archive.unlink(missing_ok=True)
    print("ChangeFormer ready:",ck)

def setup_rsvqa():
    local=MODELS/"paligemma_rsvqa_hr_224"; hf("google/paligemma-3b-ft-rsvqa-hr-224",local); print("RSVQA ready:",local)

def setup_geochat():
    repo=MODELS/"geochat"/"official"; git_clone("https://github.com/mbzuai-oryx/GeoChat.git",repo)
    weights=MODELS/"geochat"/"weights"; hf("MBZUAI/geochat-7B",weights)
    print("GeoChat ready:",repo,weights)

def setup_deltavlm():
    repo=MODELS/"deltavlm"/"official"; git_clone("https://github.com/hanlinwu/DeltaVLM.git",repo)
    root=MODELS/"deltavlm"/"pretrained"
    hf("hlwu/DeltaVLM",root/"deltavlm")
    hf("lmsys/vicuna-7b-v1.5",root/"vicuna-7b-v1.5")
    hf("bert-base-uncased",root/"bert-base-uncased")
    print("DeltaVLM ready:",repo)

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--changeformer",action="store_true"); ap.add_argument("--rsvqa",action="store_true"); ap.add_argument("--geochat",action="store_true"); ap.add_argument("--deltavlm",action="store_true"); ap.add_argument("--all",action="store_true")
    a=ap.parse_args()
    if a.all or a.changeformer: setup_changeformer()
    if a.all or a.rsvqa: setup_rsvqa()
    if a.all or a.geochat: setup_geochat()
    if a.all or a.deltavlm: setup_deltavlm()
    if not any(vars(a).values()): ap.print_help()
