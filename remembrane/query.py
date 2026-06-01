from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remembrane.record import MembraneRecord


def filter_records(
    records: list["MembraneRecord"],
    lipid: str | list[str] | None = None,
    min_fraction: tuple[str, float] | None = None,
    max_fraction: tuple[str, float] | None = None,
    force_field: str | None = None,
    temperature_K: float | None = None,
    tags: list[str] | None = None,
) -> list["MembraneRecord"]:
    if isinstance(lipid, str):
        lipid = [lipid]

    result = []
    for rec in records:
        if lipid and not _has_all_lipids(rec, lipid):
            continue
        if min_fraction and not _fraction_gte(rec, *min_fraction):
            continue
        if max_fraction and not _fraction_lte(rec, *max_fraction):
            continue
        if force_field and rec.composition.force_field != force_field:
            continue
        if temperature_K and abs(rec.composition.temperature_K - temperature_K) > 0.01:
            continue
        if tags and not all(t in rec.tags for t in tags):
            continue
        result.append(rec)
    return result


def _all_lipids(record: "MembraneRecord") -> dict[str, float]:
    totals: dict[str, float] = {}
    for leaflet in (record.composition.upper_leaflet, record.composition.lower_leaflet):
        for name, entry in leaflet.lipids.items():
            totals[name] = totals.get(name, 0.0) + entry.fraction
    return totals


def _has_all_lipids(record: "MembraneRecord", names: list[str]) -> bool:
    present = _all_lipids(record)
    return all(n in present for n in names)


def _fraction_gte(record: "MembraneRecord", lipid: str, threshold: float) -> bool:
    totals = _all_lipids(record)
    return totals.get(lipid, 0.0) >= threshold


def _fraction_lte(record: "MembraneRecord", lipid: str, threshold: float) -> bool:
    totals = _all_lipids(record)
    return totals.get(lipid, 0.0) <= threshold
