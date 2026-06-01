import pytest
from pathlib import Path
from remembrane.record import MembraneRecord, SCHEMA_VERSION

FIXTURE = Path(__file__).parent / "fixtures" / "example_record" / "metadata.yaml"


def test_load_from_yaml():
    rec = MembraneRecord.from_yaml(FIXTURE)
    assert rec.schema_version == SCHEMA_VERSION
    assert rec.composition.force_field == "CHARMM36"
    assert rec.composition.upper_leaflet.lipids["CDL2"].count == 20
    assert rec.composition.upper_leaflet.lipids["CDL2"].fraction == pytest.approx(0.2)
    assert rec.potential_meta.axis == "z"
    assert rec.potential_meta.slices == 100
    assert "MEMB" in rec.potential_meta.component_groups


def test_scientific_hash_is_deterministic():
    rec1 = MembraneRecord.from_yaml(FIXTURE)
    rec2 = MembraneRecord.from_yaml(FIXTURE)
    assert rec1.scientific_hash == rec2.scientific_hash
    assert len(rec1.scientific_hash) == 64


def test_scientific_hash_changes_with_composition():
    rec = MembraneRecord.from_yaml(FIXTURE)
    # Modify composition
    rec2_data = rec.model_dump()
    rec2_data["scientific_hash"] = ""
    rec2_data["composition"]["upper_leaflet"]["lipids"]["CDL2"]["count"] = 10
    rec2_data["composition"]["upper_leaflet"]["lipids"]["CDL2"]["fraction"] = 0.1
    rec2 = MembraneRecord.model_validate(rec2_data)
    assert rec.scientific_hash != rec2.scientific_hash


def test_roundtrip_yaml(tmp_path):
    rec = MembraneRecord.from_yaml(FIXTURE)
    out = tmp_path / "metadata.yaml"
    rec.to_yaml(out)
    rec2 = MembraneRecord.from_yaml(out)
    assert rec.scientific_hash == rec2.scientific_hash
    assert str(rec.id) == str(rec2.id)
