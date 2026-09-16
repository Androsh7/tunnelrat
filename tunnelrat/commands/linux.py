"""Defines functions for bash encoding"""

# Standard libraries
from base64 import b64encode

# Project libraries
from tunnelrat.commands.windows import create_powershell_command, create_python_command
from tunnelrat.constants import ExecutableTypes


def create_bash_command(script: str, executable: str = "bash") -> str:
    """Return a base64 wrapped shell command that runs the script through the given shell

    Args:
        script: The command line or script body to run
        executable: The shell to run the decoded script with

    Returns:
        A one line command that decodes and runs the script
    """
    return f"{executable} -c \"$(echo '{b64encode(script.encode('utf-8')).decode('utf-8')}' | base64 -d )\""


def generate_linux_command(script: str, executable: ExecutableTypes | None = None) -> str:
    """Return the command that runs a script on a linux host with the chosen interpreter

    Args:
        script: The command line or script body to run
        executable: The interpreter to run the script with, defaults to bash when left out

    Raises:
        KeyError: If the executable is not one supported on linux

    Returns:
        A one line command ready to run over ssh
    """
    if executable == ExecutableTypes.BASH or executable is None:
        return create_bash_command(script=script, executable="bash")
    if executable == ExecutableTypes.SH:
        return create_bash_command(script=script, executable="sh")
    if executable == ExecutableTypes.PWSH:
        return create_powershell_command(script=script, executable="pwsh")
    if executable == ExecutableTypes.PYTHON:
        return create_python_command(script=script)
    raise KeyError(f"Invalid linux executable type {executable}")
