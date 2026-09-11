from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RUNS_DIR = REPO_ROOT / "runs"

MAX_STEPS = 16
MAX_RUN_COST_EUR = 5.0
DEFAULT_MAX_TOKENS = 2048

SMALL_MODEL = "gemini/gemini-3.5-flash-lite"
LARGE_MODEL = "gemini/gemini-3.8-flash"

VALID_SECTIONS = {f"S{i}" for i in range(1, 14)}
