from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class SignalStateStore:
    """Atomic persisted state for one-shot signal transitions."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _process_lock(self, timeout: float = 5.0):
        deadline, descriptor = time.monotonic() + timeout, None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while descriptor is None:
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                try:
                    if time.time() - self.lock_path.stat().st_mtime > 120:
                        self.lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("signal state process lock timeout")
                time.sleep(.04)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def compare_and_store(self, states: dict[str, dict]) -> list[dict]:
        with self._lock:
            with self._process_lock():
                previous = self._read()
                changes = []
                for key, current in states.items():
                    old = previous.get(key)
                    if old and old.get("state") != current.get("state"):
                        changes.append({"key": key, "from": old.get("state"), "to": current.get("state"), "asOf": current.get("asOf"), "source": current.get("source")})
                merged = {**previous, **states}
                temporary = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
                temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
                os.replace(temporary, self.path)
                return changes
