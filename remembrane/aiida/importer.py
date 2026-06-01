from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path
from typing import Any


class ImportIncompleteError(Exception):
    def __init__(
        self,
        missing_fields: list[str] | None = None,
        missing_artifacts: list[str] | None = None,
        diagnostics: list[str] | None = None,
    ):
        self.missing_fields = missing_fields or []
        self.missing_artifacts = missing_artifacts or []
        self.diagnostics = diagnostics or []

    def __str__(self) -> str:
        lines = []
        if self.missing_fields:
            lines.append("  missing_fields:")
            lines.extend(f"    - {f}" for f in self.missing_fields)
        if self.missing_artifacts:
            lines.append("  missing_artifacts:")
            lines.extend(f"    - {a}" for a in self.missing_artifacts)
        if self.diagnostics:
            lines.append("  diagnostics:")
            lines.extend(f"    - {d}" for d in self.diagnostics)
        return "\n".join(lines)


def from_potential_workchain(
    uuid_or_pk: str | int,
) -> tuple[Any, dict]:
    """Import a MembraneRecord from a ComputeMembranePotentialWorkChain node.

    Returns (MembraneRecord, arrays) where arrays contains:
      z_nm, phi_V, components: dict[str, ndarray]

    Raises ImportIncompleteError if provenance is incomplete.
    Raises ImportError if aiida-core is not installed.
    """
    try:
        from aiida import orm
        from aiida.manage import get_manager
    except ImportError as exc:
        raise ImportError(
            "aiida-core is required for AiiDA import. "
            "Install it with: pip install remembrane[aiida]"
        ) from exc

    import numpy as np
    from remembrane.parsers.xvg import parse_xvg
    from remembrane.record import (
        AiidaRefs, ArtifactEntry, Artifacts, Composition, FileHash,
        Leaflet, LipidCount, MembraneRecord, PotentialMeta, SoftwareVersions,
    )

    missing_fields: list[str] = []
    missing_artifacts: list[str] = []
    diagnostics: list[str] = []

    # Load the workchain node
    node = orm.load_node(uuid_or_pk)
    wc_uuid = str(node.uuid)

    # ── Potential metadata ──────────────────────────────────────────────────
    if "potential_report" not in node.outputs:
        missing_fields.append("potential_meta")
        diagnostics.append("potential_report output missing from workchain node")
    else:
        report = node.outputs.potential_report.get_dict()

    if "potential_profile" not in node.outputs:
        missing_artifacts.append("potential_total.npz (source: potential_profile xvg)")
        diagnostics.append("potential_profile output missing")

    # ── Walk provenance graph ───────────────────────────────────────────────
    run_md_uuid = None
    build_membrane_uuid = None
    run_md_node = None
    build_node = None

    caller = node.caller
    while caller is not None:
        label = caller.process_label or ""
        if "RunMembraneMDWorkChain" in label and run_md_uuid is None:
            run_md_uuid = str(caller.uuid)
            run_md_node = caller
        if "BuildMembraneWorkChain" in label and build_membrane_uuid is None:
            build_membrane_uuid = str(caller.uuid)
            build_node = caller
        caller = caller.caller if hasattr(caller, "caller") else None

    if build_node is None:
        diagnostics.append("BuildMembraneWorkChain not found in provenance graph")

    # ── Composition ─────────────────────────────────────────────────────────
    composition = None
    protocols_charmm = None
    if build_node is not None:
        try:
            system_meta = build_node.outputs.system_metadata.get_dict()
            protocols_charmm = build_node.inputs.protocol.get_dict() if hasattr(build_node.inputs, "protocol") else None
            composition = _extract_composition(system_meta, protocols_charmm)
        except Exception as exc:
            missing_fields.append("composition")
            diagnostics.append(f"Failed to extract composition from BuildMembraneWorkChain: {exc}")
    else:
        missing_fields.append("composition")
        missing_fields.append("protocols.charmm_gui")

    # ── MD protocol ─────────────────────────────────────────────────────────
    protocols_md = None
    if run_md_node is not None and hasattr(run_md_node.inputs, "protocol"):
        protocols_md = run_md_node.inputs.protocol.get_dict()
    else:
        if run_md_uuid is None:
            diagnostics.append("RunMembraneMDWorkChain not found in provenance graph")

    # ── Potential protocol ───────────────────────────────────────────────────
    protocols_potential = None
    if hasattr(node.inputs, "protocol"):
        protocols_potential = node.inputs.protocol.get_dict()
    else:
        missing_fields.append("protocols.potential")

    # ── Source file hashes ───────────────────────────────────────────────────
    source_files: dict[str, FileHash] = {}
    for attr_name, key in [
        ("tpr_file", "tpr"),
        ("trajectory", "xtc"),
    ]:
        if hasattr(node.inputs, attr_name):
            node_obj = getattr(node.inputs, attr_name)
            sha = _hash_singlefile_node(node_obj)
            if sha:
                source_files[key] = FileHash(sha256=sha)

    # ── Software versions ───────────────────────────────────────────────────
    software = _collect_software_versions()

    # ── Fail if anything critical is missing ────────────────────────────────
    if missing_fields or missing_artifacts:
        raise ImportIncompleteError(missing_fields, missing_artifacts, diagnostics)

    # ── Parse XVG data ──────────────────────────────────────────────────────
    total_path = node.outputs.potential_profile.get_content()
    if isinstance(total_path, bytes):
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix=".xvg", delete=False)
        tmp.write(total_path)
        tmp.close()
        z_nm, phi_V = parse_xvg(tmp.name)
        os.unlink(tmp.name)
    else:
        z_nm, phi_V = parse_xvg(total_path)

    components: dict[str, np.ndarray] = {}
    if hasattr(node.outputs, "potential_components"):
        for label, comp_node in node.outputs.potential_components.items():
            content = comp_node.get_content()
            if isinstance(content, bytes):
                import tempfile, os
                tmp = tempfile.NamedTemporaryFile(suffix=".xvg", delete=False)
                tmp.write(content)
                tmp.close()
                _, phi = parse_xvg(tmp.name)
                os.unlink(tmp.name)
            else:
                _, phi = parse_xvg(content)
            components[label] = phi

    # ── Assemble record ──────────────────────────────────────────────────────
    pot_meta = PotentialMeta(
        axis=report.get("axis", "z"),
        slices=report.get("slices", 0),
        charge_group=report.get("charge_group", ""),
        component_groups=report.get("component_groups", []),
        symmetrize=report.get("symmetrize", False),
        correct=report.get("correct", True),
        source_tool=report.get("source_tool", "gmx potential"),
    )

    artifacts = Artifacts(
        potential_total=ArtifactEntry(path="potential_total.npz", sha256="", units={"z": "nm", "phi": "V"}),
        potential_components=ArtifactEntry(path="potential_components.npz", sha256=""),
    )

    aiida_refs = AiidaRefs(
        profile=_current_profile_name(),
        build_membrane_wc=build_membrane_uuid,
        run_md_wc=run_md_uuid,
        compute_potential_wc=wc_uuid,
    )

    record = MembraneRecord(
        composition=composition,
        protocols={
            "charmm_gui": protocols_charmm or {},
            "md": protocols_md or {},
            "potential": protocols_potential or {},
        },
        potential_meta=pot_meta,
        artifacts=artifacts,
        source_files=source_files,
        software=software,
        aiida_refs=aiida_refs,
    )

    arrays = {
        "z_nm": z_nm,
        "phi_V": phi_V,
        "components": components,
    }
    return record, arrays


