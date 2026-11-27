# ADR-0013: Engine capability scope: n <= 20

- **Status**: Accepted 2026-11-14

## Context

Scope ruling mirrored in the project hard-limits page; any card proposing
n30/n50 verification is a hard-limit violation.

## Decision (rule in force)

stdraw's verified engine range is n <= 20 (validation tiers: A-tier
n <= 20 byte-exact full sweep; B-tier sampling 21-30 retired to the z.code
line; n > 30 out of the verification envelope - drive Graphviz directly
there). Scope statements in user-facing help text cite this ruling.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/__main__.py:127`

```
    ap.add_argument("--no-exact", dest="no_exact", action="store_true",
                    help="D4 fallback (jacky 2026-11-14 scope ruling, stdraw range n<=20): opt OUT "
```

Source: `stdraw/__main__.py:252`

```
    exactness = None
    # D4 (jacky 2026-11-14): L1 planarized drawings default to
    # --exact (oracle cr UB participates in the three-account
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0013` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
