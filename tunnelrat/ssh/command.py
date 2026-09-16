"""Defines the CommandConfig class"""

# Standard libraries
from pathlib import Path

# Third-party libraries
from pydantic import BaseModel, Field

# Project libraries
from tunnelrat.constants import ExecutableTypes


class CommandBaseConfig(BaseModel):
    """Hold the settings shared by every kind of command step"""

    executable: ExecutableTypes | None = Field(
        default=None,
        description="Interpreter to run the script with, defaults to the login shell of the host",
    )
    script: str = Field(description="Command line or script body to run on the host")
    sudo: bool = Field(default=False, description="Run the script through sudo using the host sudo_password")
    stdout_print: bool = Field(default=False, description="Echo the standard output of the script to the console")
    stderr_print: bool = Field(default=False, description="Echo the standard error of the script to the console")


class CommandConfig(CommandBaseConfig):
    """Describe a command step that runs one script on one host"""

    connection_name: str = Field(alias="via", description="Name of the host from the hosts block to run the script on")
    stdout_file: Path | None = Field(default=None, description="Local file to write the standard output to")
    stderr_file: Path | None = Field(default=None, description="Local file to write the standard error to")


class BatchCommandConfig(CommandBaseConfig):
    """Describe a batch step that runs one script on several hosts"""

    connection_name_list: list[str] = Field(
        alias="via",
        description="Names of the hosts from the hosts block to run the script on", min_length=2
    )
    output_dir: Path | None = Field(
        default=None,
        description="Local directory to write one output file per host into",
    )
    stdout_output: bool = Field(default=False, description="Write the standard output of each host into output_dir")
    stderr_output: bool = Field(default=False, description="Write the standard error of each host into output_dir")

    def to_command_config(self, connection_name: str) -> CommandConfig:
        """Returns a CommandConfig model for the given connection_name"""
        assert connection_name in self.connection_name_list
        config_dict = self.model_dump()
        config_dict.update({"via": connection_name})
        config_dict.update(
            {"stderr_file": self.output_dir / f"{connection_name}_stderr.txt" if self.stderr_output else None}
        )
        config_dict.update(
            {"stdout_file": self.output_dir / f"{connection_name}_stdout.txt" if self.stdout_output else None}
        )
        return CommandConfig(**config_dict)
