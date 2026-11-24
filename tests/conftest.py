"""Session-wide isolation guard: stdraw module identity in ``sys.modules``.

Why this guard exists
---------------------
pytest imports every test module (collection) BEFORE the first test runs, so
a module-level ``from stdraw.routing import Router`` in a test file binds the
class object that existed at collection time.  The engine, however, resolves
``stdraw.<module>`` through ``sys.modules`` at CALL time.  A test that deletes
``stdraw*`` entries from ``sys.modules`` (package re-import / same-tree
self-check) and does not put the ORIGINAL module objects back splits the
suite in two: every other test file's import-time references are now stale,
monkeypatches on them never reach the chain, and those tests go red purely by
file order (green when run alone, red when sorted after the offender).

What it does
------------
Autouse, function-scoped: snapshot the ``stdraw*`` entries of ``sys.modules``
before each test and compare object identity after the test's teardown.  Any
pre-existing entry that is missing or replaced afterwards fails the test that
caused it (reported at ITS teardown, not as phantom failures elsewhere).
New entries are allowed (a call-time import of a not-yet-imported submodule
is legitimate and cannot stale anyone's references).

The fix for an offender is to restore the pre-test state in its own teardown
(see the ``pinned_local_stdraw`` fixture in test_v079_font_env.py; the
save/restore shape follows the ortools block in test_crossing_exact.py).
Fixture order makes this work: autouse fixtures are set up first and torn
down LAST, so an offender's own restore has already run when the guard
compares.
"""
import sys

import pytest


def _stdraw_modules():
    return {name: mod for name, mod in sys.modules.items()
            if name == "stdraw" or name.startswith("stdraw.")}


@pytest.fixture(autouse=True)
def _guard_stdraw_module_identity():
    before = _stdraw_modules()
    yield
    after = _stdraw_modules()
    stale = sorted(name for name, mod in before.items()
                   if after.get(name) is not mod)
    if stale:
        detail = "; ".join(
            "%s 0x%x -> %s" % (name, id(before[name]),
                               "missing" if name not in after
                               else "0x%x" % id(after[name]))
            for name in stale)
        pytest.fail(
            "test left stdraw modules replaced in sys.modules (%s): the "
            "import-time class references held by every other test file are "
            "stale now, so their monkeypatches cannot reach the chain and "
            "they fail by file order -- restore sys.modules (and any "
            "sys.meta_path / sys.path edits) in this test's teardown"
            % detail,
            pytrace=False)
