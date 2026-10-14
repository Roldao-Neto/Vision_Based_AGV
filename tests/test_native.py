"""Builds and runs the native C++ tests of the sketch's pure-math modules with the PC's g++."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sketch" / "src"
NATIVE = Path(__file__).resolve().parent / "native"

# test file -> sketch module sources it needs
SUITES = {
    "test_encoder_guard.cpp": ["encoder_guard/encoder_guard.cpp"],
    "test_wheel_pi.cpp": ["wheel_pi/wheel_pi.cpp"],
}


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
@pytest.mark.parametrize("test", sorted(SUITES))
def test_native(test: str, tmp_path: Path):
    exe = tmp_path / Path(test).stem
    sources = [str(NATIVE / test), *(str(SRC / s) for s in SUITES[test])]
    build = subprocess.run(
        ["g++", "-std=gnu++17", "-Wall", "-Wextra", "-Werror", "-I", str(SRC), *sources, "-o", str(exe)],
        check=False, capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe)], check=False, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
