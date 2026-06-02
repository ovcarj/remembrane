from __future__ import annotations

import hashlib
import platform
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
    uuid_or_pk: str | int | None = None,
    build_membrane_pk: int | None = None,
    run_md_pk: int | None = None,
    *,
    pk: int | None = None,
    uuid: str | None = None,
) -> tuple[Any, dict]:
    """Import a MembraneRecord from a ComputeMembranePotentialWorkChain node.

    Accepts the workchain identifier as a positional argument or as pk=/uuid=:
      from_potential_workchain(1894)
      from_potential_workchain(pk=1894)
      from_potential_workchain(uuid="abc-...")

    Returns (MembraneRecord, arrays) where arrays has keys:
      z_nm, phi_V, components: dict[str, ndarray]

    build_membrane_pk / run_md_pk: explicit PKs for ancestor workchains when
    they are not in the automatic provenance graph (e.g. standalone submissions).

    Raises ImportIncompleteError if required fields cannot be resolved.
    Raises ImportError if aiida-core is not installed.
    """
    if pk is not None:
        uuid_or_pk = pk
    elif uuid is not None:
        uuid_or_pk = uuid
    if uuid_or_pk is None:
        raise ValueError("Provide the workchain identifier as a positional argument, pk=, or uuid=")
    try:
        import aiida
        from aiida import orm
    except ImportError as exc:
        raise ImportError(
            "aiida-core is required for AiiDA import. "
            "Install it with: pip install remembrane[aiida]"
        ) from exc

    try:
        aiida.load_profile()
    except Exception:
        pass  # profile already loaded, or using a custom manager

    import numpy as np
    from remembrane.parsers.xvg import parse_xvg
    from remembrane.record import (
        AiidaRefs, ArtifactEntry, Artifacts, Composition, FileHash,
        Leaflet, LipidCount, MembraneRecord, PotentialMeta, SoftwareVersions,
    )

    missing_fields: list[str] = []
    missing_artifacts: list[str] = []
    diagnostics: list[str] = []

    node = orm.load_node(uuid_or_pk)
    wc_uuid = str(node.uuid)

    # ── Potential metadata ──────────────────────────────────────────────────
    if "potential_report" not in node.outputs:
        missing_fields.append("potential_meta")
        diagnostics.append("potential_report output missing from workchain node")
        report = {}
    else:
        report = node.outputs.potential_report.get_dict()

    if "potential_profile" not in node.outputs:
        missing_artifacts.append("potential_total.npz (source: potential_profile xvg)")
        diagnostics.append("potential_profile output missing")

    # ── Walk provenance graph, then fall back to explicit PKs ───────────────
    run_md_node = None
    build_node = None
    run_md_uuid = None
    build_membrane_uuid = None

    # Auto-walk caller chain
    caller = node.caller
    while caller is not None:
        label = getattr(caller, "process_label", "") or ""
        if "RunMembraneMDWorkChain" in label and run_md_node is None:
            run_md_node = caller
            run_md_uuid = str(caller.uuid)
        if "BuildMembraneWorkChain" in label and build_node is None:
            build_node = caller
            build_membrane_uuid = str(caller.uuid)
        caller = caller.caller if hasattr(caller, "caller") else None

    # Fall back to explicit PKs when not in graph
    if run_md_node is None and run_md_pk is not None:
        run_md_node = orm.load_node(run_md_pk)
        run_md_uuid = str(run_md_node.uuid)

    if build_node is None and build_membrane_pk is not None:
        build_node = orm.load_node(build_membrane_pk)
        build_membrane_uuid = str(build_node.uuid)

    if build_node is None:
        diagnostics.append(
            "BuildMembraneWorkChain not found in provenance graph. "
            "Pass build_membrane_pk= explicitly if available."
        )

    # ── Composition ─────────────────────────────────────────────────────────
    composition = None
    protocols_charmm = None
    if build_node is not None:
        try:
            system_meta = build_node.outputs.system_metadata.get_dict()
            protocols_charmm = (
                build_node.inputs.protocol.get_dict()
                if hasattr(build_node.inputs, "protocol") else None
            )
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

    # ── Potential protocol ───────────────────────────────────────────────────
    protocols_potential = None
    if hasattr(node.inputs, "protocol"):
        protocols_potential = node.inputs.protocol.get_dict()
    else:
        missing_fields.append("protocols.potential")

    # ── Source file hashes ───────────────────────────────────────────────────
    source_files: dict[str, FileHash] = {}
    for attr_name, key in [("tpr_file", "tpr"), ("trajectory_compressed", "xtc")]:
        if hasattr(node.inputs, attr_name):
            sha = _hash_singlefile_node(getattr(node.inputs, attr_name))
            if sha:
                source_files[key] = FileHash(sha256=sha)

    # ── Fail if anything critical is missing ────────────────────────────────
    if missing_fields or missing_artifacts:
        raise ImportIncompleteError(missing_fields, missing_artifacts, diagnostics)

    # ── Parse XVG data ──────────────────────────────────────────────────────
    z_nm, phi_V = _parse_xvg_node(node.outputs.potential_profile, parse_xvg)

    components: dict[str, np.ndarray] = {}
    if hasattr(node.outputs, "potential_components"):
        for label, comp_node in node.outputs.potential_components.items():
            _, phi = _parse_xvg_node(comp_node, parse_xvg)
            components[label] = phi

    # ── Software versions ────────────────────────────────────────────────────
    software = _collect_software_versions()

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

    arrays = {"z_nm": z_nm, "phi_V": phi_V, "components": components}
    return record, arrays


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_composition(system_meta: dict, protocol: dict | None):
    from remembrane.record import Composition, Leaflet, LipidCount

    charmm_params = (protocol or {}).get("charmm_gui", {}).get("quick_bilayer", {})
    upper_str = charmm_params.get("upper", "")
    lower_str = charmm_params.get("lower", "")

    upper = _parse_lipid_ratio(upper_str)
    lower = _parse_lipid_ratio(lower_str)

    force_field = system_meta.get("force_field", "CHARMM36")
    water_model = system_meta.get("water_model", "TIP3")
    temperature_K = float(charmm_params.get("temperature", system_meta.get("temperature_K", 310.15)))
    ion_type = str(charmm_params.get("ion_type", system_meta.get("ion_type", "")))
    ion_conc_M = float(charmm_params.get("ion_conc", system_meta.get("ion_conc_M", 0.0)))

    return Composition(
        upper_leaflet=Leaflet(lipids=upper),
        lower_leaflet=Leaflet(lipids=lower),
        force_field=force_field,
        water_model=water_model,
        temperature_K=temperature_K,
        ion_type=ion_type,
        ion_conc_M=ion_conc_M,
    )


def _parse_lipid_ratio(spec: str) -> dict:
    """Parse CHARMM-GUI quick_bilayer composition strings.

    Handles both:
      'POPE:POPC:TLCL2=40:40:20'  (multi-lipid)
      'POPC=128'                  (single lipid)
    """
    from remembrane.record import LipidCount
    if not spec:
        return {}
    if "=" not in spec:
        return {}
    names_part, counts_part = spec.split("=", 1)
    names = [n.strip() for n in names_part.split(":")]
    counts = [int(c.strip()) for c in counts_part.split(":")]
    total = sum(counts)
    return {
        name: LipidCount(count=count, fraction=round(count / total, 6))
        for name, count in zip(names, counts)
    }


def _parse_xvg_node(node, parse_xvg_fn) -> tuple:
    import tempfile, os
    import numpy as np
    try:
        content = node.get_content(mode="rb")
    except TypeError:
        content = node.get_content().encode() if isinstance(node.get_content(), str) else node.get_content()
    tmp = tempfile.NamedTemporaryFile(suffix=".xvg", delete=False)
    try:
        tmp.write(content)
        tmp.close()
        return parse_xvg_fn(tmp.name)
    finally:
        os.unlink(tmp.name)


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
        gromacs_version=None,
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
