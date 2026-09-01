"""One-command helper for a free Colab/Kaggle session.
Run this from backend after mounting/downloading SEN12MS.
"""
import argparse,subprocess,sys
p=argparse.ArgumentParser(); p.add_argument('--data',required=True); p.add_argument('--epochs',type=int,default=5); p.add_argument('--limit',type=int,default=2000); a=p.parse_args()
subprocess.check_call([sys.executable,'scripts/train_optical_sar.py','--sen12ms_root',a.data,'--epochs',str(a.epochs),'--limit',str(a.limit),'--batch_size','4','--patch_size','96'])
