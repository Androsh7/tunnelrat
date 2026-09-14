"""Defines functions for bash encoding"""

# Standard libraries
from base64 import b64encode

# Project libraries
from tunnelrat.commands.windows import create_powershell_command, create_python_command
from tunnelrat.constants import ExecutableTypes


def create_bash_command(script: str, executable: str = "bash") -> str:
    return f"{executable} -c \"$(echo '{b64encode(script.encode('utf-8')).decode('utf-8')}' | base64 -d )\""


def generate_linux_command(script: str, executable: ExecutableTypes | None = None) -> str:
    if executable == ExecutableTypes.BASH or executable is None:
        return create_bash_command(script=script, executable="bash")
    if executable == ExecutableTypes.SH:
        return create_bash_command(script=script, executable="sh")
    if executable == ExecutableTypes.PWSH:
        return create_powershell_command(script=script, executable="pwsh")
    if executable == ExecutableTypes.PYTHON:
        return create_python_command(script=script)
    raise KeyError(f"Invalid linux executable type {executable}")
