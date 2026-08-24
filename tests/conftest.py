from __future__ import annotations

import os
from pathlib import Path


def _prepare_env() -> None:
    cache_dir = Path(".numba_cache")
    cache_dir.mkdir(exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_dir.resolve()))
    os.environ.setdefault("MPLBACKEND", "Agg")


_prepare_env()
