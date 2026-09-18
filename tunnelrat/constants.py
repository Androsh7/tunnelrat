"""Defines constants"""

# Standard libraries
import importlib.metadata
from enum import StrEnum

VERSION = importlib.metadata.version("tunnelrat")

# SSH
DEFAULT_SSH_CONNECTION_TIMEOUT_S = 30
DEFAULT_SSH_COMMAND_TIMEOUT_S = 300

# Documentation
LOADER_INJECTED_KEY = "loader_injected"
MAX_DESCRIPTION_COLUMN_WIDTH = 60


class OSTypes(StrEnum):
    """Enumerate the operating systems a host can run"""

    WINDOWS = "windows"
    LINUX = "linux"


class ExecutableTypes(StrEnum):
    """Enumerate the interpreters a command step can be run with"""

    POWERSHELL = "powershell"
    CMD = "cmd"
    PYTHON = "python"
    PWSH = "pwsh"
    BASH = "bash"
    SH = "sh"


class ForwardTypes(StrEnum):
    """Enumerate the directions a tunnel can forward traffic"""

    LOCAL = "local"
    REMOTE = "remote"


# Script
class StepTypes(StrEnum):
    """Enumerate the kinds of step a script can hold"""

    CREATE_CONNECTION = "connect"
    CREATE_FORWARD = "forward"
    COMMAND = "command"
    BATCH_COMMAND = "batch"
    WAIT = "wait"
    BLOCK = "block"
    COMMENT = "comment"


ALL_ENUMS = [StepTypes, ForwardTypes, ExecutableTypes, OSTypes]
