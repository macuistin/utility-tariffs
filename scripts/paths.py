"""Repository folders used by every script."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# One folder per service, so gas or water can sit beside electricity later.
TARIFFS = ROOT / "tariffs" / "electricity"
