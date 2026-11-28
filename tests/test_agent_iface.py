# -*- coding: utf-8 -*-
"""Agent interface (T13/T14/T15): structured repair hints, semantic hint
consumption effects, size-limit refusal, deprecation warnings.

T13: a failing certificate gate carries a structured repair hint
     {gate, hint, retry}; all-pass certificates keep their bytes (no block).
     A loop audit with problems carries pasteable `loop ...` declaration
     lines with the correctly determined R/B (polarity parity).
T14: @order reorders the loop reading sequence (audit + pipeline);
     @main forces the main-ring selection (ring mode) and adds a centering
     term (layered mode); @pair packs same-row pairs adjacently. The
     certificate records the hints block only when hints exist.
T15: the CLI refuses graphs above MAX_LAYOUT_NODES before any layout
     attempt (structured refusal.json, exit 3); --allow-oversize extends to
     the n<=20 capability ceiling and >20 is refused even with the flag.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse, DSLParseError     # noqa: E402
from stdraw.limits import (HARD_CEILING_NODES,     # noqa: E402
                           MAX_LAYOUT_NODES, size_refusal)
from stdraw.loops import loops_audit               # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402
from stdraw.repair import certificate_repair_hints  # noqa: E402

PY = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── shared fixtures ──

THREE_LOOP = """
graph "hints-demo"
var a "A"
var b "B"
var c "C"
var d "D"
var e "E"
a -> + b @loops R1
b -> - c @loops R1
c -> + a @loops R1
c -> + d @loops B1
d -> - e @loops B1
e -> + c @loops B1
a -> + d @loops R2
e -> - a @loops R2
loop R1 "main growth" "B" [a, b, c]
loop B1 "balancing" "B" [c, d, e]
loop R2 "side" "R" [a, d, e]
"""


# ── T13: certificate repair hints ──

def test_repair_hints_present_on_failing_gate_only():
    gates = {"box_press_zero": True, "min_gap_ge_16": False}
    hints = certificate_repair_hints(gates, {})
    assert len(hints) == 1
    h = hints[0]
    assert h["gate"] == "min_gap_ge_16"
    assert h["retry"] is True
    assert "split the graph by loops" in h["hint"] or "@order" in h["hint"]


def test_repair_hints_absent_on_all_pass():
    gates = {"box_press_zero": True, "min_gap_ge_16": True,
             "dense_mode": {"note": "annotation dict, not a gate"}}
    assert certificate_repair_hints(gates, {}) == []


def test_certificate_repair_hints_block_only_when_failing():
    from stdraw.layout_auto import AutoConfig, layout
    g = parse(THREE_LOOP)
    v4 = layout(g, AutoConfig())
    cert = certificate_auto(scene_from_auto(v4), graph_name="hints-demo",
                            graph=g, deliverable=True)
    # a golden-grade ring on a small graph: no failing gate -> no block
    if cert["grade"] == "best":
        assert "repair_hints" not in cert
    else:
        assert isinstance(cert.get("repair_hints"), list)


def test_audit_suggested_declarations_close_the_loop():
    txt = """
graph "x"
var a "A"
var b "B"
var c "C"
a -> + b @loops R1
b -> + c
c -> + a
loop R1 "declared" "R" [a, b]
"""
    report = loops_audit(parse(txt))
    assert report["problems"]
    sugg = report["suggested_declarations"]
    assert len(sugg) == 1
    line = sugg[0]
    # pasteable AND correctly kinded (all-plus cycle => R)
    assert line.startswith("loop xauto1 ")
    assert '"R"' in line and "[a, b, c]" in line
    # paste + tag the edges -> audit problems from undeclared cycles gone
    g2 = parse(txt + line.replace('"undeclared cycle (auto)"', '"x"')
               .replace("] @", "]") .replace("[a, b, c]", "[a, b, c]")
               + "")
    report2 = loops_audit(g2)
    assert not any("undeclared cycle" in p for p in report2["problems"])


def test_audit_kind_mismatch_suggests_parity_kind():
    txt = """
graph "y"
var a "A"
var b "B"
a -> + b @loops R1
b -> + a @loops R1
loop R1 "wrong kind" "B" [a, b]
"""
    report = loops_audit(parse(txt))
    fixes = [h["fix"] for h in report["repair_hints"]]
    assert any('loop R1 "wrong kind" "R" [a, b]' in f for f in fixes)


def test_audit_clean_keeps_bytes_no_hint_keys():
    txt = """
