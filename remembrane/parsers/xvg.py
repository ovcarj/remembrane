from __future__ import annotations

from pathlib import Path

import numpy as np


def parse_xvg(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse a GROMACS .xvg file and return (x, y) as numpy arrays.

    Skips lines starting with '#' (comments) and '@' (GRACE directives).
    Handles optional error columns (takes only first two data columns).
    Returns arrays in the units present in the file (typically nm, V).
    """
    x_vals, y_vals = [], []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "@")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            continue
        x_vals.append(x)
        y_vals.append(y)
    return np.array(x_vals, dtype=float), np.array(y_vals, dtype=float)
