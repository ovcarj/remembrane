import sys
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")   # non-interactive backend; must be set before importing pyplot
import matplotlib.pyplot as plt
import numpy as np
import pytest

from remembrane.record import MembraneRecord
from remembrane.plot import plot_arrays, plot_profile, plot_comparison, _short_label
from remembrane.storage import save_potential_total, save_potential_components

FIXTURE_META = Path(__file__).parent / "fixtures" / "example_record" / "metadata.yaml"
FIXTURE_DIR  = FIXTURE_META.parent


def _rec():
    return MembraneRecord.from_yaml(FIXTURE_META)


def test_plot_profile_returns_figure():
    fig = plot_profile(_rec(), FIXTURE_DIR)
    assert isinstance(fig, plt.Figure)
    plt.close("all")


def test_plot_profile_single_axes():
    fig = plot_profile(_rec(), FIXTURE_DIR)
    assert len(fig.axes) == 1
    plt.close("all")


def test_plot_profile_total_only_has_one_line():
    fig = plot_profile(_rec(), FIXTURE_DIR)
    ax = fig.axes[0]
    data_lines = [l for l in ax.lines if l.get_label() and not l.get_label().startswith("_")]
    # axhline adds a line with label "_nolegend_" or similar — we count only labeled lines
    assert len(data_lines) == 1
    plt.close("all")


def test_plot_profile_with_components_has_n_plus_one_lines():
    rec = _rec()
    n_components = len(rec.potential_meta.component_groups)
    fig = plot_profile(rec, FIXTURE_DIR, components=True)
    ax = fig.axes[0]
    data_lines = [l for l in ax.lines if l.get_label() and not l.get_label().startswith("_")]
    assert len(data_lines) == n_components + 1
    plt.close("all")


def test_plot_profile_accepts_external_axes():
    fig_ext, ax_ext = plt.subplots()
    fig_returned = plot_profile(_rec(), FIXTURE_DIR, ax=ax_ext)
    assert fig_returned is fig_ext
    plt.close("all")


def test_plot_profile_custom_label():
    fig = plot_profile(_rec(), FIXTURE_DIR, label="My custom label")
    ax = fig.axes[0]
    labels = [l.get_label() for l in ax.lines]
    assert "My custom label" in labels
    plt.close("all")


def test_plot_comparison_returns_figure():
    rec = _rec()
    fig = plot_comparison([rec, rec], [FIXTURE_DIR, FIXTURE_DIR])
    assert isinstance(fig, plt.Figure)
    plt.close("all")


def test_plot_comparison_two_records_two_lines():
    rec = _rec()
    fig = plot_comparison([rec, rec], [FIXTURE_DIR, FIXTURE_DIR])
    ax = fig.axes[0]
    data_lines = [l for l in ax.lines if l.get_label() and not l.get_label().startswith("_")]
    assert len(data_lines) == 2
    plt.close("all")


def test_plot_comparison_mismatched_lengths_raises():
    rec = _rec()
    with pytest.raises(ValueError, match="same length"):
        plot_comparison([rec], [FIXTURE_DIR, FIXTURE_DIR])


def test_short_label_single_lipid():
    rec = _rec()
    # Fixture has CDL2/POPC/POPE, so label should contain all three
    label = _short_label(rec)
    assert "POPC" in label
    assert "310" in label
    assert "NaCl" in label


def test_short_label_custom_fn_used_in_comparison():
    rec = _rec()
    called_with = []
    def my_fn(r):
        called_with.append(r)
        return "custom"
    fig = plot_comparison([rec], [FIXTURE_DIR], label_fn=my_fn)
    assert called_with == [rec]
    plt.close("all")


def test_plot_profile_missing_matplotlib_raises():
    with patch.dict(sys.modules, {"matplotlib": None, "matplotlib.pyplot": None}):
        with pytest.raises(ImportError, match="matplotlib"):
            from remembrane import plot as plot_mod
            import importlib
            importlib.reload(plot_mod)
            plot_mod._require_matplotlib()


# ── plot_arrays tests ─────────────────────────────────────────────────────────

def test_plot_arrays_returns_figure():
    z = np.linspace(0, 7.5, 100)
    phi = np.sin(z)
    fig = plot_arrays(z, phi)
    assert isinstance(fig, plt.Figure)
    plt.close("all")


def test_plot_arrays_no_components_one_line():
    z = np.linspace(0, 7.5, 100)
    phi = np.sin(z)
    fig = plot_arrays(z, phi, label="total")
    ax = fig.axes[0]
    labeled = [l for l in ax.lines if not l.get_label().startswith("_")]
    assert len(labeled) == 1
    plt.close("all")


def test_plot_arrays_with_components():
    z = np.linspace(0, 7.5, 100)
    phi = np.sin(z)
    comps = {"MEMB": phi * 2, "Water": -phi}
    fig = plot_arrays(z, phi, comps, label="total")
    ax = fig.axes[0]
    labeled = [l for l in ax.lines if not l.get_label().startswith("_")]
    assert len(labeled) == 3   # total + 2 components
    plt.close("all")


def test_plot_arrays_custom_label_in_legend():
    z = np.linspace(0, 7.5, 50)
    phi = np.zeros(50)
    fig = plot_arrays(z, phi, label="my label")
    ax = fig.axes[0]
    labels = [l.get_label() for l in ax.lines]
    assert "my label" in labels
    plt.close("all")


def test_plot_arrays_accepts_external_axes():
    z = np.linspace(0, 7.5, 50)
    phi = np.zeros(50)
    fig_ext, ax_ext = plt.subplots()
    fig_returned = plot_arrays(z, phi, ax=ax_ext)
    assert fig_returned is fig_ext
    plt.close("all")
