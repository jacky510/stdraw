# -*- coding: utf-8 -*-
"""Regression: the planarized L1 pinned worker must survive quote-bearing paths.

Pre-fix bug: _l1_deterministic interpolated the package parent into the
pinned worker's `python -c` source as r'<path>'; any single quote in the
install path (e.g. "it's pkg") made the worker source a SyntaxError and the
computation silently degraded to the in-process fallback.
Fix: the path travels through the STDRAW_PKG_PARENT environment variable,
never through generated source text.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import stdraw

_PY = sys.executable


def test_pinned_worker_code_does_not_embed_the_path():
    # the generated source must not carry the literal path at all
    import inspect

    from stdraw import planarized_layout
    src = inspect.getsource(planarized_layout._l1_deterministic)
    assert "STDRAW_PKG_PARENT" in src
    assert "r'{pkg_parent}'" not in src.replace("\\'", "'")


def test_planarized_entry_runs_from_package_path_with_quote(tmp_path):
    src_pkg = Path(stdraw.__file__).parent
    pkg_parent = tmp_path / "it's pkg"
    shutil.copytree(src_pkg, pkg_parent / "stdraw",
                    ignore=shutil.ignore_patterns("__pycache__"))
    assert "'" in str(pkg_parent)  # the simulation is real

    driver = (
        "import sys;"
        "sys.path.insert(0, sys.argv[1]);"
        "from stdraw.model import Graph, Edge;"
        "from stdraw.layout_auto import AutoConfig;"
        "from stdraw.planarized_layout import planarized_entry;"
        "ids = ['a','b','c','d','e'];"
        "edges = [Edge(a=ids[i], b=ids[j], polarity='+') "
        "         for i in range(5) for j in range(i + 1, 5)];"  # K5: non-planar
        "g = Graph(name='k5', "
        "          nodes=[__import__('stdraw.model', fromlist=['Node']).Node(id=i, label=i) for i in ids],"
        "          edges=edges);"
        "mode, payload = planarized_entry(g, AutoConfig(), 'straight');"
        "assert mode == 'L1' and payload, mode;"
        "print('PLANARIZED-OK')"
    )
    r = subprocess.run([_PY, "-c", driver, str(pkg_parent)],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, (
        f"driver rc={r.returncode}\nstdout={r.stdout[-500:]}\nstderr={r.stderr[-800:]}")
    assert "PLANARIZED-OK" in r.stdout
    # the pinned worker must have run, not the degraded in-process fallback
    assert "pinned worker failed" not in r.stderr, r.stderr[-800:]
