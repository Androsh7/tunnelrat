"""Defines the CommandConfig class"""

# Standard libraries
from pathlib import Path

# Third-party libraries
from pydantic import BaseModel, Field

# Project libraries
from tunnelrat.constants import ExecutableTypes


class CommandBaseConfig(BaseModel):
    executable: ExecutableTypes | None = Field(default=None)
    script: str
    sudo: bool = Field(default=False)
    stdout_print: bool = Field(default=False)
    stderr_print: bool = Field(default=False)


class CommandConfig(CommandBaseConfig):
    connection_name: str = Field(alias="via")
    stdout_file: Path | None = Field(default=None)
    stderr_file: Path | None = Field(default=None)


class BatchCommandConfig(CommandBaseConfig):
    connection_name_list: list[str] = Field(alias="via")
    output_dir: Path | None = Field(default=None)
    stdout_output: bool = Field(default=False)
    stderr_output: bool = Field(default=False)
