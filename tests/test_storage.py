from pathlib import Path

import numpy as np
import pytest

from remembrane.storage import (
    save_potential_total,
    load_potential_total,
    save_potential_components,
    load_potential_components,
    verify_artifact,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "example_record"


def test_save_load_total(tmp_path):
    z = np.linspace(0, 7.5, 50)
    phi = np.sin(z)
    sha = save_potential_total(tmp_path, z, phi)
    assert len(sha) == 64
    z2, phi2 = load_potential_total(tmp_path)
    np.testing.assert_array_almost_equal(z, z2)
    np.testing.assert_array_almost_equal(phi, phi2)


def test_save_load_components(tmp_path):
    z = np.linspace(0, 7.5, 50)
    comps = {"MEMB": z * 0.1, "Water": z * 0.05}
    sha = save_potential_components(tmp_path, comps, z)
    assert len(sha) == 64
    loaded = load_potential_components(tmp_path)
    np.testing.assert_array_almost_equal(loaded["MEMB"], comps["MEMB"])
    np.testing.assert_array_almost_equal(loaded["z_nm"], z)


def test_verify_artifact_passes(tmp_path):
    z = np.linspace(0, 7.5, 50)
    phi = np.zeros(50)
    sha = save_potential_total(tmp_path, z, phi)
    assert verify_artifact(tmp_path, "potential_total.npz", sha)


def test_verify_artifact_fails_wrong_hash(tmp_path):
    z = np.linspace(0, 7.5, 50)
    phi = np.zeros(50)
    save_potential_total(tmp_path, z, phi)
    assert not verify_artifact(tmp_path, "potential_total.npz", "a" * 64)


def test_verify_artifact_missing_file(tmp_path):
    assert not verify_artifact(tmp_path, "potential_total.npz", "a" * 64)


def test_fixture_checksums_valid():
    """Fixture .npz files match their recorded checksums in metadata.yaml."""
    import yaml
    meta = yaml.safe_load((FIXTURE_DIR / "metadata.yaml").read_text())
    for artifact_key in ["potential_total", "potential_components"]:
        info = meta["artifacts"][artifact_key]
        assert verify_artifact(FIXTURE_DIR, info["path"], info["sha256"]), \
            f"Checksum mismatch for {artifact_key}"
