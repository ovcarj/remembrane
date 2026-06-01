import shutil
from pathlib import Path

import pytest

from remembrane.record import MembraneRecord
from remembrane.registry import Registry, DuplicateRecordError, RecordNotFoundError

FIXTURE = Path(__file__).parent / "fixtures" / "example_record" / "metadata.yaml"


def test_init_creates_structure(tmp_path):
    reg = Registry.init(tmp_path / "db")
    assert (tmp_path / "db" / "config.yaml").exists()
    assert (tmp_path / "db" / "records").exists()
    assert (tmp_path / "db" / "index.json").exists()


def test_open_uninitialized_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Registry.open(tmp_path / "nonexistent")


def test_add_and_get(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec)
    retrieved = reg.get(str(rec.id))
    assert retrieved.scientific_hash == rec.scientific_hash


def test_list_records(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec)
    records = reg.list()
    assert len(records) == 1


def test_duplicate_rejected(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec)
    rec2 = MembraneRecord.from_yaml(FIXTURE)
    with pytest.raises(DuplicateRecordError):
        reg.add(rec2)


def test_get_nonexistent_raises(tmp_path):
    reg = Registry.init(tmp_path / "db")
    with pytest.raises(RecordNotFoundError):
        reg.get("00000000-0000-0000-0000-000000000099")


def test_record_dir_accessible(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    record_dir = reg.add(rec)
    assert record_dir.exists()
    assert (record_dir / "metadata.yaml").exists()
