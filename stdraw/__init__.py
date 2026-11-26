# -*- coding: utf-8 -*-
"""stdraw systems-thinking diagram engine.

Two-layer architecture:
    Layout layer (auto-v2 mode-based placement; internal planar module)
    Quality layer (metrics certificate + check geometry self-inspection + loops loop semantic audit) -- this project's moat

Honest tiering promise: if a certificate cannot be obtained we say so; we never claim 0 crossings for arbitrary graphs.
"""

__version__ = "0.9.0"

from .model import Graph, Node, Edge, Loop, Group
from .dsl import parse, dumps
from . import recipes
from .metrics import certificate_auto
from .check import geometry_report
from .loops import loops_audit
from . import crossing_exact          # WS2: exact crossing-number layer (optional ortools)
from . import regularity              # WS2: structure detection + computable definitions of regularity
from . import placement               # WS2: slot-discretized placement (optional ortools)
from . import ringlayout              # ref-scrubbed: loop-driven ring placement (trigger decision + slots)

__all__ = [
    "Graph", "Node", "Edge", "Loop", "Group",
    "parse", "dumps",
    "certificate_auto", "geometry_report",
    "loops_audit", "recipes",
    "crossing_exact", "regularity", "placement",
]
