# -*- coding: utf-8 -*-
"""stdraw systems-thinking diagram engine.

Three-layer architecture:
    Layout layer (planar / layout3d, replaceable implementations)
    Quality layer (metrics five-metric certificate + check geometry self-inspection + loops loop semantic audit) -- this project's moat
    Viewer layer (viewer/)

Honest tiering promise: if a certificate cannot be obtained we say so; we never claim 0 crossings for arbitrary graphs.
"""

__version__ = "0.7.8"

from .model import Graph, Node, Edge, Loop, Group
from .dsl import parse, dumps
from .planar import PlanarLayout
from . import recipes
from .metrics import certificate, certificate_auto
from .check import geometry_report
from .loops import loops_audit
from . import crossing_exact          # WS2: exact crossing-number layer (optional ortools)
from . import regularity              # WS2: structure detection + computable definitions of regularity
from . import placement               # WS2: slot-discretized placement (optional ortools)
from . import ringlayout              # ref-scrubbed: loop-driven ring placement (trigger decision + slots)

__all__ = [
    "Graph", "Node", "Edge", "Loop", "Group",
    "parse", "dumps",
    "PlanarLayout", "certificate", "certificate_auto", "geometry_report",
    "loops_audit", "recipes",
    "crossing_exact", "regularity", "placement",
]
