"""Adapter for the official wgcban/ChangeFormer implementation.

The repository is intentionally not vendored into SatQuery. Run
`scripts/setup_models.py --changeformer` to install it under data/models.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import importlib

import torch
import torch.nn.functional as F


class OfficialChangeFormer:
    def __init__(self, repo_dir: Path, checkpoint: Path, device: str = "cpu"):
        self.repo_dir = Path(repo_dir)
        self.checkpoint = Path(checkpoint)
        self.device = torch.device(device)
        self.net = None

    def load(self) -> None:
        sys.path.insert(0, str(self.repo_dir))
        try:
            networks = importlib.import_module("models.networks")
            args = SimpleNamespace(
                net_G="ChangeFormerV6",
                embed_dim=256,
                gpu_ids=[],
                n_class=2,
            )
            self.net = networks.define_G(args=args, gpu_ids=[])
            ckpt = torch.load(self.checkpoint, map_location=self.device)
            state = ckpt.get("model_G_state_dict", ckpt.get("model", ckpt))
            # Handle DataParallel checkpoints.
            state = {k.replace("module.", "", 1) if k.startswith("module.") else k: v for k, v in state.items()}
            self.net.load_state_dict(state, strict=True)
            self.net.to(self.device).eval()
        finally:
            # Keep the repo path in sys.path because model modules are lazily imported.
            pass

    @torch.inference_mode()
    def predict(self, t1, t2):
        x1 = torch.from_numpy(t1).float().unsqueeze(0).to(self.device)
        x2 = torch.from_numpy(t2).float().unsqueeze(0).to(self.device)
        out = self.net(x1, x2)
        if isinstance(out, (list, tuple)):
            out = out[-1]
        prob = torch.softmax(out, dim=1)[:, 1]
        prob = F.interpolate(prob[:, None], size=t1.shape[-2:], mode="bilinear", align_corners=False)[:, 0]
        return prob.squeeze(0).cpu().numpy()


def discover_checkpoint(repo_dir: Path) -> Path | None:
    repo_dir = Path(repo_dir)
    candidates = list(repo_dir.rglob("best_ckpt.pt")) + list(repo_dir.rglob("*.pth")) + list(repo_dir.rglob("*.pt"))
    candidates = [p for p in candidates if p.is_file()]
    # Prefer the official LEVIR project checkpoint.
    for p in candidates:
        if "LEVIR" in str(p) or "levIr" in str(p):
            return p
    return candidates[0] if candidates else None
