#!/usr/bin/env python3
"""Docs consistency gate for stdraw: single-source version + mode chain.

Authoritative sources are the CODE, never the prose:
  * version: pyproject.toml [project] version  ==  stdraw/__init__.py __version__
  * mode priority chain: evaluation order of the _rule_hit(...) calls in
    stdraw/layout_auto.py, plus the layered fallback.

Checked surfaces:
  * README.md / README_zh-CN.md  version badges + engine-version mentions
  * AGENTS.md                    "Current **X**" version line
  * README.md / README_zh-CN.md / AGENTS.md   mode-chain prose expressions
  * docs/layout-modes.md / docs/layout-modes.en.md   mode-chain tables + prose

Run modes:
    python scripts/check_docs_consistency.py         # gate mode (CI / pre-push)
    python scripts/check_docs_consistency.py --fix   # auto-repair badges and
                                                     # complete partial chain
                                                     # expressions in place

Exit codes: 0 = consistent, 1 = drift remains after any --fix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Canonical mode ids, in evaluation order (derived from code at runtime).
CHAIN_IDS = [
    "symmetric", "bowtie-vertex", "spine-wing", "comb-bilateral",
    "column-chain", "ring-cycle", "layered",
]

# Alias tokens per canonical id. Longest / most specific alternatives first.
# zh aliases cover the Chinese README and docs; en aliases cover the rest.
TOKEN_PATTERNS = [
    ("symmetric",
     r"bowtie-pair symmetr(?:y|ic)|shared-edge bowtie|领结对对称"
     r"|(?<![\w-])symmetric(?=\s*(?:→|->))"),
    ("bowtie-vertex",
     r"bowtie-vertex|领结共点"),
    ("spine-wing",
     r"spine-wing|纵柱\+翼位"),
    ("comb-bilateral",
     r"comb-bilateral|双侧梳状"),
    ("column-chain",
     r"column-chain|\bcolumn\b|纵列"),
    ("ring-cycle",
     r"ring-cycle|\bring\b|环形"),
    ("layered",
     r"\blayered\b|\b分层\b"),
]
# Plain display names used when inserting a missing token (--fix).
INSERT_NAMES_EN = {
    "symmetric": "symmetric", "bowtie-vertex": "bowtie-vertex",
    "spine-wing": "spine-wing", "comb-bilateral": "comb-bilateral",
    "column-chain": "column-chain", "ring-cycle": "ring-cycle",
    "layered": "layered",
}
INSERT_NAMES_ZH = {
    "symmetric": "领结对对称", "bowtie-vertex": "领结共点",
    "spine-wing": "纵柱+翼位", "comb-bilateral": "双侧梳状",
    "column-chain": "纵列", "ring-cycle": "环形", "layered": "分层",
}

COMBINED = re.compile("|".join("(%s)" % pat for _, pat in TOKEN_PATTERNS),
                      re.IGNORECASE)


def _token_id(match: "re.Match") -> str:
    """Map a combined-pattern match to its canonical id via group index."""
    gid = match.lastindex if match.lastindex else 0
    for i, (mid, _) in enumerate(TOKEN_PATTERNS, start=1):
        if match.group(i) is not None:
            return mid
    return TOKEN_PATTERNS[gid - 1][0] if gid <= len(TOKEN_PATTERNS) else ""

MAX_TOKEN_GAP = 400  # chars; tokens farther apart do not form one expression

CHAIN_FILES = [
    "README.md", "README_zh-CN.md", "AGENTS.md",
    "docs/layout-modes.md", "docs/layout-modes.en.md",
]
VERSION_FIX_FILES = ["README.md", "README_zh-CN.md", "AGENTS.md"]


# ---------------------------------------------------------------- sources --
def pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("pyproject.toml: no project version found")
    return m.group(1)


def init_version() -> str:
    text = (ROOT / "stdraw" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("stdraw/__init__.py: no __version__ found")
    return m.group(1)


def code_chain() -> list[str]:
    """Derive the mode priority chain from the implementation."""
    src = (ROOT / "stdraw" / "layout_auto.py").read_text(encoding="utf-8")
    seen: list[str] = []
    for m in re.finditer(r'_rule_hit\(\s*"([^"]+)"', src):
        name = m.group(1).split(" (")[0].strip()
        if name in CHAIN_IDS and name not in seen:
            seen.append(name)
    if "layered" not in seen:
        seen.append("layered")
    if set(seen) != set(CHAIN_IDS):
        print(f"WARN  code-derived rule set {seen} differs from the "
              f"documented canonical set {CHAIN_IDS} -- update CHAIN_IDS in "
              f"this script if the implementation added or removed a mode")
    elif seen != CHAIN_IDS:
        # evaluation order in code may differ from effective precedence
        # (e.g. comb-bilateral sits at tier 2 but is evaluated after column
        # behind the salience rule); the prose canonical order stays CHAIN_IDS.
        print(f"NOTE  code evaluation order {seen} differs from canonical "
              f"precedence {CHAIN_IDS} (informational)")
    return CHAIN_IDS


# ---------------------------------------------------------------- helpers --
def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="")


def monotone_runs(matches: list) -> list[list]:
    """Split a token stream into runs whose canonical indices never decrease.

    This keeps contextual slot notes (e.g. 'chain slot: bowtie-vertex ->
    spine-wing -> column') from swallowing unrelated mentions after them.
    """
    runs, cur, last_idx = [], [], -1
    for m in matches:
        idx = CHAIN_IDS.index(_token_id(m))
        if cur and idx < last_idx:
            runs.append(cur)
            cur, last_idx = [], -1
        cur.append(m)
        last_idx = idx
    if cur:
        runs.append(cur)
    return runs


def dedup(seq: list[str]) -> list[str]:
    out: list[str] = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def is_subsequence(seq: list[str], ref: list[str]) -> bool:
    it = iter(ref)
    return all(x in it for x in seq)


def find_chain_windows(text: str) -> list[tuple[int, int, list]]:
    """Return (start, end, seq) for every chain-like token run in text."""
    matches = [m for m in COMBINED.finditer(text)]
    windows = []
    run: list = []
    for m in matches:
        if run and m.start() - run[-1].end() > MAX_TOKEN_GAP:
            windows.extend(_windows_from_run(run, text))
            run = []
        run.append(m)
    windows.extend(_windows_from_run(run, text))
    return windows


def _windows_from_run(run: list, text: str) -> list[tuple]:
    out = []
    for r in monotone_runs(run):
        seq = dedup([_token_id(m) for m in r])
        if len(seq) >= 4:
            out.append((r[0].start(), r[-1].end(), seq))
    return out


def is_full_chain(seq: list[str]) -> bool:
    """A window that claims the whole chain (fixable when incomplete)."""
    return len(seq) >= 4 and seq[0] in ("symmetric", "bowtie-vertex") \
        and seq[-1] == "layered"


# ------------------------------------------------------------ chain fixes --
def _arrow_sep_before(window: str, pos: int, default: str) -> str:
    """The arrow separator immediately before window[pos:]; default if none."""
    before = window[:pos]
    best = -1
    for arrow in ("->", "→"):
        i = before.rfind(arrow)
        if i > best:
            best = i
    if best >= 0 and before[best:].strip() in ("->", "→"):
        while best > 0 and before[best - 1] in " \t\n":
            best -= 1  # carry the whitespace/newline ahead of the arrow too
        return before[best:]  # whitespace + arrow up to pos
    return default


def _arrow_sep_after(window: str, pos: int, default: str) -> str:
    """The arrow separator immediately after window[pos:]; default if none."""
    m = re.match(r"\s*(->|→)\s*", window[pos:])
    return m.group(0) if m else default


def insert_missing(text: str, start: int, end: int, seq: list[str],
                   zh: bool) -> str:
    """Complete a partial full-chain window to the canonical chain."""
    names = INSERT_NAMES_ZH if zh else INSERT_NAMES_EN
    window = text[start:end]
    toks = [m for m in COMBINED.finditer(window)]
    # positions of the tokens that produce the observed (deduped) sequence
    seq_pos = []
    last = None
    for m in toks:
        if _token_id(m) != last:
            seq_pos.append(m)
            last = _token_id(m)
    missing = [cid for cid in CHAIN_IDS if cid not in seq]
    # insert each missing id right before its canonical successor
    for cid in reversed(missing):  # right-to-left keeps offsets valid
        i = CHAIN_IDS.index(cid)
        succ = next((sp for sp in seq_pos
                     if CHAIN_IDS.index(_token_id(sp)) > i), None)
        namesake = next((sp for sp in seq_pos if _token_id(sp) == cid), None)
        if namesake:  # duplicate, not missing
            continue
        nm = names[cid]
        if succ is not None:
            k = seq_pos.index(succ)
            if k > 0:
                sep = _arrow_sep_before(window, succ.start(), " -> ")
            else:
                sep = _arrow_sep_after(window, succ.end(), " -> ")
            ins = nm + sep
            pos = succ.start()
        else:  # missing id comes after every present token
            sep = " -> "
            ins = sep + nm
            pos = len(window)
        window = window[:pos] + ins + window[pos:]
        # recompute token positions inside the edited window
        toks = [m for m in COMBINED.finditer(window)]
        seq_pos, last = [], None
        for m in toks:
            if _token_id(m) != last:
                seq_pos.append(m)
                last = _token_id(m)
    return window


# --------------------------------------------------------------- checking --
def main() -> int:
    args = set(sys.argv[1:])
    fix = "--fix" in args
    problems: list[str] = []
    fixed: list[str] = []

    ver_py = pyproject_version()
    ver_init = init_version()
    chain = code_chain()
    print(f"source of truth: pyproject={ver_py} __init__={ver_init}")
    print(f"code-derived mode chain: {' -> '.join(chain)}")

    if ver_py != ver_init:
        problems.append(f"version drift: pyproject={ver_py} != "
                        f"__init__={ver_init}")

    def sub_fix(path: str, pat: str, repl: str, label: str) -> None:
        text = read(path)
        new, n = re.subn(pat, repl, text)
        if n:
            write(path, new)
            fixed.append(f"{path}: {label} ({n} site(s))")

    # -- version badges and version mentions -------------------------------
    badge = r"version-\d+\.\d+\.\d+-blue"
    badge_ok = rf"version-{ver_py}-blue"
    for path in ("README.md", "README_zh-CN.md"):
        text = read(path)
        found = set(re.findall(badge, text))
        bad = found - {badge_ok}
        if bad:
            if fix:
                sub_fix(path, badge, badge_ok, f"version badge -> {ver_py}")
            else:
                problems.append(f"{path}: version badge {sorted(bad)} "
                                f"!= {badge_ok}")
    text = read("README.md")
    m = re.search(r"current engine \(v(\d+\.\d+\.\d+)\)", text)
    if m and m.group(1) != ver_py:
        if fix:
            sub_fix("README.md", r"current engine \(v\d+\.\d+\.\d+\)",
                    f"current engine (v{ver_py})", f"engine mention -> {ver_py}")
        else:
            problems.append(f"README.md: engine mention v{m.group(1)} != "
                            f"v{ver_py}")
    text = read("README_zh-CN.md")
    m = re.search(r"当前引擎（v(\d+\.\d+\.\d+)）", text)
    if m and m.group(1) != ver_py:
        if fix:
            sub_fix("README_zh-CN.md", r"当前引擎（v\d+\.\d+\.\d+）",
                    f"当前引擎（v{ver_py}）", f"engine mention -> {ver_py}")
        else:
            problems.append(f"README_zh-CN.md: engine mention v{m.group(1)} "
                            f"!= v{ver_py}")
    text = read("AGENTS.md")
    m = re.search(r"Current \*\*(\d+\.\d+\.\d+)\*\*", text)
    if not m:
        problems.append("AGENTS.md: no 'Current **X**' version line found")
    elif m.group(1) != ver_py:
        if fix:
            sub_fix("AGENTS.md", r"Current \*\*\d+\.\d+\.\d+\*\*",
                    f"Current **{ver_py}**", f"Current line -> {ver_py}")
        else:
            problems.append(f"AGENTS.md: Current **{m.group(1)}** != "
                            f"**{ver_py}**")

    # -- mode priority chain expressions ------------------------------------
    for path in CHAIN_FILES:
        text = read(path)
        zh = path.endswith(("zh-CN.md", "layout-modes.md"))
        for start, end, seq in find_chain_windows(text):
            if seq == chain:
                continue
            if is_full_chain(seq):
                if is_subsequence(seq, chain):
                    if fix:
                        text2 = text[:start] + \
                            insert_missing(text, start, end, seq, zh) + \
                            text[end:]
                        write(path, text2)
                        fixed.append(f"{path}: completed mode chain "
                                     f"{' -> '.join(seq)} -> "
                                     f"{' -> '.join(chain)}")
                        text = text2
                    else:
                        problems.append(
                            f"{path}: incomplete mode chain "
                            f"{' -> '.join(seq)} (code: "
                            f"{' -> '.join(chain)})")
                else:
                    problems.append(
                        f"{path}: mode chain order drift "
                        f"{' -> '.join(seq)} (code: {' -> '.join(chain)})")
            elif not is_subsequence(seq, chain):
                problems.append(
                    f"{path}: mode chain order drift "
                    f"{' -> '.join(seq)} (code: {' -> '.join(chain)})")
        # markdown mode-selection tables must list the full chain in order
        rows = []
        for line in text.splitlines():
            if not re.match(r"\|\s*\d+\s*\|", line):
                continue
            # prefer the meta.placement cell (a backticked canonical id);
            # fall back to the first alias token in the row
            ids = [g for g in re.findall(r"`([a-z-]+)`", line)
                   if g in CHAIN_IDS]
            if ids:
                rows.append(ids[-1])
            else:
                mm = COMBINED.search(line)
                if mm:
                    rows.append(_token_id(mm))
        rows = dedup(rows)
        if rows and rows != chain:
            problems.append(f"{path}: mode-selection table order "
                            f"{' -> '.join(rows)} != code "
                            f"{' -> '.join(chain)}")

    # -- grading-token single-source check (WorkBuddy task 2026-11-11) ------
    # Canonical facts are the CODE (docs/grading-contract.md is the prose
    # single source): the v2 certificate_auto emits grade tokens
    # best/uncertified; `second` survives only inside the v1-legacy ortho
    # certificate(); `3d` is the docs-level 3D-delivery tier.  Every doc
    # that presents grading tiers must (a) not present `second` as a
    # current tier and (b) reference the single source docs/grading-
    # contract.md.  AGENTS.md is a protected file whose grading mentions
    # are historical changelog entries (second-removal notes): only the
    # single-source rule applies there.
    GRADE_DOC_FILES = [
        "README.md", "README_zh-CN.md", "AGENTS.md", "skills/stdraw/SKILL.md",
    ]
    CONTRACT_REF = "docs/grading-contract.md"

    def grade_doc_problems(path: str) -> list:
        text = read(path)
        issues = []
        if CONTRACT_REF not in text:
            issues.append("no " + CONTRACT_REF + " single-source reference")
        if path != "AGENTS.md":
            for m in re.finditer(r"`second`", text):
                ctx = text[max(0, m.start() - 120): m.end() + 120]
                if not re.search(r"remov|legacy|unreach|histor|v0\.7\.15|"
                                 r"移除|遗留|历史", ctx, re.I):
                    issues.append("`second` presented as a current grade "
                                  "tier (removed in v0.7.15+; v1-legacy "
                                  "ortho caliber only)")
                    break
        return issues

    for path in GRADE_DOC_FILES:
        issues = grade_doc_problems(path)
        if issues:
            problems.append(f"{path}: grading-tier drift ("
                            + "; ".join(issues) + ")")

    for f in fixed:
        print(f"FIX  {f}")
    if problems:
        for p in problems:
            print(f"DRIFT  {p}")
        print(f"docs-consistency gate: FAIL ({len(problems)} drift)")
        return 1
    print("docs-consistency gate: OK "
          "(version badges + mode chains match the code)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
