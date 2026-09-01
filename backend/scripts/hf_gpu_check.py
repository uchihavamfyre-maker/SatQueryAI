"""Run on a Hugging Face GPU Job to validate CUDA + model access.

Example:
  python scripts/hf_gpu_check.py
"""
import os
import torch

print({
    "cuda_available": torch.cuda.is_available(),
    "device_count": torch.cuda.device_count(),
    "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    "hf_token_present": bool(os.getenv("HF_TOKEN")),
})
