# -*- coding: utf-8 -*-
"""Language policy gate: repo-wide bilingual partition, no mixed language.

Faces (see the repo language manifest):
  EN face (publishing face + code + engine-generated chrome/data strings):
    zero CJK characters, except explicit content exemptions (model labels).
  zh face (engineering caliber originals + Chinese counterparts):
    no English prose paragraphs (technical terms / code / numbers / filenames
    exempt).

Runs standalone (`python tests/check_language_policy.py`) and is wired into
tests/ci_checks.py.
"""
import io
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff5e]")

EN_TEXT_FILES = [
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "skills/stdraw/SKILL.md",
    "docs/dsl-spec-v0.1.md",
    "viewer/README.md",
    "viewer/index.html",
    "demos/classic-cld-2d.html",
    "demos/classic-cld-3d.html",
    "demos/classic-certificate.json",
    "demos/classic-loops-audit.json",
]

ZH_TEXT_FILES = [
    "README_zh-CN.md",
    "docs/layout-modes.md",
    "docs/crossing-exact.md",
    "docs/ortools-comparison.md",
    "docs/dsl-spec-v0.1.zh-CN.md",
    "benchmarks/README.md",
    "benchmarks/REPORT.md",
    "benchmarks/manual/README.md",
]

# Model-content exemptions: node / loop labels from the classic corpus demo.
DEMO_LABEL_WHITELIST = [
    "采纳率", "采纳者", "口碑效应", "潜在采纳者", "拥挤效应",
    "症状解·限流扩容", "根本解·产品打磨", "副作用·资源被占用",
    "采纳扩散", "承载上限", "增长引擎",
    "市场饱和", "拥挤制约", "症状缓解", "根本治理", "饮鸩止渴",
]

# Language-switch link labels (README.md -> README_zh-CN.md, ref-scrubbed):
# the Chinese entry link is labelled in Chinese by design (users who cannot
# read English must be able to recognize it); the zh face keeps "English".
LANGUAGE_SWITCH_LABELS = [
    "中文",
]

# zh-face: English allowed verbatim lines (nav notes).
ZH_LINE_WHITELIST = [
    "> Engineering doc, maintained in Chinese — English overview: README.md",
]

# zh-face: English technical terms that never count as prose.
ZH_TERM_ALLOW = re.compile(
    r"^(?:[A-Za-z][\w./+#-]*[.:,;)?\]]*|[-—·×*/=<>()\[\]{}|,:.;%#?\"'`]+|"
    r"\d+(?:\.\d+)*|--+|\|+)$")


def strip_code_spans(line):
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\$[^$]*\$", " ", line)
    # verbatim English quotations of literature stay allowed on the zh face
    line = re.sub(r'"[^"]*"', " ", line)
    return line


def find_cjk(text):
    out = []
    for i, ch in enumerate(text):
        if CJK.match(ch):
            out.append(ch)
    return out


def check_en_text_file(rel):
    """EN face text file: zero CJK outside whitelisted labels / regions."""
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    problems = []
    # region exemptions: viewer model-data const blocks; md code fences
    if rel == "viewer/index.html":
        text = re.sub(r"const GRAPH = \{.*?\};", " ", text, flags=re.S)
        text = re.sub(r"const LAYOUTS = \{.*?\};", " ", text, flags=re.S)
    if rel.endswith(".md"):
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
    # whitelist known model labels (longest first so no label eats another)
    for w in sorted(DEMO_LABEL_WHITELIST + LANGUAGE_SWITCH_LABELS,
                    key=len, reverse=True):
        text = text.replace(w, " ")
    for m in CJK.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        problems.append(f"{rel}: CJK char {m.group(0)!r} at line {line}")
    return problems


def check_en_json_file(path, rel):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    problems = []
    for w in DEMO_LABEL_WHITELIST:
        text = text.replace(w, " ")
    for m in CJK.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        problems.append(f"{rel}: CJK char {m.group(0)!r} at line {line}")
    return problems


