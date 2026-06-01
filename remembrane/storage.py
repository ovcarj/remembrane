from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def save_potential_total(directory: Path, z_nm: np.ndarray, phi_V: np.ndarray) -> str:
    path = directory / "potential_total.npz"
    np.savez_compressed(path, z_nm=z_nm, phi_V=phi_V)
    return _sha256(path)


def load_potential_total(directory: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(directory / "potential_total.npz")
    return data["z_nm"], data["phi_V"]


def save_potential_components(directory: Path, components: dict[str, np.ndarray],
                               z_nm: np.ndarray) -> str:
    path = directory / "potential_components.npz"
    np.savez_compressed(path, z_nm=z_nm, **components)
    return _sha256(path)


def load_potential_components(directory: Path) -> dict[str, np.ndarray]:
    data = np.load(directory / "potential_components.npz")
    return dict(data)


def verify_artifact(directory: Path, filename: str, expected_sha256: str) -> bool:
    path = directory / filename
    if not path.exists():
        return False
    return _sha256(path) == expected_sha256


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
