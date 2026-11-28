"""Golden archetype set integrity (fast, no layout run): tests/golden/*.cld.

The slow half of the golden gate -- render every archetype, grade best,
byte-compare against tests/golden/baseline.json -- lives in
tests/golden_gate.py (CI phase M, docs/validation-tiers.md section 10).
This module keeps the cheap invariants inside the regular pytest suite:

- every golden graph parses, round-trips, stays inside the 3-8 node hard
  limit, has ASCII ids and CJK-only labels (the analytic text-width floor
  dominates the font measurement for CJK, which is what makes the layout
  bytes identical between the Windows and the Linux CI font environments);
- the loops audit is clean: every declared loop closes over its tagged
  edges, its R/B kind matches the polarity parity, and the independent
  enumeration finds no undeclared cycle (all feedback loops are declared);
- the baseline file is complete and its fixture hashes match the .cld files
  on disk (a fixture edit without --update-baseline fails here too);
- the gate is wired into CI (phase M in the corpus job) and refuses to run
  under a fallback-construct interpreter.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from stdraw.dsl import dumps, parse
from stdraw.loops import loops_audit

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
BASELINE = GOLDEN / "baseline.json"
# hard limit (project-hard-limits): golden graphs are small, 3-8 nodes
NODE_MIN, NODE_MAX = 3, 8
# CJK full-width repertoire only (ideographs + CJK punctuation); every
# allowed codepoint is > U+2E7F so the analytic estimate (1.10 fs per char)
# dominates the font measurement in text_width's max(), which is what makes
# the layout bytes identical between the pillow (Windows) and the analytic
# (Linux CI) paths
CJK_OK = re.compile(r"^[\u3001\u3002\uff08\uff09\u4e00-\u9fff]+$")

# every test here needs the golden fixtures (packaged into the sdist via
# MANIFEST.in `graft tests`, so they exist in a checkout and in an sdist)
pytestmark = pytest.mark.repo("tests/golden")


def golden_clds():
    return sorted(GOLDEN.glob("*.cld"))


def test_golden_set_present():
    clds = golden_clds()
    assert len(clds) >= 6, f"golden set shrunk to {len(clds)} graph(s)"
    assert len(clds) <= 8, "first batch is 6-8 archetypes; grow it via a new card"


@pytest.mark.parametrize("cld", golden_clds(), ids=lambda p: p.stem)
def test_golden_graph_small_ascii_ids_cjk_labels(cld):
    text = cld.read_text(encoding="utf-8")
    g = parse(text)
    assert NODE_MIN <= len(g.nodes) <= NODE_MAX, (cld.name, len(g.nodes))
    assert len(g.edges) >= len(g.nodes), (cld.name, "a feedback structure needs cycles")
    for n in g.nodes:
        assert n.id.isascii() and n.id.isidentifier(), (cld.name, n.id)
        assert n.label and CJK_OK.match(n.label), (
            cld.name, n.id, "label must be CJK-only so the analytic width floor "
            "dominates the font measurement (cross-platform byte stability)")
    for lp in g.loops:
        assert lp.id.isascii() and lp.kind in ("R", "B"), (cld.name, lp.id)
    assert parse(dumps(g)) == g, (cld.name, "DSL round-trip")


@pytest.mark.parametrize("cld", golden_clds(), ids=lambda p: p.stem)
def test_golden_loops_audit_clean(cld):
    g = parse(cld.read_text(encoding="utf-8"))
    audit = loops_audit(g)
    s = audit["summary"]
    assert s["problems"] == 0, (cld.name, audit["problems"])
    assert s["declared"] == s["closed"] == s["kind_consistent"], (cld.name, s)
    assert s["undeclared"] == 0, (cld.name, "every simple cycle must be declared", s)


def test_golden_baseline_matches_fixtures():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert base["_schema"] == "stdraw-golden-baseline/1"
    assert base["_meta"]["engine_caliber"] == "cp-sat-layered"
    graphs = base["graphs"]
    names = sorted(p.stem for p in golden_clds())
    assert sorted(graphs) == names, (sorted(graphs), names)
    for name in names:
        entry = graphs[name]
        assert entry["grade"] == "best", (name, entry["grade"])
        assert entry["placement"], name
        assert re.fullmatch(r"\d+/\d+", entry["gates_passed"]), (name, entry["gates_passed"])
        assert entry["crossings"] == 0 and entry["visual_crossings"] == 0, name
        assert entry["geometry_fail"] == 0 and entry["loops_problems"] == 0, name
        shas = entry["sha256"]
        assert sorted(shas) == sorted(["cld", "certificate", "layout", "loops_audit"]), name
        for key, val in shas.items():
            assert re.fullmatch(r"[0-9a-f]{64}", val), (name, key)
        raw = (GOLDEN / f"{name}.cld").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == shas["cld"], (
            name, "fixture edited without --update-baseline")
    timing = base["timing_ref"]
    assert set(timing["per_graph"]) == set(names)
    assert timing["max"] >= timing["avg"] > 0


@pytest.mark.repo(".github/workflows/ci.yml", "tests/ci_checks.py",
                  "tests/golden_gate.py")
def test_golden_gate_wired_into_ci():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"checks-corpus:.*?STDRAW_CI_PHASES:\s*([A-Z0-9,]+)", ci, re.S)
    assert m and "M" in m.group(1).split(","), "phase M missing from the corpus job"
    checks = (ROOT / "tests" / "ci_checks.py").read_text(encoding="utf-8")
    assert '_on("M")' in checks and '"golden_gate.py"' in checks
    assert (ROOT / "tests" / "golden_gate.py").exists()


def test_golden_gate_refuses_without_ortools():
    # hide ortools from the child interpreter: the gate must exit 1 instead
    # of comparing a fallback-construct render against the cp-sat baseline
    code = (
        "import sys, runpy; sys.modules['ortools'] = None; "
        "sys.argv = ['golden_gate.py', '--only', 'escalation']; "
        f"runpy.run_path({str(ROOT / 'tests' / 'golden_gate.py')!r}, run_name='__main__')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "ortools absent" in r.stdout + r.stderr
_GATE_PATH = ROOT / "tests" / "golden_gate.py"


def _gate_module():
    """Import tests/golden_gate.py as a module (it is a script with a __main__ guard)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_golden_gate_under_test", _GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_cert(path, version="0.10.0", grade="best"):
    obj = {"tool": "stdraw", "version": version, "grade": grade,
           "metrics": {"crossings": 0}}
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def test_certificate_caliber_ignores_the_version_value(tmp_path):
    """A version closure must not move the eight certificate fingerprints.

    Drift registry #8: the certificate stamps ``stdraw.__version__`` into a
    top-level ``version`` field, so bumping 0.9.0 -> 0.10.0 drifted all eight
    hashes with zero content change.  The caliber now neutralizes that one
    value (owner ruling 2026-11-28, registry #9).
    """
    gate = _gate_module()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_cert(a, version="0.9.0")
    _write_cert(b, version="0.10.0")
    assert gate.sha256_file_certificate(a) == gate.sha256_file_certificate(b)


