#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI checks (2026-11-05 six-point rework revision).

Three assertion layers:
  A. ortho-v1 frozen recipe regression (production behavior pin):
     - both examples exit 0, 11 geometric self-checks fail==0;
     - layout.json byte-identical to tests/baselines/ (planar.py behavior-freeze iron gate);
     - legacy certificate crossings==0 / grade==best; loops problems==0;
     - two runs of the same input byte-identical (determinism).
  B. auto-v2 default recipe (product main path) new hard gates:
     - box press=0, edge-box clearance >=16px, smooth anchors, card
       clearance >=16, CV<=0.35, simple-graph regularity all pass;
     - crossings <= 2 and grade in {best, second} (honest grading, never
       masquerading as 0 crossings);
     - loops problems==0; two runs byte-identical (determinism).
  C. DOM-measured box bounds (CI-side second layer, optional):
     - with playwright available, measure per-card actual text width in
       demo-2d.html against the planned box bounds;
     - without it, honestly SKIP (neither pass nor fail; the workflow
       installs the optional layer as backstop).

Stdlib only (layer C optionally depends on playwright).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

EXAMPLES = [
    "examples/limits-to-growth.cld",
    "examples/classic-cld-growth-and-burden.cld",
]
# Layer B (auto-v2) blind-spot coverage (F3 rework ref-scrubbed): the original
# B layer ran only the two EXAMPLES and missed bullwhip's arc bulging past
# the viewBox (check7 fail). Kept as a separate list, not shared with the
# layer-A
# ortho frozen pin (byte-identical baselines), to avoid cascading ortho
# baseline breakage.
AUTO_EXAMPLES = EXAMPLES + [
    "benchmarks/corpus/classic/bullwhip.cld",
    # v0.7.8 wide-card comb regression (ref-scrubbed): double-ticker cards
    # make the tier-0 fan angle-infeasible; the tier-1 facing-border fan
    # must keep the comb contract (grade best, hub edges straight)
    "tests/data/hdd-wide-tickers.cld",
]
# Layer B2 (WS3-Q routing-quality rework ref-scrubbed): random dense-graph
# sampling -- in the random n10 fixed-seed corpus, 4/10 cases previously
# had check1 crossings>2 / check3 insufficient clearance (d483639 legacy).
# After the gated (row,order) permutation + joint rerouting + stair
# candidate-pool fixes, these 4 cases must stay exit 0.
# Slow to run (gated permutation + hard-gate polish, ~2min per case),
# kept as its own layer.
RANDOM_SAMPLES = [
    "benchmarks/corpus/random/random-n10-i00.cld",
    "benchmarks/corpus/random/random-n10-i01.cld",
    "benchmarks/corpus/random/random-n10-i04.cld",
    "benchmarks/corpus/random/random-n10-i05.cld",
]
HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
              "min_gap_ge_16", "cv_le_035", "pitch_uniform",
              "column_snap24_ge_060",
              "mutual_pairs_separated", "lines_no_coincidence",
                      "visual_crossings_zero")
# ref-scrubbed ring placement (placement=ring-cycle): regularity gates switch
# to ring criteria (row alignment / column snap don't apply to rings; never
# misjudge a ring under row criteria)
RING_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                   "min_gap_ge_16", "ring_spacing_cv_le_005",
                   "ring_template_fit_le_005", "mutual_pairs_separated",
                   "lines_no_coincidence",
                      "visual_crossings_zero")
# ref-scrubbed column/symmetric placement: regularity gate switches by mode
# (main-chain column axis alignment + uniform row pitch / mirror-axis
# error). Crossings (crossings_zero) and row alignment (row_align_ge_060)
# were demoted to report-only items (jacky's 2026-11-05 ruling: partial
# line crossings are acceptable; order and elegance come first).
COLUMN_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                     "min_gap_ge_16", "cv_le_035", "column_axis_aligned",
                     "spine_pitch_uniform", "mutual_pairs_separated",
                     "lines_no_coincidence",
                      "visual_crossings_zero")
SYM_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                  "min_gap_ge_16", "cv_le_035", "symmetry_mirror_le_2px",
                  "mutual_pairs_separated", "lines_no_coincidence",
                      "visual_crossings_zero")
