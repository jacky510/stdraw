"""CI wrapper for the docs consistency gate.

The gate itself lives in scripts/check_docs_consistency.py and is runnable
stand-alone (python scripts/check_docs_consistency.py, --fix to auto-repair).
This test keeps it inside the regular pytest suite so a version bump or a
mode-chain change that forgets the docs turns CI red.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docs_consistency_gate():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_docs_consistency.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 0, (
        "docs consistency drift (run 'python scripts/check_docs_consistency."
        "py --fix' locally):\n" + r.stdout + r.stderr
    )
