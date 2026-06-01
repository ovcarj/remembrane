from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remembrane.record import MembraneRecord


def records_to_json(records: list["MembraneRecord"], indent: int = 2) -> str:
    """Serialize a list of records to a JSON string."""
    import json as _json
    return _json.dumps(
        [json.loads(r.model_dump_json()) for r in records],
        indent=indent,
        default=str,
    )


def records_to_csv(records: list["MembraneRecord"]) -> str:
    """Flatten records to CSV rows.

    Each row contains: id, scientific_hash, force_field, temperature_K,
    ion_type, ion_conc_M, water_model, upper_leaflet (per-lipid columns),
    lower_leaflet (per-lipid columns), potential_axis, potential_slices,
    charge_group, component_groups, tags.

    Lipid columns are dynamically generated from all lipids present across
    all records, with fractional values (e.g. upper_POPC_fraction).
    """
    if not records:
        return ""

    all_lipids: set[str] = set()
    for rec in records:
        all_lipids.update(rec.composition.upper_leaflet.lipids)
        all_lipids.update(rec.composition.lower_leaflet.lipids)
    sorted_lipids = sorted(all_lipids)

    header = [
        "id", "scientific_hash", "force_field", "temperature_K",
        "ion_type", "ion_conc_M", "water_model",
    ]
    for leaflet in ("upper", "lower"):
        for lipid in sorted_lipids:
            header.append(f"{leaflet}_{lipid}_count")
            header.append(f"{leaflet}_{lipid}_fraction")
    header += ["potential_axis", "potential_slices", "charge_group", "component_groups", "tags"]

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore")
    writer.writeheader()

    for rec in records:
        row: dict = {
            "id": str(rec.id),
            "scientific_hash": rec.scientific_hash,
            "force_field": rec.composition.force_field,
            "temperature_K": rec.composition.temperature_K,
            "ion_type": rec.composition.ion_type,
            "ion_conc_M": rec.composition.ion_conc_M,
            "water_model": rec.composition.water_model,
            "potential_axis": rec.potential_meta.axis,
            "potential_slices": rec.potential_meta.slices,
            "charge_group": rec.potential_meta.charge_group,
            "component_groups": ";".join(rec.potential_meta.component_groups),
            "tags": ";".join(rec.tags),
        }
        for leaflet_attr, prefix in [
            ("upper_leaflet", "upper"),
            ("lower_leaflet", "lower"),
        ]:
            lipids = getattr(rec.composition, leaflet_attr).lipids
            for lipid in sorted_lipids:
                entry = lipids.get(lipid)
                row[f"{prefix}_{lipid}_count"] = entry.count if entry else 0
                row[f"{prefix}_{lipid}_fraction"] = entry.fraction if entry else 0.0
        writer.writerow(row)

    return buf.getvalue()
