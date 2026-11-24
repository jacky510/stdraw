# -*- coding: utf-8 -*-
"""Packaged runtime data (stdraw/data/*.json).

These files ship inside the wheel / sdist as package data (declared in
pyproject.toml) so that a pip install and a git clone behave identically.
They are DATA, read-only at runtime: the calibration / library-build
research pipelines under benchmarks/ regenerate them and commit the result
here.  Read them through ``stdraw._datafiles`` (importlib.resources), never
via repo-relative ``Path(__file__)`` arithmetic.
"""
