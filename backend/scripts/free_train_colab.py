"""Run a presentation-sized SEN12MS training job on Colab/Kaggle.

The dataset must be downloaded from its official source and mounted at ``--data``.
This helper never fabricates metrics and refuses to claim GPU usage when CUDA is
not available.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Mounted SEN12MS root directory")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--patch-size", type=int, default=96)
    parser.add_argument("--output-dir", default="data/models/optical_sar_fusion")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()

    import torch

    if not args.cpu and not torch.cuda.is_available():
        raise SystemExit(
            "CUDA GPU is unavailable. In Colab select Runtime > Change runtime type > T4 GPU, "
            "or rerun with --cpu."
        )
    print(f"Training device: {'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'}")

    command = [
        sys.executable,
        "scripts/train_optical_sar.py",
        "--sen12ms_root",
        args.data,
        "--epochs",
        str(args.epochs),
        "--limit",
        str(args.limit),
        "--batch_size",
        str(args.batch_size),
        "--patch_size",
        str(args.patch_size),
        "--output_dir",
        args.output_dir,
    ]
    if args.cpu:
        command.append("--cpu")
    subprocess.check_call(command)

    metrics_path = Path(args.output_dir) / "training_metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
