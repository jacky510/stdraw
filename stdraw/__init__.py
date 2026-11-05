# -*- coding: utf-8 -*-
"""stdraw 系统思维图引擎。

三层架构：
  布局层（planar / layout3d，可替换实现）
  质量层（metrics 五指标证书 + check 几何自检 + loops 环路语义审计）—— 本项目的护城河
  查看层（viewer/）

诚实分级承诺：拿不到证书就说拿不到；绝不宣称任意图 0 交叉。
"""

__version__ = "0.1.0"

from .model import Graph, Node, Edge, Loop, Group
from .dsl import parse, dumps
from .planar import PlanarLayout
from .metrics import certificate
from .check import geometry_report
from .loops import loops_audit

__all__ = [
    "Graph", "Node", "Edge", "Loop", "Group",
    "parse", "dumps",
    "PlanarLayout", "certificate", "geometry_report", "loops_audit",
]
