# -*- coding: utf-8 -*-
"""Delivery-contract metadata tests (card ref-scrubbed).

Coordinate outputs self-declare "coordinates-only" + a warning; the CLI
re-stamps interactive when the full deliverable (demo-2d.html) was
produced; the ortho CLI layout.json stays byte-frozen (production pin,
ci_checks gate A) and carries its delivery contract on certificate.json
instead (interactive / drag_layer fields).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw import __version__
from stdraw.dsl import parse
from stdraw.planar import PlanarLayout, LayoutConfig
from stdraw.layout_auto import layout as auto_layout, AutoConfig
from stdraw.recipes import run as recipes_run
from stdraw.metrics import (certificate, certificate_auto,
                            scene_from_planar, scene_from_auto)

LIMITS = os.path.join(ROOT, "examples", "limits-to-growth.cld")
DELIVERY_KEYS = ("delivery", "interactive", "engine_version",
                 "delivery_warning")


def _graph():
    with open(LIMITS, encoding="utf-8") as f:
        return parse(f.read())


def _cli(args):
    return subprocess.run([sys.executable, "-m", "stdraw", "layout"] + args,
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)


class TestLibraryStamping(unittest.TestCase):
    def test_planar_stamped(self):
        v4 = PlanarLayout(_graph(), LayoutConfig(pitch=62)).run()
        self.assertEqual(v4["delivery"], "coordinates-only")
        self.assertIs(v4["interactive"], False)
        self.assertEqual(v4["engine_version"], __version__)
        self.assertIn("demo-2d.html", v4["delivery_warning"])

    def test_auto_stamped(self):
        v4 = auto_layout(_graph(), AutoConfig())
        self.assertEqual(v4["delivery"], "coordinates-only")
        self.assertIs(v4["interactive"], False)
        self.assertEqual(v4["engine_version"], __version__)
        self.assertIn("demo-2d.html", v4["delivery_warning"])

    def test_recipes_stamped(self):
        g = _graph()
        v4o = recipes_run("ortho-v1", g, None)
        self.assertEqual(v4o["delivery"], "coordinates-only")
        self.assertIn("demo-2d.html", v4o["delivery_warning"])
        v4a = recipes_run("auto-v2", g, None)
        self.assertEqual(v4a["delivery"], "coordinates-only")
        self.assertIn("demo-2d.html", v4a["delivery_warning"])

    def test_suppress_warning_is_explicit_opt_out(self):
        g = _graph()
        v4o = recipes_run("ortho-v1", g, None, suppress_delivery_warning=True)
        self.assertNotIn("delivery_warning", v4o)
        self.assertEqual(v4o["delivery"], "coordinates-only")
        self.assertIs(v4o["interactive"], False)
        v4a = recipes_run("auto-v2", g, None, suppress_delivery_warning=True)
        self.assertNotIn("delivery_warning", v4a)
        self.assertEqual(v4a["delivery"], "coordinates-only")

    def test_certificate_defaults_confess_static(self):
        v4 = PlanarLayout(_graph(), LayoutConfig(pitch=62)).run()
        cert = certificate(scene_from_planar(v4))
        self.assertEqual(cert["interactive"], "no")
        self.assertEqual(cert["drag_layer"], "no")

    def test_certificate_cli_flags_confess_interactive(self):
        v4 = auto_layout(_graph(), AutoConfig())
        cert = certificate_auto(scene_from_auto(v4),
                                interactive="yes", drag_layer="yes")
        self.assertEqual(cert["interactive"], "yes")
        self.assertEqual(cert["drag_layer"], "yes")


class TestCliDelivery(unittest.TestCase):
    def test_ortho_layout_frozen_and_cert_confesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ortho")
            r = _cli([LIMITS, "--outdir", out, "--recipe", "ortho",
                      "--pitch", "62"])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, "layout.json"), "rb") as f:
                raw = f.read()
            base = os.path.join(ROOT, "tests", "baselines",
                                "limits-to-growth.layout.json")
            with open(base, "rb") as f:
                self.assertEqual(raw, f.read())  # production pin intact
            layout = json.loads(raw)
            for k in DELIVERY_KEYS:
                self.assertNotIn(k, layout)
            with open(os.path.join(out, "certificate.json"),
                      encoding="utf-8") as f:
                cert = json.load(f)
            self.assertEqual(cert["interactive"], "yes")
            self.assertEqual(cert["drag_layer"], "yes")

    def test_auto_layout_interactive_no_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "auto")
            r = _cli([LIMITS, "--outdir", out, "--skip-3d"])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, "layout.json"), encoding="utf-8") as f:
                layout = json.load(f)
            self.assertEqual(layout["delivery"], "stdraw-cli")
            self.assertIs(layout["interactive"], True)
            self.assertNotIn("delivery_warning", layout)
            self.assertEqual(layout["engine_version"], __version__)
            with open(os.path.join(out, "certificate.json"),
                      encoding="utf-8") as f:
                cert = json.load(f)
            self.assertEqual(cert["interactive"], "yes")
            self.assertEqual(cert["drag_layer"], "yes")

    def test_deterministic_stamping_double_run(self):
        outs = []
        with tempfile.TemporaryDirectory() as tmp:
            for i in (1, 2):
                out = os.path.join(tmp, "auto-%d" % i)
                r = _cli([LIMITS, "--outdir", out, "--skip-3d"])
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(os.path.join(out, "layout.json"), "rb") as f:
                    outs.append(f.read())
        self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
