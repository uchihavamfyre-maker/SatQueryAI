# GPU training for the presentation

The repository includes a small dual-encoder model that is practical on a free
Google Colab T4 GPU. The dataset is not committed to Git because SEN12MS is
large and must be downloaded from its official source:
<https://mediatum.ub.tum.de/1474000>.

In Colab, select **Runtime > Change runtime type > T4 GPU**, then run:

```bash
!git clone https://github.com/uchihavamfyre-maker/SatQueryAI.git
%cd SatQueryAI/backend
!pip install torch torchvision rasterio opencv-python-headless numpy
```

Upload or mount the extracted SEN12MS directory, then run:

```bash
!python scripts/free_train_colab.py \
  --data /content/SEN12MS \
  --epochs 5 \
  --limit 2000 \
  --batch-size 4 \
  --patch-size 96
```

The script verifies CUDA before training and writes:

- `data/models/optical_sar_fusion/dual_encoder_fused.pth`
- `data/models/optical_sar_fusion/training_metrics.json`

Use the generated `training_metrics.json` in the presentation. Do not claim
benchmark accuracy unless the training output contains the measured values.
