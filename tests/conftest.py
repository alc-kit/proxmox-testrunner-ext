"""testrunner is not on PyPI: the tests import it from a checkout, TESTRUNNER_SRC (its src/), and
refuse to run without one (a suite that skips silently proves nothing)."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = os.environ.get("TESTRUNNER_SRC")
if not src or not (Path(src) / "testrunner" / "__init__.py").is_file():
    raise SystemExit(f"TESTRUNNER_SRC must point at a testrunner checkout's src/ (got {src!r})")
sys.path[:0] = [str(Path(src).resolve()), str(HERE.parent / "src")]
