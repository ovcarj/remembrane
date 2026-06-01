from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def preview_from_workchain(
    uuid_or_pk: str | int,
    components: bool = False,
) -> tuple["Figure", str]:
    """Plot φ(z) directly from an AiiDA ComputeMembranePotentialWorkChain node.

    Does not create a record or touch the registry.
    Returns (figure, label).

    Requires remembrane[aiida] and remembrane[plot].
    """
    try:
        import aiida
        from aiida import orm
    except ImportError as exc:
        raise ImportError(
            "aiida-core is required for preview. "
            "Install it with: pip install remembrane[aiida]"
        ) from exc

    try:
        aiida.load_profile()
    except Exception:
        pass  # profile already loaded, or using a custom manager

    from remembrane.aiida.importer import _parse_xvg_node
    from remembrane.parsers.xvg import parse_xvg
    from remembrane.plot import plot_arrays

    node = orm.load_node(uuid_or_pk)

    z_nm, phi_V = _parse_xvg_node(node.outputs.potential_profile, parse_xvg)

    comp_dict = None
    if components and hasattr(node.outputs, "potential_components"):
        comp_dict = {}
        for group, comp_node in node.outputs.potential_components.items():
            _, phi = _parse_xvg_node(comp_node, parse_xvg)
            comp_dict[group] = phi

    label = _build_label(node)
    title = f"Preview — {label}"
    fig = plot_arrays(z_nm, phi_V, comp_dict, label=label, title=title)
    return fig, label


def _build_label(node) -> str:
    pk = node.pk
    try:
        report = node.outputs.potential_report.get_dict()
        charge_group = report.get("charge_group", "")
        return f"pk={pk} / {charge_group}" if charge_group else f"pk={pk}"
    except Exception:
        return f"pk={pk}"
