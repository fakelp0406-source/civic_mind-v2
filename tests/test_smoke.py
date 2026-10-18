"""Smoke test: the skeleton imports cleanly and keeps its architectural boundaries."""

import importlib
import subprocess
import sys
import types
from pathlib import Path

import civicmind

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

#: Third-party stacks that must never be loaded merely by importing ``civicmind``.
HEAVY_MODULES = (
    "pandas", "numpy", "fastapi", "pydantic", "yaml", "torch", "transformers", "pypdf",
    "onnxruntime", "tokenizers", "sqlite3",
)  # fmt: skip


def heavy_modules_loaded_in_fresh_interpreter(heavy=HEAVY_MODULES, extra_code=""):
    """Import every layer in a NEW interpreter and return which ``heavy`` modules got loaded.

    A fresh subprocess is used so that modules already imported by the test runner or its
    plugins cannot hide (or fake) a heavy import made by ``civicmind``.
    """
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(SRC_DIR)!r})\n"
        "import importlib, civicmind\n"
        "for layer in civicmind.LAYERS:\n"
        "    importlib.import_module('civicmind.' + layer)\n"
        f"{extra_code}\n"
        f"print(','.join(m for m in {tuple(heavy)!r} if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return {name for name in result.stdout.strip().split(",") if name}


def test_version_is_declared():
    assert civicmind.__version__ == "0.0.1"


def test_every_layer_is_importable_and_documented():
    for layer in civicmind.LAYERS:
        module = importlib.import_module(f"civicmind.{layer}")
        assert module.__doc__ and module.__doc__.strip(), f"{layer} lacks a docstring"


def test_importing_the_package_stays_lightweight():
    assert heavy_modules_loaded_in_fresh_interpreter() == set()


def test_check_is_isolated_from_modules_preloaded_in_the_test_process(monkeypatch):
    # Regression: the earlier in-process check skipped any module the test runner had already
    # imported. Simulate a preloaded heavy module in THIS process; the subprocess check must
    # still evaluate a clean interpreter and report nothing.
    for name in HEAVY_MODULES:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    assert heavy_modules_loaded_in_fresh_interpreter() == set()


def test_check_detects_a_heavy_import_when_one_happens():
    # Negative control: the check must not be vacuous. Treat a standard-library module as
    # "heavy" and import it inside the subprocess; it has to be reported.
    loaded = heavy_modules_loaded_in_fresh_interpreter(
        heavy=("xml.dom.minidom",), extra_code="import xml.dom.minidom"
    )
    assert loaded == {"xml.dom.minidom"}
