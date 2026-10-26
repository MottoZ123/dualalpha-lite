from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


SAFE_FORMULA = re.compile(r"^[A-Za-z0-9_+\-*/()., <>=]{3,240}$")


class ResearchRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._schema()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _schema(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS factor_versions(
                    id TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL,
                    family TEXT NOT NULL, track TEXT NOT NULL, formula TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(id, version)
                );
                CREATE TABLE IF NOT EXISTS model_releases(
                    id TEXT PRIMARY KEY, engine TEXT NOT NULL, job_id TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    retired_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_factor_versions_latest ON factor_versions(id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_model_releases_engine_status ON model_releases(engine, status, created_at DESC);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(model_releases)")}
            if "artifact_sha256" not in columns:
                db.execute("ALTER TABLE model_releases ADD COLUMN artifact_sha256 TEXT")
            if "metadata_json" not in columns:
                db.execute("ALTER TABLE model_releases ADD COLUMN metadata_json TEXT")
            db.execute("PRAGMA optimize")

    def factors(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM factor_versions ORDER BY id, version DESC")]

    def latest_factor_formulas(self):
        with self._connect() as db:
            rows = db.execute("""SELECT f.id, f.formula FROM factor_versions f JOIN (SELECT id, MAX(version) version FROM factor_versions GROUP BY id) latest ON latest.id=f.id AND latest.version=f.version""")
            return {row["id"]: row["formula"] for row in rows}

    def create_factor(self, payload: dict):
        factor_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or factor_id).strip()
        formula = str(payload.get("formula") or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,63}", factor_id):
            raise ValueError("factor id must be a safe identifier")
        if not SAFE_FORMULA.fullmatch(formula):
            raise ValueError("formula contains unsupported characters; arbitrary code is forbidden")
        with self._connect() as db:
            latest = db.execute("SELECT COALESCE(MAX(version),0) FROM factor_versions WHERE id=?", (factor_id,)).fetchone()[0]
            version = int(latest) + 1
            record = {"id": factor_id, "version": version, "name": name[:80], "family": str(payload.get("family") or "custom")[:40], "track": str(payload.get("track") or "shared")[:16], "formula": formula, "description": str(payload.get("description") or "")[:320], "status": "draft", "created_at": datetime.now(timezone.utc).isoformat()}
            db.execute("INSERT INTO factor_versions VALUES(:id,:version,:name,:family,:track,:formula,:description,:status,:created_at)", record)
        return record

    def model_releases(self):
        with self._connect() as db:
            records = [dict(row) for row in db.execute("SELECT * FROM model_releases ORDER BY created_at DESC")]
            for record in records:
                record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
            return records

    @staticmethod
    def _artifact_hash(directory: Path) -> str:
        digest = hashlib.sha256()
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        if not files:
            raise ValueError("training artifact directory contains no files")
        for path in files:
            digest.update(str(path.relative_to(directory)).replace("\\", "/").encode("utf-8"))
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    def active_release(self, engine: str):
        if engine not in {"tx", "bs"}:
            raise ValueError("engine must be tx or bs")
        with self._connect() as db:
            row = db.execute("SELECT * FROM model_releases WHERE engine=? AND status='active' ORDER BY created_at DESC LIMIT 1", (engine,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
            return result

    def promote(self, engine: str, job: dict):
        if engine not in {"tx", "bs"} or job.get("mode") != "training" or job.get("status") != "completed":
            raise ValueError("only a completed training job can be promoted")
        job_root = Path(str(job.get("output_dir") or ""))
        if not str(job_root):
            raise ValueError("training artifact directory is missing")
        engine_root = job_root / engine
        artifact_root = engine_root if engine_root.is_dir() else job_root
        if not artifact_root.is_dir():
            raise ValueError("training artifact directory does not exist")
        artifact_hash = self._artifact_hash(artifact_root)
        metadata = {"dataVersion": (job.get("results") or {}).get(engine, {}).get("dataVersion"), "jobCreatedAt": job.get("created_at"), "jobCompletedAt": job.get("completed_at")}
        now, release_id = datetime.now(timezone.utc).isoformat(), uuid.uuid4().hex
        with self._connect() as db:
            db.execute("UPDATE model_releases SET status='retired', retired_at=? WHERE engine=? AND status='active'", (now, engine))
            db.execute("INSERT INTO model_releases(id,engine,job_id,artifact_dir,status,created_at,retired_at,artifact_sha256,metadata_json) VALUES(?,?,?,?,?,?,NULL,?,?)", (release_id, engine, job["id"], str(artifact_root), "active", now, artifact_hash, json.dumps(metadata, ensure_ascii=False)))
        return {"id": release_id, "engine": engine, "job_id": job["id"], "artifact_dir": str(artifact_root), "artifact_sha256": artifact_hash, "metadata": metadata, "status": "active", "created_at": now}

    def rollback(self, engine: str):
        with self._connect() as db:
            releases = list(db.execute("SELECT * FROM model_releases WHERE engine=? ORDER BY created_at DESC LIMIT 2", (engine,)))
            if len(releases) < 2:
                raise ValueError("no previous model release is available")
            now = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE model_releases SET status='retired', retired_at=? WHERE id=?", (now, releases[0]["id"]))
            db.execute("UPDATE model_releases SET status='active', retired_at=NULL WHERE id=?", (releases[1]["id"],))
            return dict(db.execute("SELECT * FROM model_releases WHERE id=?", (releases[1]["id"],)).fetchone())


def resolve_active_model_dir(engine: str, variant: str, default: str | Path) -> str:
    """Resolve the model directory actually used by daily inference."""
    data_root = Path(os.getenv("RESEARCH_DATA_DIR", "").strip() or (Path.home() / ".quant-research")).expanduser()
    registry_path = data_root / "motto-research.sqlite3"
    if not registry_path.exists():
        return os.fspath(default)
    release = ResearchRegistry(registry_path).active_release(engine)
    if not release:
        return os.fspath(default)
    root = Path(release["artifact_dir"])
    candidate = root / variant
    resolved = candidate if candidate.is_dir() else root
    if not resolved.is_dir() or not any(path.is_file() for path in resolved.iterdir()):
        raise RuntimeError(f"active {engine} model release is missing or empty: {resolved}")
    return os.fspath(resolved)
