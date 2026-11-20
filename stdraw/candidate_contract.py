# -*- coding: utf-8 -*-
"""Unified LayoutCandidate contract (candidate-pool pipeline, M1 minimal loop).

Every candidate source (templates / layered incumbent) emits LayoutCandidate
objects — and NOTHING else crosses the source/orchestrator/selection boundary:

  - candidate_id: stable "<source>:<seq:03d>" (deterministic per run)
  - source:       source name (which generator produced it)
  - node_positions: {node_id: (x, y)} integer 2px-grid coordinates (ALL nodes)
  - metadata:     provenance only (engine, detector reason, deg0 handling);
                  no timestamps, no absolute paths (byte-determinism rule)
  - generation_cost: deterministic construction-effort units (documented per
                  source in candidate_sources.py; never wall-clock)
  - structural_signature: sha256[:16] over the shape quantized to a 24px grid
                  (same grid as the slot layer) — candidates with the same
                  quantized shape share a signature; this is the diversity-
                  grouping key of Stage 2 and the FIRST tie-break key.

Zero-scoring-power rule (plan v1.3.1 section 1.1 / section 8): sources carry
no metric-based filtering — a source emits every construction it completes;
quality decisions happen exclusively downstream (Hard Filter / epsilon-Pareto
/ ranking). Enforced by convention + a static import lint test.

Deterministic tie-break chain (plan section 3): structural_signature ->
coordinate sequence -> candidate_id. Floats never serve as the sole
tie-breaker (scores are compared with an explicit epsilon band; anything
inside the band falls to the structural chain).
"""
import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, Tuple

# Signature quantization grid (px). 24px = the slot-layer grid; coarse enough
# that micro-jitter candidates group together, fine enough to separate
# genuinely different structural forms at n<=20.
SIGNATURE_GRID_PX = 24

# Epsilon band for the Stage-3 heuristic score: two candidates whose scores
# differ by less than this are tied -> fall to the structural tie-break chain
# (floats are never the sole tie-breaker). Preregistered constant; to be
# recalibrated by the Phase 0/2 experiments, never tuned per graph.
SCORE_TIE_EPS = 1e-6


@dataclass
class LayoutCandidate:
    candidate_id: str
    source: str
    node_positions: Dict[str, Tuple[int, int]]
    metadata: dict = field(default_factory=dict)
    generation_cost: int = 0
    structural_signature: str = ""

    def __post_init__(self):
        if not self.structural_signature:
            self.structural_signature = structural_signature(
                self.node_positions)

    def to_dict(self):
        """JSON-safe deterministic serialization (no timestamps/paths)."""
        return {
            "candidate_id": self.candidate_id,
            "source": self.source,
            "node_positions": {v: list(self.node_positions[v])
                               for v in sorted(self.node_positions)},
            "metadata": self.metadata,
            "generation_cost": self.generation_cost,
            "structural_signature": self.structural_signature,
        }


def structural_signature(node_positions: Dict[str, Tuple[int, int]]) -> str:
    """sha256[:16] over the 24px-quantized shape, canonical node order."""
    g = SIGNATURE_GRID_PX
    parts = []
    for v in sorted(node_positions):
        x, y = node_positions[v]
        parts.append(f"{v}:{int(x) // g},{int(y) // g}")
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def coordinate_sequence_key(cand: LayoutCandidate):
    """Second tie-break key: the full-precision coordinate sequence in
    canonical node-id order (integers on the 2px grid -> exact comparison)."""
    return tuple(cand.node_positions[v] for v in sorted(cand.node_positions))


def structural_tiebreak_key(cand: LayoutCandidate):
    """Full deterministic tie-break chain: signature -> coords -> id."""
    return (cand.structural_signature, coordinate_sequence_key(cand),
            cand.candidate_id)


def score_rank_bucket(score: float) -> int:
    """LEGACY single-score quantizer — superseded by the chained eps
    bucketing in candidate_selection._score_buckets (a hard floor at integer
    multiples of eps let sub-eps gaps straddle a boundary; the chain form
    decides bucket membership by the eps band itself). Kept only for the
    contract-level eps band demo; NOT used by selection anymore."""
    return math.floor(score / SCORE_TIE_EPS)
