"""Defines functions for powershell encoding"""

# Standard libraries
from base64 import b64decode, b64encode

# Project libraries
from tunnelrat.constants import ExecutableTypes


def to_powershell_encoded(script: str) -> str:
    """Converts a UTF-8 string to UTF-16LE for powershell -EncodedCommand"""
    return b64encode(script.encode(encoding="utf-16le")).decode("utf-8")


def from_powershell_encoded(script: str) -> str:
    """Converts a UTF-16LE base64 string to a UTF-8 string"""
    return b64decode(script).decode("utf-16le")


def create_powershell_command(script: str, executable: str = "powershell") -> str:
    """Assembles a powershell command using the raw script and an optional powershell path"""
    return f"{executable} -EncodedCommand {to_powershell_encoded(script)}"


def create_python_command(script: str, executable: str = "python") -> str:
    """Assembles a python command using the raw script"""
    return f"{executable} -c \"import base64; exec(base64.b64decode('{b64encode(script)}'))\""


def generate_windows_command(script: str, executable: ExecutableTypes | None = None) -> str:
    if executable == ExecutableTypes.POWERSHELL or executable is None:
        return create_powershell_command(script=script)
    if executable == ExecutableTypes.CMD:
        return script
    if executable == ExecutableTypes.PYTHON:
        return create_python_command(script=script)
    raise KeyError(f"Invalid windows executable type {executable}")
