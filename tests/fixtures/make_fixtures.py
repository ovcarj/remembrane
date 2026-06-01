"""Run once to create example_record/*.npz files and patch their checksums into metadata.yaml."""
import hashlib
from pathlib import Path

import numpy as np
import yaml

FIXTURE_DIR = Path(__file__).parent / "example_record"

z = np.linspace(0, 7.5, 100)
phi_total = np.sin(2 * np.pi * z / 7.5) * 0.5

np.savez_compressed(FIXTURE_DIR / "potential_total.npz", z_nm=z, phi_V=phi_total)
np.savez_compressed(
    FIXTURE_DIR / "potential_components.npz",
    z_nm=z,
    MEMB=phi_total * 0.7,
    Water=phi_total * 0.2,
    ION=phi_total * 0.1,
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


meta_path = FIXTURE_DIR / "metadata.yaml"
meta = yaml.safe_load(meta_path.read_text())
meta["artifacts"]["potential_total"]["sha256"] = sha256(FIXTURE_DIR / "potential_total.npz")
meta["artifacts"]["potential_components"]["sha256"] = sha256(FIXTURE_DIR / "potential_components.npz")
meta_path.write_text(yaml.dump(meta, default_flow_style=False, allow_unicode=True))
print("Fixtures created and checksums patched.")