def _extract_composition(system_meta: dict, protocol: dict | None):
    from remembrane.record import Composition, Leaflet, LipidCount

    charmm_params = (protocol or {}).get("charmm_gui", {}).get("quick_bilayer", {})
    upper_str = charmm_params.get("upper", "")
    lower_str = charmm_params.get("lower", "")

    upper = _parse_lipid_ratio(upper_str)
    lower = _parse_lipid_ratio(lower_str)

    return Composition(
        upper_leaflet=Leaflet(lipids=upper),
        lower_leaflet=Leaflet(lipids=lower),
        force_field=system_meta.get("force_field", "CHARMM36"),
        water_model=system_meta.get("water_model", "TIP3"),
        temperature_K=float(charmm_params.get("temperature", system_meta.get("temperature_K", 310.15))),
        ion_type=charmm_params.get("ion_type", system_meta.get("ion_type", "")),
        ion_conc_M=float(charmm_params.get("ion_conc", system_meta.get("ion_conc_M", 0.0))),
    )


def _parse_lipid_ratio(spec: str) -> dict:
    """Parse 'POPE:POPC:CDL2=40:40:20' into {POPE: LipidCount(...), ...}."""
    from remembrane.record import LipidCount
    if not spec or "=" not in spec:
        return {}
    names_part, counts_part = spec.split("=", 1)
    names = [n.strip() for n in names_part.split(":")]
    counts = [int(c.strip()) for c in counts_part.split(":")]
    total = sum(counts)
    return {
        name: LipidCount(count=count, fraction=round(count / total, 6))
        for name, count in zip(names, counts)
    }


def _hash_singlefile_node(node) -> str | None:
    try:
        content = node.get_content(mode="rb")
        return hashlib.sha256(content).hexdigest()
    except Exception:
        return None


def _collect_software_versions() -> Any:
    from remembrane.record import SoftwareVersions
    import importlib.metadata as meta

    def _ver(pkg: str) -> str | None:
        try:
            return meta.version(pkg)
        except meta.PackageNotFoundError:
            return None

    return SoftwareVersions(
        remembrane_version=_ver("remembrane") or "unknown",
        tracy_version=_ver("tracy"),
        gromacs_version=None,  # extracted from AiiDA node extras when available
        aiida_core_version=_ver("aiida-core"),
        aiida_gromacs_version=_ver("aiida-gromacs"),
        python_version=platform.python_version(),
    )


def _current_profile_name() -> str | None:
    try:
        from aiida.manage import get_manager
        return get_manager().get_profile().name
    except Exception:
        return None
