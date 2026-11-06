# -*- coding: utf-8 -*-
"""stdraw 系统思维图引擎。

三层架构：
  布局层（planar / layout3d，可替换实现）
  质量层（metrics 五指标证书 + check 几何自检 + loops 环路语义审计）—— 本项目的护城河
  查看层（viewer/）

诚实分级承诺：拿不到证书就说拿不到；绝不宣称任意图 0 交叉。
"""

__version__ = "0.6.0"

from .model import Graph, Node, Edge, Loop, Group
from .dsl import parse, dumps
from .planar import PlanarLayout
from . import recipes
from .metrics import certificate, certificate_auto
from .check import geometry_report
from .loops import loops_audit
from . import crossing_exact          # WS2：精确交叉数层（可选 ortools）
from . import regularity              # WS2：结构检测 + 规律性可计算定义
from . import placement               # WS2：槽位离散化放置（可选 ortools）
from . import ringlayout              # ref-scrubbed：回路主导环形排布（触发判定+槽位）

__all__ = [
    "Graph", "Node", "Edge", "Loop", "Group",
    "parse", "dumps",
    "PlanarLayout", "certificate", "certificate_auto", "geometry_report",
    "loops_audit", "recipes",
    "crossing_exact", "regularity", "placement",
]