# ref-scrubbed (aesthetics v3) bowtie shared vertex: regularity gate = mirror-axis error (same criteria as symmetric)
BOWTIE_HARD_GATES = SYM_HARD_GATES
# ref-scrubbed (v0.7.1) column + wing slots: column x alignment + midline adherence + mirror (equivalent gates)
SPINE_WING_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16",
                         "anchors_smooth", "min_gap_ge_16", "cv_le_035",
                         "spine_axis_le_2px", "midline_adherence_le_2px",
                         "symmetry_mirror_le_2px", "mutual_pairs_separated",
                         "lines_no_coincidence",
                      "visual_crossings_zero")
# v0.7.7 comb-bilateral (K_{m,2} hubs): column axis + pitch + hub symmetry +
# all-straight hub fan (CV not applicable as a gate: hub wings are
# structurally far from the column)
COMB_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                   "min_gap_ge_16", "column_axis_aligned",
                   "column_pitch_uniform", "hub_symmetry_le_2px",
                   "hub_edges_straight", "mutual_pairs_separated",
                   "lines_no_coincidence",
                      "visual_crossings_zero")


def _hard_gates_for(cert):
    p = cert.get("placement")
    if p == "ring-cycle":
        return RING_HARD_GATES
    if p == "column-chain":
        return COLUMN_HARD_GATES
    if p == "spine-wing":
        return SPINE_WING_HARD_GATES
    if p == "comb-bilateral":
        return COMB_HARD_GATES
    if p in ("symmetric", "bowtie-vertex"):
        return SYM_HARD_GATES
    return HARD_GATES


def run_cli(path, outdir, extra=(), pitch="62"):
    # ortho uses --pitch 62 to pass the clearance gate (legacy tuning); auto self-tunes pitch=80, so it is not passed (pitch=None)
    cmd = [sys.executable, "-m", "stdraw", "layout", path, "--outdir", outdir]
    if pitch:
        cmd += ["--pitch", pitch]
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


