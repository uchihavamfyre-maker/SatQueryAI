#!/usr/bin/env python3
"""Print the recommended zero-cost SatQuery model profile."""
import os
print("SatQuery ZERO-COST PROFILE")
print("device:", os.getenv("DEFAULT_DEVICE", "cpu"))
print("RSVQA:", os.getenv("RSVQA_BACKEND", "baseline"))
print("Heavy models: opt-in only")
print("Recommended GPU: temporary Colab/Kaggle session")
