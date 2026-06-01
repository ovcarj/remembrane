import textwrap
from pathlib import Path

import numpy as np
import pytest

from remembrane.parsers.xvg import parse_xvg


def write_xvg(path, content):
    Path(path).write_text(textwrap.dedent(content))


def test_basic_two_columns(tmp_path):
    xvg = tmp_path / "test.xvg"
    write_xvg(xvg, """\
        # GROMACS generated XVG
        @ title "Test"
        @ xaxis label "z (nm)"
        @ yaxis label "Potential (V)"
        0.0  1.5
        0.5  2.0
        1.0  0.5
    """)
    x, y = parse_xvg(xvg)
    assert len(x) == 3
    assert x[0] == pytest.approx(0.0)
    assert y[1] == pytest.approx(2.0)


def test_skips_comments_and_directives(tmp_path):
    xvg = tmp_path / "test.xvg"
    write_xvg(xvg, """\
        # comment line
        @TYPE xy
        @ s0 legend "phi"
        1.0  -0.3
        2.0  0.7
    """)
    x, y = parse_xvg(xvg)
    assert len(x) == 2
    np.testing.assert_array_almost_equal(x, [1.0, 2.0])


def test_three_columns_uses_first_two(tmp_path):
    xvg = tmp_path / "test.xvg"
    write_xvg(xvg, """\
        0.0  1.0  0.1
        1.0  2.0  0.2
    """)
    x, y = parse_xvg(xvg)
    assert len(x) == 2
    assert y[1] == pytest.approx(2.0)


def test_empty_file(tmp_path):
    xvg = tmp_path / "empty.xvg"
    xvg.write_text("# only comments\n@ title\n")
    x, y = parse_xvg(xvg)
    assert len(x) == 0
    assert len(y) == 0
