"""Tiny file cache with per-entry TTL. Values are pickled."""
from __future__ import annotations

import hashlib
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


class FileCache:
    def __init__(self, directory: str | Path, enabled: bool = True):
        self.dir = Path(directory)
        self.enabled = enabled
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Hash-only names keep paths short (Windows MAX_PATH is 260 characters).
        return self.dir / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:24]}.pkl"

    def get(self, key: str, ttl_seconds: float) -> Any | None:
        if not self.enabled:
            return None
        p = self._path(key)
        if not p.exists():
            return None
        if time.time() - p.stat().st_mtime > ttl_seconds:
            return None
        try:
            with p.open("rb") as f:
                return pickle.load(f)
        except Exception as e:  # corrupt entry: ignore and refetch
            log.debug("cache read failed for %s: %s", key, e)
            return None

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(value, f)
        tmp.replace(p)

    def get_or_set(self, key: str, ttl_seconds: float, fn: Callable[[], Any]) -> Any:
        hit = self.get(key, ttl_seconds)
        if hit is not None:
            log.debug("cache hit: %s", key)
            return hit
        value = fn()
        if value is not None:
            self.set(key, value)
        return value
