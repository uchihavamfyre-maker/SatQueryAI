"""CLI adapter around the official DeltaVLM repository."""
import argparse, json, subprocess, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',required=True); ap.add_argument('--checkpoint',required=True); ap.add_argument('--llm',required=True); ap.add_argument('--bert',required=True); ap.add_argument('--image-a',required=True); ap.add_argument('--image-b',required=True); ap.add_argument('--prompt',required=True)
    a=ap.parse_args(); cmd=[sys.executable,'scripts/predict.py','--image_A',a.image_a,'--image_B',a.image_b,'--checkpoint',a.checkpoint,'--llm_model',a.llm,'--bert_model',a.bert]
    p=subprocess.run(cmd,cwd=a.repo,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    if p.returncode: raise SystemExit(p.stdout)
    print(json.dumps({'text':p.stdout,'model':'DeltaVLM'}))
if __name__=='__main__': main()
