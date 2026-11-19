# -*- coding: utf-8 -*-
"""Optimization Orchestrator v1 (candidate-pool pipeline).

Plan v1.3.1 section 1.3/2 — the Orchestrator decides which candidate sources
run, manages the generation budget, and owns every failure path. Its power
boundary is explicit:

  - it NEVER sees candidate-quality data: scheduling reads topology features
    (GraphStructureAnalysis) + resource budgets + preregistered rules only.
    Eliminating a source because its candidates score poorly is forbidden
    (plan section 2 power-transfer note: source exits only via the M2
    ablation reports).
  - it does not replace the independent validator and does not bypass hard
    gates: "best candidate" means the best candidate that PASSED selection
    and delivery verification (pipeline contract), or the honest fallback.

Failure paths (each has a defined destination — M1 acceptance item):
  - loop-analysis failure -> loop_model.status="failed": the loop-reading
    source is disarmed by the preregistered rule (candidate_sources.template_
    enabled), all other sources still run, the failure is recorded.
  - source construction failure -> per-source failure record, the rest of
    the sources continue.
  - topological non-trigger (detector None) -> per-source record, not a
    failure.
  - generation budget exhausted -> remaining sources marked budget-skipped.
  - zero candidates after all sources -> result.ok=False; the pipeline
    delivers the v0.8.2 incumbent path untouched (final fallback).
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .candidate_contract import LayoutCandidate
from .candidate_sources import (SOURCE_ORDER, SourceContext,
                                SourceConstructionError, SourceUnavailable,
                                generate_from_source, template_enabled)

# ---- generation budget (preregistered constants; never wall-clock) ----
MAX_TOTAL_CANDIDATES = 12      # engine n<=20 scope: sources emit 1 candidate
MAX_PER_SOURCE = 2             # structural quota headroom for M2 variants


@dataclass
class SourceRecord:
    source: str
    outcome: str                  # "generated" | "not_triggered" | "failed"
                                  # | "budget_skipped" | "disabled_by_rule"
    detail: Optional[str] = None
    candidates: int = 0

    def to_dict(self):
        return {"source": self.source, "outcome": self.outcome,
                "detail": self.detail, "candidates": self.candidates}


@dataclass
class OrchestrationResult:
    candidates: List[LayoutCandidate] = field(default_factory=list)
    records: List[SourceRecord] = field(default_factory=list)
    budget_total: int = MAX_TOTAL_CANDIDATES
    budget_per_source: int = MAX_PER_SOURCE
    exhausted: bool = False

    def to_dict(self):
        return {
            "budget": {"total": self.budget_total,
                       "per_source": self.budget_per_source,
                       "exhausted": self.exhausted},
            "source_records": [r.to_dict() for r in self.records],
            "candidates": [c.to_dict() for c in self.candidates],
        }


class Orchestrator:
    """Source on/off + generation budget + failure management, v1.

    Deterministic: fixed source order (SOURCE_ORDER), sorted candidate ids,
    no wall-clock anywhere.
    """

    def __init__(self, max_total: int = MAX_TOTAL_CANDIDATES,
                 max_per_source: int = MAX_PER_SOURCE):
        self.max_total = max_total
        self.max_per_source = max_per_source

    def run(self, ctx: SourceContext) -> OrchestrationResult:
        result = OrchestrationResult(budget_total=self.max_total,
                                     budget_per_source=self.max_per_source)
        total = 0
        for source in SOURCE_ORDER:            # preregistered fixed order
            if total >= self.max_total:
                result.records.append(SourceRecord(
                    source=source, outcome="budget_skipped",
                    detail=f"total candidate budget {self.max_total} reached"))
                result.exhausted = True
                continue
            if not template_enabled(source, ctx):
                result.records.append(SourceRecord(
                    source=source, outcome="disabled_by_rule",
                    detail="preregistered topology rule (node cap / loop "
                           "model status)"))
                continue
            try:
                cands = generate_from_source(
                    source, ctx, seq=total)
            except SourceUnavailable as e:
                result.records.append(SourceRecord(
                    source=source, outcome="not_triggered",
                    detail=str(e)))
                continue
            except SourceConstructionError as e:
                result.records.append(SourceRecord(
                    source=source, outcome="failed", detail=str(e)))
                continue
            except Exception as e:             # unexpected: honest record
                result.records.append(SourceRecord(
                    source=source, outcome="failed",
                    detail=f"unexpected {type(e).__name__}: {e}"))
                continue
            # structural quota: deterministic per-source cap (never
            # quality-based — takes the source's own deterministic order)
            kept = cands[:self.max_per_source]
            result.candidates.extend(kept)
            total += len(kept)
            result.records.append(SourceRecord(
                source=source, outcome="generated",
                candidates=len(kept),
                detail=(f"emitted {len(cands)}, kept {len(kept)} "
                        f"(per-source budget {self.max_per_source})")))
        return result
