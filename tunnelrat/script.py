"""Defines the script class"""

# Standard libraries
import asyncio
from pathlib import Path
from time import time

# Third-party libraries
import yaml
from attrs import define, field, validators
from pydantic import BaseModel, Field

# Project libraries
from tunnelrat.constants import StepTypes
from tunnelrat.exceptions import TunnelratBackendAbort
from tunnelrat.ssh.command import BatchCommandConfig, CommandConfig
from tunnelrat.ssh.connection import SshConnectionConfig
from tunnelrat.ssh.connection_manager import connection_manager
from tunnelrat.ssh.forward import ForwardConfig


class WaitConfig(BaseModel):
    """Describe a wait step that pauses the script for a fixed time"""

    time_s: int = Field(alias="time", description="Seconds to pause before moving on to the next step")

    def __str__(self):
        return f"Waiting for {self.time_s} seconds"


class BlockConfig(BaseModel):
    """Describe a block step that holds the script open so tunnels stay up"""

    timeout_s: int | None = Field(
        alias="timeout",
        default=None,
        description="Seconds to block for, blocks until interrupted with CTRL + C when left out",
    )
    raise_on_timeout: bool = Field(
        default=True,
        description="Whether reaching the timeout raises an exception rather than continuing silently",
    )

    def __str__(self):
        return f"Blocking until interrupted (timeout {self.timeout_s} seconds)"


class CommentConfig(BaseModel):
    """Describe a comment step that prints a message to the console"""

    body: str = Field(description="Text to print when the step is reached")

    def __str__(self):
        return self.body


STEP_MODELS = (
    SshConnectionConfig | CommandConfig | ForwardConfig | WaitConfig | BlockConfig | CommentConfig | BatchCommandConfig
)
STEP_TO_MODEL: dict[StepTypes, STEP_MODELS] = {
    StepTypes.CREATE_CONNECTION: SshConnectionConfig,
    StepTypes.COMMAND: CommandConfig,
    StepTypes.BATCH_COMMAND: BatchCommandConfig,
    StepTypes.CREATE_FORWARD: ForwardConfig,
    StepTypes.WAIT: WaitConfig,
    StepTypes.BLOCK: BlockConfig,
    StepTypes.COMMENT: CommentConfig,
}


class Step(BaseModel):
    """Wrap one step of a script with its position and the model describing it"""

    step_number: int = Field(ge=1)
    step_type: StepTypes
    config: STEP_MODELS
    progress: str = Field(default="")
    completed: bool = Field(default=False)
    failed: bool = Field(default=False)
    started: bool = Field(default=False)

    @classmethod
    def from_dict(cls, step_dict: dict, step_number: int):
        """Return the step described by one entry of the steps list

        Args:
            step_dict: A single-key mapping of step type to the settings of that step
            step_number: The position of the step in the steps list, counted from one

        Raises:
            ValueError: If the key of the mapping is not a known step type
        """
        step_type = StepTypes(list(step_dict.keys())[0])
        config_model = STEP_TO_MODEL[step_type]

        return cls(
            step_type=step_type,
            step_number=step_number,
            config=config_model.model_validate(step_dict[step_type]),
        )


@define
class Script:
    """Hold the hosts and the ordered steps parsed out of one script file"""

    script_path: Path = field(converter=Path)
    step_list: list[Step] = field(
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(Step),
            iterable_validator=validators.instance_of(list),
        )
    )

    @classmethod
    def from_yaml_path(cls, yaml_path: Path):
        """Return the script described by one yaml file

        Args:
            yaml_path: The path of the yaml file holding the hosts and steps blocks

        Raises:
            KeyError: If the file has no hosts block or no steps block
        """
        with open(file=yaml_path, mode="rb") as yaml_file:
            raw_text = yaml_file.read()
            script_dict = yaml.safe_load(raw_text)

        step_list = []
        for step_number, step_dict in enumerate(script_dict["steps"], start=1):
            step_list.append(Step.from_dict(step_dict=step_dict, step_number=step_number))

        return cls(
            script_path=yaml_path,
            step_list=step_list,
        )

    async def run_script(self):
        """Open every host connection, run every step in order and then clean up

        Raises:
            KeyError: If a step has a type that has no execution path
        """
        for step in self.step_list:
            try:
                step.started = True

                # Create an SSH connection
                if step.step_type == StepTypes.CREATE_CONNECTION:
                    await connection_manager.create_connection(step.config)

                # Run a command
                elif step.step_type == StepTypes.COMMAND:
                    await connection_manager.run_command(step.config)

                # Run a batch command
                elif step.step_type == StepTypes.BATCH_COMMAND:
                    for connection_name in step.config.connection_name_list:
                        await connection_manager.run_command(step.config.to_command_config(connection_name))

                # Create a forward
                elif step.step_type == StepTypes.CREATE_FORWARD:
                    await connection_manager.create_forward(step.config)

                # Wait for some time
                elif step.step_type == StepTypes.WAIT:
                    elapsed_time = 0
                    start_time = time()
                    while elapsed_time < step.config.time_s:
                        elapsed_time = time() - start_time
                        step.progress = f"{int(step.config.time_s - elapsed_time)} seconds remaining"
                        await asyncio.sleep(0.25)

                # Block with an optional timeout
                elif step.step_type == StepTypes.BLOCK:
                    start_time = time()
                    elapsed_time = 0
                    try:
                        while step.config.timeout_s is None or elapsed_time < step.config.timeout_s:
                            elapsed_time = time() - start_time
                            step.progress = f"{int(elapsed_time)} seconds elapsed"
                            await asyncio.sleep(0.25)
                        if step.config.raise_on_timeout:
                            raise asyncio.TimeoutError(f"Blocking timed out after {int(elapsed_time)} seconds")
                    except asyncio.CancelledError:
                        asyncio.current_task().uncancel()

                # Write a Comment
                elif step.step_type == StepTypes.COMMENT:
                    pass

                else:
                    raise KeyError(f"Invalid step type {step.step_type}")

                # Mark task as complete
                step.completed = True
                step.progress = ""
            except Exception as exc:
                step.failed = True
                step.progress = f"Exception: {exc}"
                raise TunnelratBackendAbort(f"Exception: {exc}") from exc

        await connection_manager.close_all()
