"""
Fine-tune RSVQA-HR on RSVQA dataset + BigEarthNet-derived QA pairs
==================================================================
RSVQA dataset: https://zenodo.org/record/6344334
BigEarthNet:   https://bigearth.net/

Usage
-----
  python scripts/finetune_rsvqa.py \
      --rsvqa_root /data/RSVQA_HR \
      --bigearth_root /data/BigEarthNet \
      --output_dir data/models/rsvqa_hr \
      --epochs 20 \
      --batch_size 32
"""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ─── RSVQA-HR Dataset ─────────────────────────────────────────────────────────

class RSVQADataset(Dataset):
    """
    RSVQA-HR dataset loader.
    Structure:
      root/
        Images/  (*.tif or *.png)
        USGS_split_train_questions.json
        USGS_split_train_answers.json
    """

    def __init__(self, root: Path, split: str = "train", img_size: int = 512):
        self.root = root
        self.img_size = img_size
        self.samples: list[dict] = []
        self.answer_vocab: list[str] = []
        self._load(split)

    def _load(self, split: str) -> None:
        q_file = self.root / f"USGS_split_{split}_questions.json"
        a_file = self.root / f"USGS_split_{split}_answers.json"
        if not q_file.exists():
            logger.warning(f"RSVQA question file not found: {q_file}")
            return

        with open(q_file) as f:
            questions = json.load(f)["questions"]
        with open(a_file) as f:
            answers_data = json.load(f)["answers"]

        # Build answer vocabulary
        all_answers = [a["answer"] for a in answers_data]
        self.answer_vocab = sorted(set(all_answers))
        ans_to_idx = {a: i for i, a in enumerate(self.answer_vocab)}
        answers_by_id = {a["id"]: a["answer"] for a in answers_data}

        img_dir = self.root / "Images"
        for q in questions:
            img_id = str(q.get("img_id", q.get("image_id", "")))
            # Try common extensions
            img_path = None
            for ext in (".tif", ".tiff", ".png", ".jpg"):
                p = img_dir / f"{img_id}{ext}"
                if p.exists():
                    img_path = p
                    break
            if img_path is None:
                continue
            answer_text = answers_by_id.get(q["id"], "")
            if answer_text not in ans_to_idx:
                continue
            self.samples.append({
                "img_path": img_path,
                "question": q["question"],
                "answer_idx": ans_to_idx[answer_text],
            })

        logger.info(f"RSVQA-HR {split}: {len(self.samples)} samples, {len(self.answer_vocab)} answer classes")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        import cv2
        sample = self.samples[idx]
        img = _load_image(sample["img_path"], self.img_size)
        return {
            "image": torch.from_numpy(img),
            "question": sample["question"],
            "answer_idx": torch.tensor(sample["answer_idx"], dtype=torch.long),
        }


def _load_image(path: Path, size: int) -> np.ndarray:
    """Load image as [3, size, size] float32 ImageNet-normalized."""
    import cv2
    try:
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read().astype(np.float32)
        # Select RGB bands
        if arr.shape[0] >= 3:
            arr = arr[[2, 1, 0], :, :]  # BGR → RGB for Sentinel-2 style
        elif arr.shape[0] == 1:
            arr = np.repeat(arr, 3, axis=0)
        else:
            arr = np.stack([arr[0], arr[0], arr[0]], axis=0)
    except Exception:
        img = cv2.imread(str(path))
        if img is None:
            return np.zeros((3, size, size), dtype=np.float32)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        arr = np.transpose(img, (2, 0, 1)).astype(np.float32)

    # Normalize per-band to [0,1]
    for i in range(arr.shape[0]):
        lo, hi = arr[i].min(), arr[i].max()
        arr[i] = (arr[i] - lo) / (hi - lo + 1e-8)

    # Resize
    import cv2 as cv
    out = np.zeros((3, size, size), dtype=np.float32)
    for i in range(3):
        out[i] = cv.resize(arr[i], (size, size), interpolation=cv.INTER_LINEAR)

    # ImageNet normalize
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]
    return (out - mean) / std


# ─── Collate (handles variable-length questions) ──────────────────────────────

def collate_fn(batch: list[dict], tokenizer):
    images = torch.stack([b["image"] for b in batch])
    questions = [b["question"] for b in batch]
    answer_idxs = torch.stack([b["answer_idx"] for b in batch])
    encoding = tokenizer(
        questions,
        return_tensors="pt",
        max_length=64,
        padding="max_length",
        truncation=True,
    )
    return {
        "images": images,
        "input_ids": encoding["input_ids"],
        "attention_mask": encoding["attention_mask"],
        "answer_idxs": answer_idxs,
    }


# ─── Training ─────────────────────────────────────────────────────────────────

def train(args: argparse.Namespace) -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.tools.rs_vqa import _RSVQAModel

    from transformers import BertTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Training RSVQA on: {device}")

    rsvqa_root = Path(args.rsvqa_root)
    train_ds = RSVQADataset(rsvqa_root, split="train", img_size=args.img_size)
    val_ds = RSVQADataset(rsvqa_root, split="val", img_size=args.img_size)

    if len(train_ds) == 0:
        logger.error("No training samples found. Check --rsvqa_root path and dataset structure.")
        return

    tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
    _collate = lambda b: collate_fn(b, tokenizer)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.num_workers, collate_fn=_collate, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=args.num_workers, collate_fn=_collate, pin_memory=True)

    num_answers = len(train_ds.answer_vocab)
    model = _RSVQAModel(num_answers=num_answers, visual_backbone="resnet50").to(device)

    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.CrossEntropyLoss()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            images = batch["images"].to(device)
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            targets = batch["answer_idxs"].to(device)

            optimizer.zero_grad()
            logits = model(images, input_ids, attention_mask)
            loss = criterion(logits, targets)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for batch in val_loader:
                images = batch["images"].to(device)
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                targets = batch["answer_idxs"].to(device)
                logits = model(images, input_ids, attention_mask)
                preds = logits.argmax(dim=1)
                correct += (preds == targets).sum().item()
                total += targets.size(0)

        val_acc = correct / max(total, 1)
        scheduler.step()
        logger.info(f"Epoch {epoch:03d}/{args.epochs} | train_loss={train_loss:.4f} | val_acc={val_acc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            ckpt_path = output_dir / "rsvqa_hr_finetuned.pth"
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "answer_vocab": train_ds.answer_vocab,
                "val_acc": val_acc,
            }, ckpt_path)
            logger.info(f"  ✓ Saved best checkpoint → {ckpt_path} (val_acc={val_acc:.4f})")

    logger.info(f"Fine-tuning complete. Best val_acc={best_val_acc:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rsvqa_root", type=str, required=True)
    parser.add_argument("--bigearth_root", type=str, default=None)
    parser.add_argument("--output_dir", type=str, default="data/models/rsvqa_hr")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--img_size", type=int, default=512)
    parser.add_argument("--num_workers", type=int, default=4)
    args = parser.parse_args()
    train(args)
