# -*- coding: utf-8 -*-
"""Single resolution point for packaged runtime data files.

Runtime data (``stdraw/data/*.json``) must resolve identically whether the
package is a git checkout, an editable install, or a pip-installed wheel --
so it is read through ``importlib.resources``, never via repo-relative
``Path(__file__)`` arithmetic (a wheel has no repo tree around it; the old
``parent.parent / "benchmarks"`` lookups silently degraded to fallbacks on
pip installs).
"""
import os
from importlib import resources
from pathlib import Path


def data_file(name):
    """Traversable for ``stdraw/data/<name>`` (read_text / open both work)."""
    return resources.files("stdraw.data").joinpath(name)


def read_text(f, encoding="utf-8"):
    """read_text for a str / os.PathLike / importlib Traversable."""
    if isinstance(f, (str, os.PathLike)):
        return Path(f).read_text(encoding=encoding)
    return f.read_text(encoding=encoding)
