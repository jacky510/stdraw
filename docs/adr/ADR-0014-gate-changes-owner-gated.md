# ADR-0014: Hard-gate thresholds and grade semantics change only with explicit owner authorization

- **Status**: Standing governance (owner-gated gate changes; restated 2026-11-26 with the gate-registry refactor and again with the T18 annotation migration)

## Context

Mirrors the repo AGENTS.md forbidden list and the fleet hard-limits
page; the registry refactor intentionally made such changes ONE-LINE, which
is exactly why the authorization gate is restated at the code site.

## Decision (rule in force)

Relaxing a certificate hard-gate threshold, changing grade semantics, or
re-scoping a gate (e.g. "regularity gates become report items for n>10" as
a one-line `when=` data change in the gate registry) is OWNER-GATED: it
must never happen as a side effect of a refactor, and never to let a
figure pass.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/cert_gates.py:23`

```
  ``when=lambda ctx: ctx.n_nodes <= 10`` on the affected entries.  That
  change is owner-gated (jacky authorization) and must NOT happen as a
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0014` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
