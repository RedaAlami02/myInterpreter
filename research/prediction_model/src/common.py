"""Shared paths, integrity checks, serialization, and reproducibility helpers."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FEATURE_DIR = PROJECT_ROOT / "data" / "features"
LABEL_DIR = PROJECT_ROOT / "data" / "labels"
MODEL_DIR = PROJECT_ROOT / "models"
REPORT_DIR = PROJECT_ROOT / "reports"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, default=json_default)
        handle.write("\n")


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest() -> dict[str, Any]:
    manifest = load_json(PROJECT_ROOT / "manifest.json")
    failures: list[str] = []
    for name, metadata in manifest["collections"].items():
        path = PROJECT_ROOT / metadata["file"]
        if not path.exists():
            failures.append(f"{name}: missing {path}")
            continue
        if path.stat().st_size != metadata["bytes"]:
            failures.append(f"{name}: byte-size mismatch")
        if sha256(path) != metadata["sha256"]:
            failures.append(f"{name}: checksum mismatch")
    if failures:
        raise RuntimeError("Raw-data integrity failure: " + "; ".join(failures))
    return manifest


def raw_frame(name: str) -> pd.DataFrame:
    return pd.DataFrame(load_json(RAW_DIR / f"{name}.json"))


def numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def clean_name(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()

