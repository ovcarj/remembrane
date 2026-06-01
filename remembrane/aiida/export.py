from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def export_provenance_archive(wc_uuid: str, output_path: str | Path) -> None:
    """Export a complete AiiDA provenance archive for a workchain UUID.

    Calls `verdi archive create` (AiiDA ≥2.0 CLI).
    """
    output_path = Path(output_path)
    cmd = [
        sys.executable, "-m", "aiida.cmdline",
        "archive", "create",
        "--all",
        "-n", wc_uuid,
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"verdi archive create failed:\n{result.stdout}\n{result.stderr}"
        )
