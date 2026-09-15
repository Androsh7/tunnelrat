"""Defines constants"""

# Standard libraries
from enum import StrEnum
from pathlib import Path

PARENT_DIRECTORY = Path(__file__).parent.parent

VERSION = (PARENT_DIRECTORY / "VERSION.txt").read_text().strip()

# SSH
DEFAULT_SSH_CONNECTION_TIMEOUT_S = 30
DEFAULT_SSH_COMMAND_TIMEOUT_S = 300


class OSTypes(StrEnum):
    WINDOWS = "windows"
    LINUX = "linux"


class ExecutableTypes(StrEnum):
    POWERSHELL = "powershell"
    CMD = "cmd"
    PYTHON = "python"
    PWSH = "pwsh"
    BASH = "bash"
    SH = "sh"


class ForwardTypes(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


# Script
class StepTypes(StrEnum):
    COMMAND = "command"
    BATCH_COMMAND = "batch"
    FORWARD = "forward"
    WAIT = "wait"
    BLOCK = "block"
    COMMENT = "comment"


ALL_ENUMS = [StepTypes, ForwardTypes, ExecutableTypes, OSTypes]
