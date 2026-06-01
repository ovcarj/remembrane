import sys
from unittest.mock import MagicMock, patch

import pytest


def test_preview_raises_import_error_without_aiida():
    with patch.dict(sys.modules, {"aiida": None, "aiida.orm": None}):
        with pytest.raises(ImportError, match="aiida-core"):
            from remembrane.aiida import preview as preview_mod
            import importlib
            importlib.reload(preview_mod)
            preview_mod.preview_from_workchain(1)


def test_build_label_with_report():
    from remembrane.aiida.preview import _build_label

    node = MagicMock()
    node.pk = 42
    node.outputs.potential_report.get_dict.return_value = {"charge_group": "SYSTEM"}
    assert _build_label(node) == "pk=42 / SYSTEM"


def test_build_label_without_report():
    from remembrane.aiida.preview import _build_label

    node = MagicMock()
    node.pk = 99
    node.outputs.potential_report.get_dict.side_effect = Exception("no report")
    assert _build_label(node) == "pk=99"
