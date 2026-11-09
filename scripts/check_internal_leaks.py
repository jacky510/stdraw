#!/usr/bin/env python3
"""Internal-leak sanitization gate (rules: AGENTS.md "Internal-leak sanitization gate").

Fails if any git-tracked file contains internal ops markers:
- internal task/card ids (t_ + 8 hex chars)
- local machine absolute paths under a user home
- internal approval-record phrases

The patterns below are written in a deliberately non-self-matching form:
this file must itself pass this gate.
"""
import os
import re
import subprocess
import sys

LEAK_PATTERNS = [
    (r"t_[0-9a-f]{8}", "internal task/card id"),
    (r"C:[/\\]Users", "local machine absolute path"),
    (r"Feishu\s+approval", "internal approval record"),
]

COMPILED = [(re.compile(p), why) for p, why in LEAK_PATTERNS]


def tracked_files():
    out = subprocess.check_output(["git", "ls-files"], text=True)
    return [f for f in out.splitlines() if f.strip()]


def main():
    root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    offenders = []
    for f in tracked_files():
        path = os.path.join(root, f)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, "rb").read().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pat, why in COMPILED:
            m = pat.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                offenders.append("%s:%d: %s" % (f, line, why))
    if offenders:
        print("INTERNAL-LEAK GATE FAILED:")
        for o in offenders[:50]:
            print("  " + o)
        if len(offenders) > 50:
            print("  ... %d hits total" % len(offenders))
        print("Rules: AGENTS.md 'Internal-leak sanitization gate'")
        return 1
    print("internal-leak gate: clean (%d tracked files scanned)" % len(tracked_files()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
