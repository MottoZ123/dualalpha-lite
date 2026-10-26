from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any
    completed_at: float
    completed_wall: float
    error: str | None = None

    def age(self) -> float:
        return max(0.0, time.time() - self.completed_wall)


class SWRCache:
    """SWR cache with single-flight, disk LKG, atomic writes and process locks."""

    def __init__(self, directory: str | Path | None = None):
        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _paths(self, key: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        assert self.directory is not None
        return self.directory / f"{digest}.json", self.directory / f"{digest}.lock"

    @contextmanager
    def _process_lock(self, key: str, timeout: float = 8.0):
        if not self.directory:
            yield
            return
        _, lock_path = self._paths(key)
        deadline = time.monotonic() + timeout
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > 300:
                        lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"cache process lock timeout: {key}")
                time.sleep(.04)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def _load_disk(self, key: str) -> CacheEntry | None:
        if not self.directory:
            return None
        data_path, _ = self._paths(key)
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            return CacheEntry(payload["value"], time.monotonic(), float(payload["completed_wall"]), payload.get("error"))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_disk(self, key: str, entry: CacheEntry):
        if not self.directory:
            return
        data_path, _ = self._paths(key)
        temporary = data_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(json.dumps({"key": key, "completed_wall": entry.completed_wall, "value": entry.value}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(temporary, data_path)

    def peek(self, key: str) -> CacheEntry | None:
        with self._guard:
            entry = self._entries.get(key)
        if entry:
            return entry
        entry = self._load_disk(key)
        if entry:
            with self._guard:
                self._entries.setdefault(key, entry)
                return self._entries[key]
        return None

    def status(self, key: str, hard_ttl: int) -> dict[str, Any]:
        entry = self.peek(key)
        age = entry.age() if entry else None
        return {"present": bool(entry), "ageSeconds": round(age, 3) if age is not None else None, "hardExpired": not entry or age > hard_ttl, "lastError": entry.error if entry else None}

    def get(self, key: str, builder: Callable[[], Any], ttl: int, hard_ttl: int, background: bool = True) -> tuple[Any, str]:
        entry = self.peek(key)
        age = entry.age() if entry else float("inf")
        if entry and age <= ttl:
            return entry.value, "fresh"
        lock = self._lock_for(key)
        if entry and age <= hard_ttl and background:
            if lock.acquire(blocking=False):
                threading.Thread(target=self._rebuild, args=(key, builder, lock), daemon=True).start()
            return entry.value, "stale"
        with lock:
            latest = self.peek(key)
            latest_age = latest.age() if latest else float("inf")
            if latest and latest_age <= ttl:
                return latest.value, "fresh"
            try:
                with self._process_lock(key):
                    disk = self._load_disk(key)
                    if disk and disk.age() <= ttl:
                        with self._guard:
                            self._entries[key] = disk
                        return disk.value, "fresh"
                    value = builder()
                    entry = CacheEntry(value=value, completed_at=time.monotonic(), completed_wall=time.time())
                    self._save_disk(key, entry)
                    with self._guard:
                        self._entries[key] = entry
                    return value, "fresh"
            except Exception as exc:
                if latest and latest_age <= hard_ttl:
                    latest.error = str(exc)
                    return latest.value, "stale-error"
                raise

    def _rebuild(self, key: str, builder: Callable[[], Any], lock: threading.Lock):
        try:
            with self._process_lock(key):
                value = builder()
                entry = CacheEntry(value=value, completed_at=time.monotonic(), completed_wall=time.time())
                self._save_disk(key, entry)
                with self._guard:
                    self._entries[key] = entry
        except Exception as exc:
            with self._guard:
                if key in self._entries:
                    self._entries[key].error = str(exc)
        finally:
            lock.release()
