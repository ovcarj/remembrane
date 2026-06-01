from pathlib import Path

from remembrane.record import MembraneRecord
from remembrane.query import filter_records

FIXTURE = Path(__file__).parent / "fixtures" / "example_record" / "metadata.yaml"


def _rec():
    return MembraneRecord.from_yaml(FIXTURE)


def test_filter_by_lipid_present():
    results = filter_records([_rec()], lipid="CDL2")
    assert len(results) == 1


def test_filter_by_lipid_absent():
    results = filter_records([_rec()], lipid="DPPC")
    assert len(results) == 0


def test_filter_multiple_lipids():
    results = filter_records([_rec()], lipid=["POPE", "CDL2"])
    assert len(results) == 1


def test_filter_min_fraction_pass():
    # CDL2 total fraction across both leaflets = 0.2 + 0.2 = 0.4 (sum, not average)
    results = filter_records([_rec()], min_fraction=("CDL2", 0.3))
    assert len(results) == 1


def test_filter_min_fraction_fail():
    results = filter_records([_rec()], min_fraction=("CDL2", 0.9))
    assert len(results) == 0


def test_filter_force_field():
    results = filter_records([_rec()], force_field="CHARMM36")
    assert len(results) == 1
    results = filter_records([_rec()], force_field="AMBER")
    assert len(results) == 0


def test_filter_temperature():
    results = filter_records([_rec()], temperature_K=310.15)
    assert len(results) == 1
    results = filter_records([_rec()], temperature_K=300.0)
    assert len(results) == 0


def test_filter_tag():
    results = filter_records([_rec()], tags=["cardiolipin"])
    assert len(results) == 1
    results = filter_records([_rec()], tags=["missing_tag"])
    assert len(results) == 0
