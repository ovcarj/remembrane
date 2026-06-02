from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import yaml

if TYPE_CHECKING:
    from remembrane.record import MembraneRecord


class DuplicateRecordError(Exception):
    pass


class RecordNotFoundError(Exception):
    pass


class Registry:
    def __init__(self, path: Path):
        self._path = Path(path).expanduser()
        self._records_dir = self._path / "records"
        self._index_path = self._path / "index.json"

    @classmethod
    def open(cls, path: str | Path) -> "Registry":
        p = Path(path).expanduser()
        if not (p / "config.yaml").exists():
            raise FileNotFoundError(
                f"{p} is not an initialized remembrane database. Run 'remembrane init'."
            )
        return cls(p)

    @classmethod
    def init(cls, path: str | Path) -> "Registry":
        p = Path(path).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        (p / "records").mkdir(exist_ok=True)
        config = {"schema_version": "0.1.0", "backend": "directory"}
        (p / "config.yaml").write_text(yaml.dump(config))
        if not (p / "index.json").exists():
            (p / "index.json").write_text(json.dumps({}))
        return cls(p)

    def add(self, record: "MembraneRecord") -> Path:
        index = self._load_index()
        if record.scientific_hash in index.values():
            existing_id = next(k for k, v in index.items() if v == record.scientific_hash)
            raise DuplicateRecordError(
                f"Record with identical scientific content already exists: {existing_id}"
            )

        record_dir = self._records_dir / str(record.id)
        record_dir.mkdir(parents=True, exist_ok=True)
        record.to_yaml(record_dir / "metadata.yaml")

        index[str(record.id)] = record.scientific_hash
        self._save_index(index)
        return record_dir

    def get(self, record_id: str | UUID) -> "MembraneRecord":
        from remembrane.record import MembraneRecord
        record_dir = self._records_dir / str(record_id)
        if not record_dir.exists():
            raise RecordNotFoundError(f"No record with id {record_id}")
        return MembraneRecord.from_yaml(record_dir / "metadata.yaml")

    def record_dir(self, record_id: str | UUID) -> Path:
        return self._records_dir / str(record_id)

    def list(self) -> list["MembraneRecord"]:
        from remembrane.record import MembraneRecord
        records = []
        for d in sorted(self._records_dir.iterdir()):
            if d.is_dir() and (d / "metadata.yaml").exists():
                records.append(MembraneRecord.from_yaml(d / "metadata.yaml"))
        return records

    def rebuild_index(self) -> dict:
        """Scan all record directories and rebuild index.json from metadata.yaml files.

        Useful when index.json is corrupted, missing, or out of sync with disk.
        Returns the new {record_id: scientific_hash} mapping that was written.
        """
        from remembrane.record import MembraneRecord
        index: dict = {}
        if self._records_dir.exists():
            for d in sorted(self._records_dir.iterdir()):
                meta = d / "metadata.yaml"
                if d.is_dir() and meta.exists():
                    try:
                        rec = MembraneRecord.from_yaml(meta)
                        index[str(rec.id)] = rec.scientific_hash
                    except Exception as exc:
                        import warnings
                        warnings.warn(f"Skipping unreadable record at {meta}: {exc}")
        self._save_index(index)
        return index

    def _load_index(self) -> dict:
        if self._index_path.exists():
            return json.loads(self._index_path.read_text())
        return {}

    def _save_index(self, index: dict) -> None:
        self._index_path.write_text(json.dumps(index, indent=2))
