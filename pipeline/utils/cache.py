"""
Cache utilities for the CycloneShield pipeline.

All heavy computation outputs are cached to disk so:
  - the live demo never depends on GEE quota or network
  - repeated runs skip already-computed steps
  - Gemini responses are cached by input hash
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from pipeline.utils.logger import get_logger

log = get_logger(__name__)
T = TypeVar("T")


def compute_hash(data: Any) -> str:
    """
    Compute a SHA-256 hash of any JSON-serializable object.

    Parameters
    ----------
    data : Any
        JSON-serializable object to hash.

    Returns
    -------
    str
        Hex digest of the SHA-256 hash (first 16 chars for brevity).
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def load_json_cache(path: Path) -> Optional[Any]:
    """
    Load a JSON cache file if it exists.

    Parameters
    ----------
    path : Path
        Path to the cache file.

    Returns
    -------
    Any or None
        Parsed JSON if the file exists, else None.
    """
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            log.debug(f"Cache hit: {path}")
            return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"Cache read failed for {path}: {e}")
    return None


def save_json_cache(path: Path, data: Any) -> None:
    """
    Save data to a JSON cache file, creating parent directories as needed.

    Parameters
    ----------
    path : Path
        Destination path.
    data : Any
        JSON-serializable data to save.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    log.debug(f"Cache saved: {path}")


def cached_step(
    cache_path: Path,
    compute_fn: Callable[[], T],
    force: bool = False,
) -> T:
    """
    Run a computation with file caching.

    If the cache file exists and ``force`` is False, return the cached result.
    Otherwise, run ``compute_fn()``, save the result, and return it.

    Parameters
    ----------
    cache_path : Path
        Path to the JSON cache file.
    compute_fn : Callable[[], T]
        Function that computes and returns the result.
    force : bool
        If True, re-run even if cache exists.

    Returns
    -------
    T
        The computed (or cached) result.
    """
    if not force:
        cached = load_json_cache(cache_path)
        if cached is not None:
            log.info(f"Using cached result from {cache_path.name}")
            return cached  # type: ignore[return-value]

    log.info(f"Computing (no cache or force=True): {cache_path.name}")
    result = compute_fn()
    save_json_cache(cache_path, result)
    return result


def gemini_cache_path(cache_dir: Path, input_hash: str, lang: str) -> Path:
    """
    Return the cache file path for a Gemini API response.

    Parameters
    ----------
    cache_dir : Path
        Directory for advisory caches.
    input_hash : str
        Hash of the input fact pack.
    lang : str
        Language code (e.g. 'en', 'hi', 'or').

    Returns
    -------
    Path
    """
    return cache_dir / f"advisory_{input_hash}_{lang}.json"