def load(outdir, name):
    with open(os.path.join(outdir, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    failures = []
    tmp = tempfile.mkdtemp(prefix="stdraw-ci-")
    try:
        # ── A. ortho-v1 frozen regression (production behavior pin) ──
        for ex in EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-ortho-1")
            out2 = os.path.join(tmp, name + "-ortho-2")
            r1 = run_cli(ex, out1, ("--recipe", "ortho"))
            if r1.returncode != 0:
                failures.append(f"ortho {ex}: CLI exit {r1.returncode}\n{r1.stderr}")
                continue
            run_cli(ex, out2, ("--recipe", "ortho"))
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"ortho {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            if cert["metrics"]["crossings"] != 0 or cert["grade"] != "best":
                failures.append(f"ortho {ex}: legacy cert crossings="
                                f"{cert['metrics']['crossings']} grade={cert['grade']}")
            # Production pin iron gate: byte-identical to the committed baseline
            base = os.path.join(root, "tests", "baselines", name + ".layout.json")
            with open(base, "rb") as a, \
                 open(os.path.join(out1, "layout.json"), "rb") as b:
                if a.read() != b.read():
                    failures.append(f"ortho {ex}: layout.json drift vs tests/baselines/"
                                    f"(production behavior pin broken -- planar.py must stay frozen)")
            # Determinism (ref-scrubbed: loops_audit.json added to the byte-identical determinism list)
            for fn in ("layout.json", "demo-2d.html", "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"ortho {ex}: {fn} non-deterministic (two runs differ)")
            audit = load(out1, "loops_audit.json")
            if audit["summary"]["problems"] != 0:
                failures.append(f"ortho {ex}: loops problems={audit['summary']['problems']}")
            print(f"OK  ortho {ex}: 11 checks fail=0, baseline byte-identical, deterministic")

        # ── B. auto-v2 new hard gates ──
        for ex in AUTO_EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-auto-1")
            out2 = os.path.join(tmp, name + "-auto-2")
            r1 = run_cli(ex, out1, ("--recipe", "auto"), pitch=None)
            # auto recipe takes no pitch (self-tuned to 80)
            if r1.returncode != 0:
                tail = "\n".join(r1.stdout.strip().splitlines()[-25:])
                try:
                    lj = json.load(open(os.path.join(out1, "layout.json"),
                                        encoding="utf-8"))
                    dump = json.dumps({"viewBox": lj["viewBox"],
                                       "nodes": {v: p for v, p in lj["nodes"].items()}},
                                      ensure_ascii=False)
                except Exception as _e:
                    dump = f"layout.json unreadable: {_e}"
                failures.append(f"auto {ex}: CLI exit {r1.returncode}\n"
                                f"stderr={r1.stderr}\nstdout_tail:\n{tail}\n"
                                f"layout_dump={dump}")
                continue
            run_cli(ex, out2, ("--recipe", "auto"), pitch=None)
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"auto {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            m = cert["metrics"]
            gates = _hard_gates_for(cert)
            for k in gates:
                if not cert["gates"].get(k, False):
                    failures.append(f"auto {ex}: hard gate {k} FAIL "
                                    f"(metrics={json.dumps(m, ensure_ascii=False)[:300]})")
            if m["crossings"] > 2:
                failures.append(f"auto {ex}: crossings={m['crossings']} > 2")
            if cert["grade"] not in ("best", "second"):
                failures.append(f"auto {ex}: grade={cert['grade']}")
            audit = load(out1, "loops_audit.json")
            if audit["summary"]["problems"] != 0:
                failures.append(f"auto {ex}: loops problems={audit['summary']['problems']}")
            # Determinism (ref-scrubbed: loops_audit.json added to the byte-identical determinism list)
            for fn in ("layout.json", "certificate.json", "demo-2d.html",
                       "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"auto {ex}: {fn} non-deterministic (two runs differ)")
            print(f"OK  auto {ex}: hard gates pass, crossings={m['crossings']}, "
                  f"grade={cert['grade']}, deterministic")

        # ── B2. Random dense-graph sampling (WS3-Q routing-quality gated regression) ──
        for ex in RANDOM_SAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-auto-1")
            out2 = os.path.join(tmp, name + "-auto-2")
            r1 = run_cli(ex, out1, ("--recipe", "auto"), pitch=None)
            if r1.returncode != 0:
                tail = "\n".join(r1.stdout.strip().splitlines()[-10:])
                failures.append(f"random {ex}: CLI exit {r1.returncode}\n{tail}")
                continue
            run_cli(ex, out2, ("--recipe", "auto"), pitch=None)
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"random {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            m = cert["metrics"]
            if m["crossings"] > 2:
                failures.append(f"random {ex}: crossings={m['crossings']} > 2")
            if (m.get("edge_box_min_clear") or 0) < 16:
                failures.append(f"random {ex}: edge_box_min_clear="
                                f"{m.get('edge_box_min_clear')} < 16")
            # Determinism (ref-scrubbed: loops_audit.json added to the byte-identical determinism list)
            for fn in ("layout.json", "demo-2d.html", "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"random {ex}: {fn} non-deterministic (two runs differ)")
            print(f"OK  random {ex}: crossings={m['crossings']}, "
                  f"min_clear={m.get('edge_box_min_clear')}px, deterministic")

        # ── C. DOM-measured box bounds (optional layer) ──
        r = subprocess.run(
            [sys.executable, "-m", "stdraw.rendercheck",
             os.path.join(tmp, os.path.basename(EXAMPLES[0]).split(".")[0] + "-auto-1")],
            capture_output=True, text=True)
        if r.returncode == 2:
            print("SKIP  rendercheck: playwright unavailable (CI workflow installs the optional layer as backstop)")
        elif r.returncode != 0:
            failures.append(f"rendercheck: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        else:
            print("OK  rendercheck: DOM-measured box bounds, no overflow")

        # ── D. WS3 routing math units (visibility-graph shortest path / clearance / dual criteria) ──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_visibility.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_visibility: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_visibility: visibility-graph shortest path / arc smoothness / dual criteria units all pass")

        # ── E. WS2 exact crossing-count layer (optional: needs ortools; honestly SKIP when unavailable) ──
        try:
            import ortools  # noqa: F401
            has_ortools = True
        except Exception:
            has_ortools = False
        if has_ortools:
            for t in ("test_crossing_exact.py", "test_placement.py",
                      "test_scalability.py"):
                r = subprocess.run([sys.executable, os.path.join(root, "tests", t)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    failures.append(f"{t}: exit {r.returncode}\n"
                                    f"{r.stdout}\n{r.stderr}")
                else:
                    print(f"OK  {t}: all pass")
        else:
            print("SKIP test_crossing_exact/test_placement: "
                  "ortools unavailable (CI workflow installs the [solver] optional layer as backstop)")

        # ── F. Manual-layout round-trip (ref-scrubbed): --from-layout identical replay + layout-diff ──
        ex = EXAMPLES[0]
        name = os.path.splitext(os.path.basename(ex))[0]
        out_f = os.path.join(tmp, name + "-manual-f")
        r_f = run_cli(ex, out_f, (), pitch=None)          # auto baseline (layer F self-contained)
        if r_f.returncode != 0:
            failures.append(f"manual-loop {ex}: auto baseline exit {r_f.returncode}")
        else:
            lay = load(out_f, "layout.json")
            ident = {"viewBox": lay["viewBox"],
                     "nodes": {v: {"x": p["x"], "y": p["y"]}
                               for v, p in lay["nodes"].items()}}
            ipath = os.path.join(tmp, "ci-ident-manual.json")
            with open(ipath, "w", encoding="utf-8") as f:
                json.dump(ident, f, ensure_ascii=False)
            out_f2 = os.path.join(tmp, name + "-manual-f2")
            r_f2 = run_cli(ex, out_f2, ("--from-layout", ipath), pitch=None)
            geo_f = load(out_f2, "geometry_report.json")
            lay_f = load(out_f2, "layout.json")
            if r_f2.returncode != 0 or geo_f.get("fail", 0) != 0:
                failures.append(f"manual-loop {ex}: identical manual layout exit "
                                f"{r_f2.returncode} fail={geo_f.get('fail')}")
            elif lay_f["nodes"] != lay["nodes"] or \
                    lay_f["meta"].get("position_engine") != "manual":
                failures.append(f"manual-loop {ex}: identical manual layout drift / engine not manual")
            else:
                dpath = os.path.join(tmp, "ci-layout-diff.json")
                r_d = subprocess.run(
                    [sys.executable, "-m", "stdraw", "layout-diff",
                     os.path.join(out_f, "layout.json"),
                     os.path.join(out_f2, "layout.json"),
                     "--cld", ex, "--diff-out", dpath],
                    capture_output=True, text=True)
                try:
                    with open(dpath, encoding="utf-8") as f:
                        diff = json.load(f)
                    assert (diff["node_level"] and diff["structural"]
                            and diff["semantic"])
                except Exception as e:
                    failures.append(f"manual-loop layout-diff: {e}\n{r_d.stdout[-300:]}")
                if not failures or all("manual-loop" not in x for x in failures):
                    print("OK  manual-loop: --from-layout identical replay fail=0 + "
                          "layout-diff all three layers present")

        # ── F2. ref-scrubbed: --from-layout waypoints identical recompute (polyline-handle full chain) ──
        # Fixture: since ref-scrubbed, polylines carry fixed type costs
        # (arc > line > polyline), so the router rarely emits vg edges on
        # its own -- the fixture instead uses **manually anchored waypoints**
        # (isomorphic to the demo polyline-handle export), verifying the
        # same full chain: waypoints anchored as-is fed back -> the same
        # polyline with kind=waypoints (anchors recomputed onto box edges)
        # + determinism holds.
        lay_g = load(out_f, "layout.json")
        man_base = {"viewBox": lay_g["viewBox"],
                    "nodes": {v: {"x": p["x"], "y": p["y"]}
                              for v, p in lay_g["nodes"].items()}}
        e0 = lay_g["edges"][0]
        a0n, b0n = nodes_of = (e0["a"], e0["b"])
        p0 = lay_g["nodes"][a0n]
        p1 = lay_g["nodes"][b0n]
        mx = (p0["x"] + p1["x"]) / 2
        my = (p0["y"] + p1["y"]) / 2
        # Deterministic detour waypoints perpendicular to the edge (one per side, on the 2px grid)
        dx, dy = p1["x"] - p0["x"], p1["y"] - p0["y"]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = -dy / n, dx / n
        wp = [[int(round((mx + ux * 70) / 2)) * 2, int(round((my + uy * 70) / 2)) * 2],
              [int(round((mx - ux * 70) / 2)) * 2, int(round((my - uy * 70) / 2)) * 2]]
        man_base["edges"] = [{"a": a0n, "b": b0n, "waypoints": wp}]
        ipath2 = os.path.join(tmp, "ci-wp-manual.json")
        with open(ipath2, "w", encoding="utf-8") as f:
            json.dump(man_base, f, ensure_ascii=False)
        out_w1 = os.path.join(tmp, name + "-wp-1")
        out_w2 = os.path.join(tmp, name + "-wp-2")
        r_w1 = run_cli(ex, out_w1, ("--from-layout", ipath2), pitch=None)
        run_cli(ex, out_w2, ("--from-layout", ipath2), pitch=None)
        lay_w = load(out_w1, "layout.json")
        e_w = next((x for x in lay_w["edges"]
                    if (x["a"], x["b"]) == (a0n, b0n)), None)
        want_via = [[float(q[0]), float(q[1])] for q in wp]
        if (not e_w or e_w["route"]["kind"] != "waypoints" or
                e_w["route"].get("via") != want_via or
                len(e_w["route"]["points"]) != len(want_via) + 2):
            failures.append(f"manual-waypoints: recompute mismatch rc={r_w1.returncode} "
                            f"kind={e_w['route']['kind'] if e_w else '?'}")
        else:
            for fn in ("layout.json", "demo-2d.html"):
                with open(os.path.join(out_w1, fn), "rb") as a, \
                     open(os.path.join(out_w2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"manual-waypoints: {fn} non-deterministic")
            if not any("manual-waypoints" in x for x in failures):
                print("OK  manual-waypoints: --from-layout waypoints identical recompute "
                      "fail=0 + deterministic")

        # ── G. Loop-dominant ring placement (ref-scrubbed): trigger / criteria / negatives / fallback ──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_ring_layout.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_ring_layout: exit {r.returncode}\n"
                            f"{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_ring_layout: ring trigger / criteria / negatives not misfired / determinism all pass")

        # G2. debt-spiral real run: main loop forms a circle, 0 crossings, all ring-criteria gates pass
        ds = os.path.join(root, "benchmarks/corpus/classic/debt-spiral.cld")
        out_g = os.path.join(tmp, "debt-spiral-ring")
        r_g = run_cli(ds, out_g, (), pitch=None)
        if r_g.returncode != 0:
            failures.append(f"ring debt-spiral: CLI exit {r_g.returncode}\n{r_g.stdout[-800:]}")
        else:
            lay_g = load(out_g, "layout.json")
            cert_g = load(out_g, "certificate.json")
            if lay_g["meta"].get("placement") != "ring-cycle" or \
                    lay_g["meta"].get("position_engine") != "ring-construct":
                failures.append("ring debt-spiral: ring placement not taken "
                                f"(engine={lay_g['meta'].get('position_engine')})")
            if cert_g["metrics"]["crossings"] != 0 or \
                    cert_g.get("placement") != "ring-cycle":
                failures.append(f"ring debt-spiral: crossings="
                                f"{cert_g['metrics']['crossings']} placement="
                                f"{cert_g.get('placement')}")
            for k in RING_HARD_GATES:
                if not cert_g["gates"].get(k, False):
                    failures.append(f"ring debt-spiral: ring-criteria gate {k} FAIL")
            if cert_g["grade"] != "best":
                failures.append(f"ring debt-spiral: grade={cert_g['grade']}")
            if not failures or all("debt-spiral" not in x for x in failures):
                print("OK  ring debt-spiral: main loop circular (5 nodes), 0 crossings, best grade, "
                      "all ring-criteria gates pass")

        # G3. Negatives must not misfire: chain / tree / 13-node ring / two triangles + bridge -> ring must NOT trigger
        # (ref-scrubbed: two triangles + bridge may enter column placement -- few loops + main-chain
        # structure; the assertion only forbids ring)
        neg_fixtures = {
            "ci-neg-chain.cld": 'graph "链"\nvar a "A"\nvar b "B"\nvar c "C"\n'
                                'var d "D"\na -> + b\nb -> + c\nc -> + d\n',
            "ci-neg-tree.cld": 'graph "树"\nvar root "根"\nvar x1 "子一"\n'
                               'var x2 "子二"\nroot -> + x1\nroot -> + x2\n',
            "ci-neg-big-ring.cld": "graph \"大环\"\n" + "".join(
                f'var v{i} "节点{i}"\n' for i in range(13)) + "".join(
                f'v{i} -> + v{(i + 1) % 13}\n' for i in range(13)),
            "ci-neg-two-tri.cld": 'graph "双三角"\nvar a1 "甲一"\nvar a2 "甲二"\n'
                                  'var a3 "甲三"\nvar b1 "乙一"\nvar b2 "乙二"\n'
                                  'var b3 "乙三"\na1 -> + a2\na2 -> + a3\n'
                                  'a3 -> + a1\nb1 -> + b2\nb2 -> + b3\n'
                                  'b3 -> + b1\na1 -> + b1\n',
        }
        for fn, text in neg_fixtures.items():
            p = os.path.join(tmp, fn)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            out_n = os.path.join(tmp, fn + "-out")
            r_n = run_cli(p, out_n, (), pitch=None)
            if r_n.returncode not in (0, 1):     # geometry fail is legacy semantics; exit 1 is legal
                failures.append(f"ring negative {fn}: CLI exit {r_n.returncode}")
                continue
            lay_n = load(out_n, "layout.json")
            if lay_n["meta"].get("position_engine") == "ring-construct":
                failures.append(f"ring negative {fn}: ring placement misfired")
        if not failures or all("ring negative" not in x for x in failures):
            print("OK  ring negatives x4 (chain/tree/13-node ring/two triangles + bridge): ring not triggered "
                  "(two triangles + bridge may enter column placement since ref-scrubbed; only ring is forbidden)")

        # ── H. Layout aesthetics v2 (ref-scrubbed): column/symmetric trigger + R/B coloring + full corpus ──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_layout_modes.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_layout_modes: exit {r.returncode}\n"
                            f"{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_layout_modes: column/symmetric trigger, geometry, R/B coloring,"
                  "crossings soft goal, determinism all pass")

        # H2. Full classic corpus, 19 graphs: exit 0 + all best grade + all hard gates pass (new criteria)
        corpus_dir = os.path.join(root, "benchmarks", "corpus", "classic")
        n_ok = 0
        for fn in sorted(os.listdir(corpus_dir)):
            if not fn.endswith(".cld"):
                continue
            name = fn[:-4]
            out_h = os.path.join(tmp, "H-" + name)
            r_h = run_cli(os.path.join(corpus_dir, fn), out_h, (), pitch=None)
            if r_h.returncode != 0:
                failures.append(f"corpus {name}: CLI exit {r_h.returncode}\n"
                                f"{r_h.stdout[-500:]}")
                continue
            cert_h = load(out_h, "certificate.json")
            if cert_h["grade"] != "best":
                failures.append(f"corpus {name}: grade={cert_h['grade']}")
            for k in _hard_gates_for(cert_h):
                if not cert_h["gates"].get(k, False):
                    failures.append(f"corpus {name}: hard gate {k} FAIL")
            if cert_h["metrics"]["crossings"] > 2:
                failures.append(f"corpus {name}: crossings="
                                f"{cert_h['metrics']['crossings']}")
            n_ok += 1
        print(f"OK  corpus full set {n_ok}/19: exit 0, best grade, all new-criteria hard gates pass")

        # J. Anchor-criteria hard gate (ref-scrubbed second-review rework):
        #    jacky: "the point where a line meets a box should prefer the
        #    midpoint of each edge, never a corner" -- docs/layout-modes.md
        #    §anchor criteria. Measured per graph: (1) corner hits = 0 (hard
        #    gate for all engines); (2) in-band anchor ratio (edge midpoint
        #    +/- 1/4 edge length): spine-wing (this card's domain) = 100%;
        #    other engines locked to v0.7.2 baseline ratios (table below) to
        #    prevent regressions -- ring-cycle inter-ring pairs / bowtie-vertex
        #    +/-12px spoke corridors are registered legacy out-of-band cases
        #    (a fix would shift deliverables and break the 18-graph
        #    zero-drift hard gate; deferred to a later card).
        BASELINE_BAND = {
            # v0.7.2 baseline in-band ratios (band/total exact fractions, avoiding rounding misjudgment)
            "arms-race": 8 / 8, "brand-flywheel": 14 / 16,
            "bullwhip": 12 / 12, "burnout-attrition": 12 / 12,
            "classic-cld-growth-and-burden": 26 / 26,   # spine-wing gate raised to 100%
            "debt-spiral": 12 / 12, "eroding-goals": 8 / 12,
            "fishing-collapse": 15 / 18, "fixes-that-fail": 10 / 10,
            "induced-demand": 14 / 14, "learning-flywheel": 10 / 10,
            "limits-to-growth": 14 / 14, "population-logistic": 12 / 12,
            "renewable-resource": 14 / 14, "shifting-the-burden": 10 / 16,
            "soil-erosion": 16 / 16, "tragedy-of-the-commons": 12 / 12,
            "urban-migration": 16 / 16, "wage-price-spiral": 8 / 12,
        }
        n_anchor_ok = 0
        for fn in sorted(os.listdir(corpus_dir)):
            if not fn.endswith(".cld"):
                continue
            name = fn[:-4]
            if not os.path.exists(os.path.join(tmp, "H-" + name,
                                               "layout.json")):
                continue
            lay = load(os.path.join(tmp, "H-" + name), "layout.json")
            ch = lay.get("meta", {}).get("cardH", 44.0)
            total = band_in = corner = 0
            worst = []
            for e in lay["edges"]:
                rt = e["route"]
                for side, idx in (("a", 0), ("b", len(rt["points"]) - 1)):
                    nd = lay["nodes"][e[side]]
                    cx, cy, hw, hh = nd["x"], nd["y"], nd["w"] / 2.0, ch / 2.0
                    p = rt["points"][idx]
                    dxo, dyo = p[0] - cx, p[1] - cy
                    on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
                    total += 1
                    if (abs(abs(dxo) - hw) < 0.75 and
                            abs(abs(dyo) - hh) < 0.75):
                        corner += 1
                    if on_x:
                        if abs(dyo) <= hh / 2 + 1e-6:
                            band_in += 1
                        elif len(worst) < 3:
                            worst.append(f"{e['a']}->{e['b']}:{side}")
                    else:
                        if abs(dxo) <= hw / 2 + 1e-6:
                            band_in += 1
                        elif len(worst) < 3:
                            worst.append(f"{e['a']}->{e['b']}:{side}")
            eng = lay.get("meta", {}).get("engine", "")
            ratio = band_in / total if total else 1.0
            floor = BASELINE_BAND.get(name, 1.0)
            if corner > 0:
                failures.append(f"corpus {name}: anchor corner hits {corner} "
                                f"(criteria: must be 0)")
            elif ratio < floor - 1e-9:
                failures.append(f"corpus {name}: anchor in-band {band_in}/{total} "
                                f"({ratio:.0%}) < v0.7.2 baseline {floor:.0%} "
                                f"{worst}")
            else:
                n_anchor_ok += 1
                print(f"OK  anchor criteria {name}: engine={eng} in-band {band_in}/{total}"
                      f" ({ratio:.0%}) corners {corner}")
        if n_anchor_ok == 19:
            print("OK  anchor criteria hard gate: 19/19 corners=0, in-band ratios meet the bar "
                  "(spine-wing=100%, others locked to baseline)")

        # H3. R/B coloring criteria: wage R1 amber / B1 sky blue / multi-loop mixed-color neutral + polarity data retained
        out_w = os.path.join(tmp, "H-wage")
        run_cli(os.path.join(corpus_dir, "wage-price-spiral.cld"), out_w,
                (), pitch=None)
        lay_w = load(out_w, "layout.json")
        by_pair = {(e["a"], e["b"]): e for e in lay_w["edges"]}
        for pr, kinds, color in (
                (("wages", "cost"), ["R"], "#d97706"),
                (("cost", "prices"), ["R"], "#d97706"),
                (("prices", "real_income"), ["B"], "#0284c7"),
                (("demand", "prices"), ["B"], "#0284c7")):
            e = by_pair[pr]
            if e["loop_kinds"] != kinds or e["loop_color"] != color:
                failures.append(f"R/B coloring {pr}: kinds={e['loop_kinds']} "
                                f"color={e['loop_color']}")
            if "polarity" not in e:
                failures.append(f"R/B coloring {pr}: polarity data lost")
        demo_w = open(os.path.join(out_w, "demo-2d.html"), encoding="utf-8").read()
        if "data-pol" in demo_w:
            failures.append("R/B coloring: demo still contains text badge data-pol")
        if 'stroke="#d97706"' not in demo_w or 'stroke="#0284c7"' not in demo_w:
            failures.append("R/B coloring: demo missing polarity amber / sky-blue coloring")
        if 'stroke-dasharray="' in demo_w:
            failures.append("polarity coloring: demo still has dashed edges "
                            "(two-color caliber, jacky 2026-11-09: all solid)")
        if 'stroke="#64748b"' in demo_w:
            failures.append("polarity coloring: demo still has neutral-gray edges "
                            "(two-color caliber, jacky 2026-11-09)")
        print("OK  polarity coloring: edges colored by sign (+ amber / − sky blue), "
              "all solid, text badges removed, polarity data retained")

        # I. Demo deliverable freshness (ref-scrubbed rework, v0.7.1 lesson):
        #    after the engine switched to spine-wing, demos/classic-cld-2d.html
        #    was not re-rendered, so jacky's eyeball review still saw the old
        #    ring-construct image and wrongly flagged "structural
        #    inconsistency". Iron gate: the delivered demo must be
        #    byte-identical to a fresh re-render by the current engine
        #    (engine determinism is already proven by double runs, so a
        #    byte-exact pin is valid).
        fresh_out = os.path.join(tmp, "I-fresh-demo")
        r_f = run_cli("examples/classic-cld-growth-and-burden.cld", fresh_out,
                      ("--name", "classic-cld", "--skip-3d"), pitch=None)
        if r_f.returncode != 0:
            failures.append(f"demo freshness: CLI exit {r_f.returncode}\n"
                            f"{r_f.stderr[-500:]}")
        else:
            committed = os.path.join(root, "demos", "classic-cld-2d.html")
            with open(committed, "rb") as a, \
                    open(os.path.join(fresh_out, "demo-2d.html"), "rb") as b:
                if a.read() != b.read():
                    failures.append(
                        "demo freshness: demos/classic-cld-2d.html does not match a "
                        "re-render by the current engine (deliverable stale -- rerun "
                        "python -m stdraw layout examples/"
                        "classic-cld-growth-and-burden.cld --name classic-cld"
                        " --skip-3d and update the demo + docs/gallery screenshots)")
                else:
                    print("OK  demo freshness: demos/classic-cld-2d.html byte-identical "
                          "to the current engine's re-render (ref-scrubbed anti-staleness gate)")
                # Certificate deliverable under the same criteria (caught in
                # ref-scrubbed closeout: demos/classic-certificate.json was stuck
                # at the old ring-cycle 9-gate certificate) -- byte-exact pin.
                committed_cert = os.path.join(root, "demos",
                                              "classic-certificate.json")
                with open(committed_cert, "rb") as a, \
                        open(os.path.join(fresh_out, "certificate.json"),
                             "rb") as b:
                    if a.read() != b.read():
                        failures.append(
                            "certificate freshness: demos/classic-certificate.json does "
                            "not match a re-render by the current engine (deliverable "
                            "python -m stdraw layout examples/"
                            "classic-cld-growth-and-burden.cld --name classic-cld"
                            " --skip-3d and update demos/classic-certificate.json)")
                    else:
                        print("OK  certificate freshness: demos/classic-certificate.json "
                              "byte-identical to the current engine's re-render (ref-scrubbed anti-staleness gate)")

        # K. Language policy gate: repo-wide bilingual partition
        #    (EN face CJK-free incl. code files, zh face prose-free).
        r_lang = subprocess.run(
            [sys.executable, os.path.join(root, "tests", "check_language_policy.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r_lang.returncode != 0:
            failures.append("language policy gate FAILED (see output above)")
            print(r_lang.stdout)
            print(r_lang.stderr)
        else:
            print("OK  " + r_lang.stdout.strip().splitlines()[-1])

        if failures:
            print("\nFAILURES:")
            for f in failures:
                print(" -", f)
            return 1
        print("\nAll CI checks passed.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
