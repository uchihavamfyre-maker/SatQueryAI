# SatQuery — ₹0 / Free Compute Profile

This profile is designed to develop and demo SIH26167 without paid GPU APIs.

## Default behavior
- CPU-first backend
- Heavy 3B/7B models are opt-in
- Change detection uses the real image-processing baseline when ChangeFormer weights are absent
- Optical+SAR uses a transparent fusion baseline until a trained checkpoint exists
- RSVQA uses the transparent baseline by default; PaliGemma RSVQA-HR can be enabled later
- Every result reports `REAL_MODEL`, `PRETRAINED_RS_VQA`, or `BASELINE` so the demo never claims a model ran when it did not

## Free workflow
1. Develop locally on CPU.
2. Use Google Colab Free or Kaggle notebooks only for occasional training/benchmark runs.
3. Download checkpoints to `data/models/` and run the same backend locally.
4. Deploy the lightweight frontend to Vercel; keep ML inference local for the SIH demo if necessary.

## Optional heavy models
Do NOT enable GeoChat/DeltaVLM/PaliGemma unless you have enough RAM/VRAM. They are not required for the zero-cost baseline demo.

## Colab
See `notebooks/sih26167_free_gpu.ipynb` for a one-cell-friendly evaluation/training workflow.
