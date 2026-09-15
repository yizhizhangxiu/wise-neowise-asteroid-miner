"""Small conversion, serialization, CSV, and HTTP helpers."""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import requests


def safe_float(v, default=np.nan) -> float:
    """Convert a scalar-like value to a finite float or return ``default``."""
    try:
        if v is None or np.ma.is_masked(v):
            return float(default)
        x = float(v)
        return x if np.isfinite(x) else float(default)
    except Exception:
        return float(default)


def safe_int(v, default=None):
    """Convert a scalar-like value to int, returning ``default`` on failure."""
    x = safe_float(v, np.nan)
    return int(x) if np.isfinite(x) else default


def safe_str(v, default="") -> str:
    """Return a stripped string while tolerating masked/null table values."""
    try:
        if v is None or np.ma.is_masked(v):
            return default
        s = str(v).strip()
        return s if s else default
    except Exception:
        return default


def slugify(s: str) -> str:
    """Convert a target designation into a filesystem-safe directory name."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s.strip())
    return s.strip("_") or "target"


def robust_sigma(a: Iterable[float]) -> float:
    """Estimate Gaussian-equivalent sigma from the median absolute deviation."""
    x = np.asarray(list(a), dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return np.nan
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return float(1.4826 * mad)


def write_csv(rows: list[dict], path: Path) -> None:
    """Write dictionaries to CSV while preserving first-seen column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    cols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                cols.append(key)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def request_get(
    session: requests.Session,
    url: str,
    *,
    params=None,
    json_payload=None,
    timeout: int = 180,
    retries: int = 4,
) -> requests.Response:
    """GET a URL with bounded retries and simple linear backoff.

    MPC uses JSON request bodies for some GET endpoints, hence ``json_payload``
    is intentionally supported in addition to ordinary query parameters.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(
                url,
                params=params,
                json=json_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def jsonable(obj):
    """Recursively convert NumPy scalars into standard JSON-compatible values."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj
