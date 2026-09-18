"""Defines the CommandConfig class"""

# Standard libraries
from pathlib import Path

# Third-party libraries
from pydantic import BaseModel, Field, model_validator

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


class CommandConfig(CommandBaseConfig):
    """Describe a command step that runs one script on one host"""

    connection_name: str = Field(alias="via", description="Name of the host from the hosts block to run the script on")
    stdout_file: Path | None = Field(default=None, description="Local file to write the standard output to")
    stderr_file: Path | None = Field(default=None, description="Local file to write the standard error to")

    def __str__(self) -> str:
        """Return the command described as a header line and the script body"""
        sudo_note = " (sudo enabled)" if self.sudo else ""
        return f"Running command on {self.connection_name} using {self.executable}{sudo_note}\n{self.script}"


class BatchCommandConfig(CommandBaseConfig):
    """Describe a batch step that runs one script on several hosts"""

    connection_name_list: list[str] = Field(
        alias="via", description="Names of the hosts from the hosts block to run the script on", min_length=2
    )
    output_dir: Path | None = Field(
        default=None,
        description="Local directory to write one output file per host into",
    )
    stdout_output: bool = Field(default=False, description="Write the standard output of each host into output_dir")
    stderr_output: bool = Field(default=False, description="Write the standard error of each host into output_dir")

    @model_validator(mode="after")
    def require_output_dir_when_capturing(self):
        """Return the model after checking that output_dir is set when output is captured

        Raises:
            ValueError: If stdout_output or stderr_output is set without an output_dir
        """
        if (self.stdout_output or self.stderr_output) and self.output_dir is None:
            raise ValueError("output_dir is required when stdout_output or stderr_output is set")
        return self

    def __str__(self) -> str:
        """Return the batch command described as a header line and the script body

        Returns:
            The hosts and sudo flag on one line, then the script
        """
        sudo_note = " (sudo enabled)" if self.sudo else ""
        connection_names = ", ".join(self.connection_name_list)
        return f"Running command on ({connection_names}){sudo_note}:\n{self.script}"

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
