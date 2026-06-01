from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from remembrane.record import MembraneRecord


def plot_arrays(
    z_nm: "np.ndarray",
    phi_V: "np.ndarray",
    components: "dict[str, np.ndarray] | None" = None,
    *,
    label: str = "",
    ax=None,
    color=None,
    title: str = "Electrostatic potential",
) -> "Figure":
    """Plot (z_nm, phi_V) arrays directly.

    components maps group name → phi array (sharing the same z grid).
    Component curves are dashed, at reduced opacity, in the same color as the total.
    If ax is provided, draws into it; otherwise creates a new Figure.
    Returns the Figure.
    """
    import numpy as np
    plt = _require_matplotlib()

    created_fig = ax is None
    if created_fig:
        fig, ax = plt.subplots(figsize=(7, 4))
    else:
        fig = ax.get_figure()

    kw = dict(color=color) if color is not None else {}
    line, = ax.plot(z_nm, phi_V, lw=1.8, label=label or "_nolegend_", **kw)

    if components:
        prop_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        used = {line.get_color()}
        avail = [c for c in prop_cycle if c not in used]
        for i, (group, phi_comp) in enumerate(components.items()):
            ax.plot(
                z_nm, phi_comp,
                lw=1.0, ls="--", alpha=0.75,
                color=avail[i % len(avail)],
                label=f"{label} / {group}" if label else group,
            )

    if created_fig:
        _style_axes(ax, title)

    return fig


def plot_profile(
    record: "MembraneRecord",
    record_dir: Path,
    *,
    components: bool = False,
    ax=None,
    label: str | None = None,
    color=None,
    title: str | None = None,
) -> "Figure":
    """Plot φ(z) for one record.

    With components=True, adds one dashed curve per component group on the same axes.
    If ax is provided the plot is drawn into it; otherwise a new Figure is created.
    Returns the Figure.
    """
    from remembrane.storage import load_potential_total, load_potential_components

    record_dir = Path(record_dir)
    z_nm, phi_V = load_potential_total(record_dir)
    lbl = label if label is not None else _short_label(record)

    comp_dict = None
    if components:
        raw = load_potential_components(record_dir)
        comp_dict = {
            group: raw[group]
            for group in record.potential_meta.component_groups
            if group in raw
        }

    fig = plot_arrays(
        z_nm, phi_V, comp_dict,
        label=lbl, ax=ax, color=color,
        title=title or "Electrostatic potential",
    )
    return fig


def plot_comparison(
    records: list["MembraneRecord"],
    record_dirs: list[Path],
    *,
    components: bool = False,
    label_fn: Callable | None = None,
    title: str | None = None,
) -> "Figure":
    """Overlay φ(z) for multiple records on a single Axes.

    Each record gets a distinct color. With components=True each record's component
    curves are drawn in the same color as its total, but dashed and at reduced opacity.
    """
    plt = _require_matplotlib()

    if len(records) != len(record_dirs):
        raise ValueError("records and record_dirs must have the same length")

    fig, ax = plt.subplots(figsize=(8, 5))
    fn = label_fn or _short_label
    prop_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for i, (rec, rdir) in enumerate(zip(records, record_dirs)):
        color = prop_cycle[i % len(prop_cycle)]
        plot_profile(rec, rdir, components=components, ax=ax,
                     label=fn(rec), color=color)

    _style_axes(ax, title or "Potential comparison")
    return fig


# ── Helpers ──────────────────────────────────────────────────────────────────

def _short_label(record: "MembraneRecord") -> str:
    """Concise legend label: upper-leaflet composition · temperature · ion type."""
    lipids = record.composition.upper_leaflet.lipids
    if len(lipids) == 1:
        name, entry = next(iter(lipids.items()))
        comp = f"{name} {int(round(entry.fraction * 100))}%"
    else:
        parts = ":".join(
            f"{name} {int(round(entry.fraction * 100))}%"
            for name, entry in lipids.items()
        )
        comp = parts
    temp = f"{record.composition.temperature_K:.0f} K"
    ion = record.composition.ion_type or ""
    parts_out = [comp, temp]
    if ion:
        parts_out.append(ion)
    return " · ".join(parts_out)


def _style_axes(ax, title: str) -> None:
    ax.set_xlabel("z (nm)")
    ax.set_ylabel("φ (V)")
    ax.set_title(title)
    ax.axhline(0, color="black", lw=0.5, ls="--", zorder=0)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=8)
    ax.get_figure().tight_layout()


def _require_matplotlib():
    try:
        import matplotlib.pyplot as plt
        return plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for plotting. "
            "Install it with: pip install remembrane[plot]"
        ) from exc
