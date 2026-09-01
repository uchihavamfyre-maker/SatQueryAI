# SatQuery — ₹0 ML path

The default Optical+SAR model is now a small, genuinely trainable dual-encoder (~1.2M parameters). It can be trained on a free Colab/Kaggle GPU or CPU; no paid API is required.

## Train on SEN12MS

```bash
python scripts/train_optical_sar.py --sen12ms_root /path/to/SEN12MS --epochs 5 --limit 2000
```

For a CPU laptop:

```bash
python scripts/train_optical_sar.py --sen12ms_root /path/to/SEN12MS --epochs 2 --limit 200 --cpu --patch_size 64 --batch_size 2
```

The checkpoint and `training_metrics.json` are written to `data/models/optical_sar_fusion/`.

## What to report to SIH judges

Do not invent benchmark numbers. Run training/evaluation and show the generated mIoU, mF1 and accuracy from `training_metrics.json`. The app labels a checkpoint as `TRAINED_CHECKPOINT`; otherwise it labels the deterministic path as `BASELINE`.