def test_certificate_caliber_still_pins_everything_else(tmp_path):
    # a real content change must still drift, or the caliber is a blunt amnesty
    gate = _gate_module()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_cert(a, grade="best")
    _write_cert(b, grade="good")
    assert gate.sha256_file_certificate(a) != gate.sha256_file_certificate(b)
    # formatting is part of the pin too (raw bytes, not canonical JSON)
    c = tmp_path / "c.json"
    c.write_text(a.read_text(encoding="utf-8").replace("\n ", "\n    "),
                 encoding="utf-8", newline="\n")
    assert gate.sha256_file_certificate(a) != gate.sha256_file_certificate(c)


def test_certificate_caliber_fails_closed(tmp_path):
    # no string version -> the gate must refuse, not fall back to raw bytes
    gate = _gate_module()
    p = tmp_path / "no-version.json"
    p.write_text(json.dumps({"tool": "stdraw"}, indent=1) + "\n",
                 encoding="utf-8", newline="\n")
    with pytest.raises(SystemExit):
        gate.sha256_file_certificate(p)
    # version present but written in a shape the caliber cannot pin down
    q = tmp_path / "odd.json"
    q.write_text('{"version":"0.10.0"}\n', encoding="utf-8", newline="\n")
    with pytest.raises(SystemExit):
        gate.sha256_file_certificate(q)
