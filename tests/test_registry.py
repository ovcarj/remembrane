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


def test_rebuild_index_from_clean_state(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec)
    # Wipe the index
    reg._index_path.write_text("{}")
    assert reg._load_index() == {}
    # Rebuild
    new_index = reg.rebuild_index()
    assert str(rec.id) in new_index
    assert new_index[str(rec.id)] == rec.scientific_hash


def test_rebuild_index_corrects_corrupted_hash(tmp_path):
    reg = Registry.init(tmp_path / "db")
    rec = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec)
    # Corrupt the index with a wrong hash
    reg._save_index({str(rec.id): "wrong_hash"})
    new_index = reg.rebuild_index()
    assert new_index[str(rec.id)] == rec.scientific_hash


def test_rebuild_index_ignores_dirs_without_metadata(tmp_path):
    reg = Registry.init(tmp_path / "db")
    # Create a stray directory with no metadata.yaml
    stray = reg._records_dir / "stray-dir"
    stray.mkdir()
    new_index = reg.rebuild_index()
    assert len(new_index) == 0


def test_rebuild_index_multiple_records(tmp_path):
    import uuid
    from remembrane.record import MembraneRecord
    reg = Registry.init(tmp_path / "db")
    rec1 = MembraneRecord.from_yaml(FIXTURE)
    reg.add(rec1)
    # Add a second record with a different id by patching
    rec2_data = rec1.model_dump()
    rec2_data["id"] = str(uuid.uuid4())
    rec2_data["scientific_hash"] = ""
    rec2_data["notes"] = "second record"
    rec2 = MembraneRecord.model_validate(rec2_data)
    # Write manually to a new directory (bypassing dedup on same hash)
    d = reg._records_dir / str(rec2.id)
    d.mkdir()
    rec2.to_yaml(d / "metadata.yaml")

    new_index = reg.rebuild_index()
    assert len(new_index) == 2
