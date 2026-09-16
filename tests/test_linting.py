"""Unit tests for linting"""

# Standard libraries
import json
import subprocess


def test_ruff_formatting() -> None:
    """Every file is formatted the way ruff would format it"""
    subprocess.run("ruff format . --check", shell=True, capture_output=True, check=True)


def test_ruff_check() -> None:
    """No ruff error is left that ruff could safely fix on its own"""
    result = subprocess.run(
        "ruff check . --show-fixes --output-format=json", shell=True, capture_output=True, check=False
    )
    for fix in json.loads(result.stdout):
        if fix["fix"] is not None and fix["fix"]["applicability"] != "unsafe":
            raise Exception("Fixable ruff error")