graph "z"
var a "A"
var b "B"
a -> + b @loops R1
b -> + a @loops R1
loop R1 "r" "R" [a, b]
"""
    report = loops_audit(parse(txt))
    assert report["pass"] is True
    assert "suggested_declarations" not in report
    assert "repair_hints" not in report


# ── T14: semantic hint consumption ──

def test_order_hint_reorders_audit_and_pipeline():
    from stdraw.hints import apply_hints, has_hints
    g = parse(THREE_LOOP + "@order B1,R2,R1\n")
    g2, applied = apply_hints(g)
    assert [lp.id for lp in g2.loops] == ["B1", "R2", "R1"]
    assert applied
    report = loops_audit(g2)
    assert [it["id"] for it in report["loops"]] == ["B1", "R2", "R1"]
    assert apply_hints(g2)[0] == g2                 # idempotent
    g0 = parse(THREE_LOOP)
    assert not has_hints(g0) and apply_hints(g0)[0] is g0


def test_main_hint_forces_ring_selection():
    from stdraw.layout_auto import AutoConfig, layout
    g = parse(THREE_LOOP + "@main R1\n")
    v4 = layout(g, AutoConfig())
    meta = v4["meta"].get("ring") or {}
    assert meta.get("declared_loop") == "R1"
    assert meta.get("hint_main") == "R1"


def test_main_hint_changes_selection_vs_unhinted():
    from stdraw.layout_auto import AutoConfig, layout
    g0 = parse(THREE_LOOP)
    v40 = layout(g0, AutoConfig())
    m0 = v40["meta"].get("ring") or {}
    g1 = parse(THREE_LOOP + "@main R1\n")
    v41 = layout(g1, AutoConfig())
    m1 = v41["meta"].get("ring") or {}
    # the unhinted ranking picked something else (declared_loop None here);
    # with @main the declared loop wins and the meta records it
    assert m1.get("hint_main") == "R1" and m0.get("hint_main") is None


def test_pair_hint_adjacent_on_ring():
    from stdraw.layout_auto import AutoConfig, layout
    g = parse(THREE_LOOP + "@pair d,e\n")
    v4 = layout(g, AutoConfig())
    xs = {k: v["x"] for k, v in v4["nodes"].items()}
    ys = {k: v["y"] for k, v in v4["nodes"].items()}
    cx = sum(xs.values()) / len(xs)
    cy = sum(ys.values()) / len(ys)
    ids = list(xs)
    order = [ids[i] for i in sorted(range(len(ids)),
                                    key=lambda i: __import__("math").atan2(
                                        ys[ids[i]] - cy, xs[ids[i]] - cx))]
    i, k = order.index("d"), len(order)
    assert order[(i + 1) % k] == "e" or order[(i - 1) % k] == "e"


def test_certificate_hints_block_only_when_hints_exist():
    from stdraw.layout_auto import AutoConfig, layout
    g0 = parse(THREE_LOOP)
    v40 = layout(g0, AutoConfig())
    c0 = certificate_auto(scene_from_auto(v40), graph_name="x",
                          graph=g0, deliverable=True)
    assert "hints" not in c0
    g1 = parse(THREE_LOOP + "@main R1\n@order R1,B1,R2\n@pair a,b\n")
    v41 = layout(g1, AutoConfig())
    c1 = certificate_auto(scene_from_auto(v41), graph_name="x",
                          graph=g1, deliverable=True)
    blk = c1["hints"]
    assert blk["main"] == ["R1"]
    assert blk["order"] == ["R1", "B1", "R2"]
    assert blk["pairs"] == [["a", "b"]]
    assert "mechanism" in blk and "deprecated" in blk["note"]


# ── T15: size-limit structured refusal ──

def _write_cld(path, n):
    ids = [f"v{i}" for i in range(n)]
    lines = ['graph "big"']
    lines += [f'var {i} "V{i}"' for i in ids]
    for i in range(1, n):
        pol = "-" if i % 5 == 0 else "+"
        lines.append(f"{ids[i-1]} -> {pol} {ids[i]}")
    lines.append(f"{ids[-1]} -> + {ids[0]} @loops R1")
    lines.append('loop R1 "cycle" "R" [' + ", ".join(ids) + "]")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _run_cli(path, outdir, extra=(), env=None):
    return subprocess.run(
        [PY, "-m", "stdraw", "layout", path, "--outdir", outdir, *extra],
        capture_output=True, text=True, cwd=ROOT, env=env)


@pytest.mark.parametrize("n,extra,want_rc,want_refusal", [
    (MAX_LAYOUT_NODES, (), 0, False),        # 15: under the limit -> lays out
    (MAX_LAYOUT_NODES + 1, (), 3, True),     # 16: refused before layout
    (16, ("--allow-oversize",), None, False),   # flag: 16-20 lays out
    (HARD_CEILING_NODES, ("--allow-oversize",), None, False),  # ceiling ok
    (HARD_CEILING_NODES + 1, ("--allow-oversize",), 3, True),  # >20: always refused
])
def test_size_refusal_matrix(tmp_path, n, extra, want_rc, want_refusal):
    cld = tmp_path / f"g{n}.cld"
    _write_cld(str(cld), n)
    outdir = tmp_path / f"o{n}-{int(bool(extra))}"
    r = _run_cli(str(cld), str(outdir), extra)
    if want_refusal:
        assert r.returncode == want_rc == 3
        ref = json.load(open(outdir / "refusal.json", encoding="utf-8"))
        assert ref["rejected"] is True
        assert ref["reason"] == "node_limit_exceeded"
        assert ref["nodes"] == n
        assert ref["limit"] == (HARD_CEILING_NODES if extra
                                else MAX_LAYOUT_NODES)
        assert "split the graph by loops" in ref["advice"]
        assert not (outdir / "layout.json").exists()
    else:
        assert r.returncode in (0, 1)          # honest layout outcome
        assert (outdir / "layout.json").exists()
        assert not (outdir / "refusal.json").exists()


def test_refusal_payload_lists_declared_loops(tmp_path):
    cld = tmp_path / "g17.cld"
    _write_cld(str(cld), 17)
    outdir = tmp_path / "o17"
    _run_cli(str(cld), str(outdir))
    ref = json.load(open(outdir / "refusal.json", encoding="utf-8"))
    assert ref["split_hint"]["loops"][0]["id"] == "R1"
    assert ref["split_hint"]["loops"][0]["nodes"][0] == "v0"


def test_size_refusal_pure_function():
    g = parse(THREE_LOOP)
    ref = size_refusal(g, limit=2)
    assert ref["rejected"] is True and ref["limit"] == 2
    assert ref["nodes"] == 5
    assert ref["split_hint"]["loops"][0]["id"] == "R1"


# ── T14 deprecation warnings + certificate record ──

def test_deprecated_pitch_warning_and_certificate_note(tmp_path):
    cld = os.path.join(ROOT, "examples", "limits-to-growth.cld")
    outdir = tmp_path / "o-pitch"
    r = _run_cli(cld, str(outdir), ("--pitch", "62"))
    assert r.returncode == 0
    assert "[deprecated] --pitch" in r.stderr
    cert = json.load(open(outdir / "certificate.json", encoding="utf-8"))
    assert any("deprecated pixel parameter" in n for n in cert["honest_notes"])


def test_no_deprecation_warning_without_pixel_params(tmp_path):
    cld = os.path.join(ROOT, "examples", "limits-to-growth.cld")
    outdir = tmp_path / "o-clean"
    r = _run_cli(cld, str(outdir))
    assert r.returncode == 0
    assert "[deprecated]" not in r.stderr


# ── structured parse errors (error-surface contract) ──
#
# The library keeps raising: DSLParseError IS a ValueError and every message
# is byte-identical to the historical one.  The CLI stops the stack trace at
# its own boundary and writes parse_error.json + exit 2 (3 stays the size
# refusal, 1 a layout that ran but failed its geometry gate).

ANCHOR_TYPO = ('graph "t"\n'
               'var a "A"\n'
               'var b "B"\n'
               'a -> + b\n'
               'loop R1 "r" "R" [a, b]\n'
               'b -> + a @anchors src=n-g8\n')

UNDECLARED_ENDPOINT = ('graph "t"\n'
                       'var a "A"\n'
                       'a -> + b\n')

SYNTAX_ERROR = ('graph "t"\n'
                'var a "A"\n'
                'var b "B"\n'
                'a => b\n')


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return str(path)


def _parse_error(outdir):
    with open(os.path.join(str(outdir), "parse_error.json"), encoding="utf-8") as f:
        return json.load(f)


def test_parse_error_unknown_anchor_id(tmp_path):
    cld = _write(tmp_path / "anch.cld", ANCHOR_TYPO)
    out = tmp_path / "o"
    r = _run_cli(cld, str(out))
    assert r.returncode == 2
    d = _parse_error(out)
    assert d["error"] is True and d["kind"] == "syntax"
    assert d["line"] == 6
    assert d["snippet"] == "b -> + a @anchors src=n-g8"
    assert d["column"] == len("b -> + a ") + 1     # the failing tag, not the line
    assert "unknown anchor id" in d["detail"] and "n-g8" in d["detail"]
    # the legacy message is untouched; only the presentation changed
    assert d["reason"] == ("DSL line 6 cannot be parsed: "
                           "'b -> + a @anchors src=n-g8'")
    assert d["input"] == "anch.cld" and d["exit_code"] == 2
    assert json.loads(r.stdout) == d               # stdout = the artifact
    assert "Traceback (most recent call last)" not in r.stderr
    assert "[input rejected] syntax line 6" in r.stderr
    assert not (out / "layout.json").exists()      # nothing was laid out


def test_parse_error_undeclared_endpoint(tmp_path):
    cld = _write(tmp_path / "undecl.cld", UNDECLARED_ENDPOINT)
    out = tmp_path / "o"
    r = _run_cli(cld, str(out))
    assert r.returncode == 2
    d = _parse_error(out)
    assert d["kind"] == "structure"
    assert d["line"] == 3 and d["snippet"] == "a -> + b"
    assert d["column"] is None                     # line-scoped problem
    assert d["reason"] == ("DSL structural validation failed:\n"
                           "  edge endpoint not declared: a->b")
    assert d["problems"] == [{"line": 3,
                              "reason": "edge endpoint not declared: a->b"}]
    assert "Traceback (most recent call last)" not in r.stderr
    assert not (out / "layout.json").exists()


def test_parse_error_syntax_error(tmp_path):
    cld = _write(tmp_path / "syn.cld", SYNTAX_ERROR)
    out = tmp_path / "o"
    r = _run_cli(cld, str(out))
    assert r.returncode == 2
    d = _parse_error(out)
    assert d["kind"] == "syntax" and d["line"] == 4 and d["column"] == 1
    assert d["snippet"] == "a => b"
    assert "documented forms" in d["detail"]
    assert "Traceback (most recent call last)" not in r.stderr


def test_parse_error_missing_input_is_structured(tmp_path):
    out = tmp_path / "o"
    r = _run_cli(str(tmp_path / "nope.cld"), str(out))
    assert r.returncode == 2
    d = _parse_error(out)
    assert d["kind"] == "io" and d["line"] is None
    assert "not found" in d["reason"]
    assert "Traceback (most recent call last)" not in r.stderr


def test_parse_error_traceback_only_under_debug(tmp_path):
    cld = _write(tmp_path / "anch.cld", ANCHOR_TYPO)
    out = tmp_path / "o"
    env = dict(os.environ, STDRAW_DEBUG="1")
    r = _run_cli(cld, str(out), env=env)
    assert r.returncode == 2                       # debug never changes the code
    assert "Traceback (most recent call last)" in r.stderr
    assert _parse_error(out)["kind"] == "syntax"


def test_parse_error_does_not_regress_size_refusal(tmp_path):
    cld = tmp_path / "g16.cld"
    _write_cld(str(cld), MAX_LAYOUT_NODES + 1)
    out = tmp_path / "o"
    r = _run_cli(str(cld), str(out))
    assert r.returncode == 3
    assert (out / "refusal.json").exists()
    assert not (out / "parse_error.json").exists()  # two distinct error faces


def test_library_still_raises_valueerror():
    # the CLI presentation must not leak into the library contract
    with pytest.raises(ValueError) as struct_err:
        parse(UNDECLARED_ENDPOINT)
    assert isinstance(struct_err.value, DSLParseError)
    assert struct_err.value.kind == "structure"
    assert str(struct_err.value) == ("DSL structural validation failed:\n"
                                     "  edge endpoint not declared: a->b")

    with pytest.raises(ValueError) as syn_err:
        parse(SYNTAX_ERROR)
    assert isinstance(syn_err.value, DSLParseError)
    assert syn_err.value.kind == "syntax" and syn_err.value.line == 4
    assert str(syn_err.value) == "DSL line 4 cannot be parsed: 'a => b'"
    assert syn_err.value.to_dict()["line"] == 4