def check_en_py_file(path, rel):
    """EN face python file: zero CJK outside DSL-fixture string blocks.

    CJK is allowed only inside triple-quoted string literals (DSL fixtures /
    spec text) — single-quoted strings, comments and identifiers must be pure
    English. benchmarks/tools/gen_random.py additionally whitelists its .cld
    header f-string.
    """
    with open(path, encoding="utf-8") as f:
        src = f.read()
    problems = []
    allowed = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff5e]")
    # extract triple-quoted blocks and drop them from consideration
    dropped = re.sub(r"'''(?:(?!''').)*'''", lambda m: " " * len(m.group(0)),
                     src, flags=re.S)
    dropped = re.sub(r'"""(?:(?!""").)*"""', lambda m: " " * len(m.group(0)),
                     dropped, flags=re.S)
    # tokenize remainder: STRING tokens are exempt only for the fixture /
    # zh-report carriers below (tests embed DSL fixtures with Chinese model
    # labels; collect.py generates the Chinese-face REPORT.md); all other
    # tokens — comments, identifiers, messages — must be CJK-free.
    fixture_only = rel.startswith("tests/") or rel in (
        "benchmarks/tools/collect.py",
        "benchmarks/tools/gen_random.py",
    )
    toks = list(tokenize.generate_tokens(io.StringIO(dropped).readline))
    FSTRING_TYPES = {tokenize.STRING}
    if hasattr(tokenize, "FSTRING_MIDDLE"):
        FSTRING_TYPES.add(tokenize.FSTRING_MIDDLE)
    for t in toks:
        if t.type in FSTRING_TYPES and fixture_only:
            continue
        for m in allowed.finditer(t.string):
            problems.append(
                f"{rel}: CJK in {tokenize.tok_name[t.type]} line {t.start[0]}: "
                f"{t.string.strip()[:60]!r}")
            break
    return problems


def check_zh_file(rel):
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    problems = []
    for i, ln in enumerate(lines, 1):
        if ln.strip() in ZH_LINE_WHITELIST:
            continue
        s = strip_code_spans(ln)
        # remove urls / paths
        s = re.sub(r"https?://\S+", " ", s)
        s = re.sub(r"\b[\w-]+(?:\.[\w-]+)+\b", " ", s)
        words = s.split()
        # find runs of >= 5 pure-ASCII alphabetic tokens
        run = []
        for w in words:
            if re.fullmatch(r"[A-Za-z][A-Za-z'-]*", w.strip(",.;:()\"'")):
                run.append(w)
            else:
                if len(run) >= 5:
                    ctx = " ".join(run)
                    if not any(t in ctx for t in ("Engineering doc",)):
                        problems.append(
                            f"{rel}: English prose run at line {i}: {ctx[:70]!r}")
                run = []
        if len(run) >= 5:
            ctx = " ".join(run)
            problems.append(f"{rel}: English prose run at line {i}: {ctx[:70]!r}")
    return problems


def run_checks():
    problems = []
    for rel in EN_TEXT_FILES:
        problems += check_en_text_file(rel)
    for rel in ("stdraw", "tests", "benchmarks/tools"):
        d = os.path.join(ROOT, rel)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py"):
                continue
            if rel == "tests" and fn == "check_language_policy.py":
                continue  # this gate's own whitelist strings
            problems += check_en_py_file(os.path.join(d, fn), f"{rel}/{fn}")
    rawdir = os.path.join(ROOT, "benchmarks", "raw")
    for fn in sorted(os.listdir(rawdir)):
        if fn.endswith(".json"):
            problems += check_en_json_file(
                os.path.join(rawdir, fn), f"benchmarks/raw/{fn}")
    for rel in ZH_TEXT_FILES:
        problems += check_zh_file(rel)
    return problems


def main():
    problems = run_checks()
    if problems:
        print("LANGUAGE POLICY FAILURES:")
        for p in problems:
            print(" -", p)
        return 1
    print("OK  language policy: EN face CJK-free (exemptions applied), "
          "zh face prose-free, code files English-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
