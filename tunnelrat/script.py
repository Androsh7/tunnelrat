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
from tunnelrat.exceptions import TunnelratBackendAbortError
from tunnelrat.ssh.command import BatchCommandConfig, CommandConfig
from tunnelrat.ssh.connection import SshConnectionConfig
from tunnelrat.ssh.connection_manager import connection_manager
from tunnelrat.ssh.forward import ForwardConfig


class WaitConfig(BaseModel):
    """Describe a wait step that pauses the script for a fixed time"""

    time_s: int = Field(alias="time", description="Seconds to pause before moving on to the next step")

    def __str__(self) -> str:
        """Return the wait described as a line of text

        Returns:
            The number of seconds the step waits for
        """
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

    def __str__(self) -> str:
        """Return the block described as a line of text

        Returns:
            The timeout the step blocks until, or nothing when it blocks until interrupted
        """
        return f"Blocking until interrupted (timeout {self.timeout_s} seconds)"


class CommentConfig(BaseModel):
    """Describe a comment step that prints a message to the console"""

    body: str = Field(description="Text to print when the step is reached")

    def __str__(self) -> str:
        """Return the comment text

        Returns:
            The body of the comment
        """
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
        step_type = StepTypes(next(iter(step_dict)))
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
        with Path(yaml_path).open(mode="rb") as yaml_file:
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
        """Run every step in order, mark its outcome and then close every connection

        Raises:
            TunnelratBackendAbortError: If any step fails, after marking that step failed
        """
        for step in self.step_list:
            try:
                step.started = True
                await self._execute_step(step)
                step.completed = True
                step.progress = ""
            except Exception as exc:
                step.failed = True
                step.progress = f"Exception: {exc}"
                raise TunnelratBackendAbortError(f"Exception: {exc}") from exc

        await connection_manager.close_all()

    async def _execute_step(self, step: Step):
        """Run one step by dispatching on its type

        Args:
            step: The step to run

        Raises:
            KeyError: If a step has a type that has no execution path
        """
        handler_by_type = {
            StepTypes.CREATE_CONNECTION: self._execute_create_connection,
            StepTypes.COMMAND: self._execute_command,
            StepTypes.BATCH_COMMAND: self._execute_batch,
            StepTypes.CREATE_FORWARD: self._execute_create_forward,
            StepTypes.WAIT: self._execute_wait,
            StepTypes.BLOCK: self._execute_block,
            StepTypes.COMMENT: self._execute_comment,
        }
        if step.step_type not in handler_by_type:
            raise KeyError(f"Invalid step type {step.step_type}")
        await handler_by_type[step.step_type](step)

    async def _execute_create_connection(self, step: Step):
        """Open the ssh connection described by one step

        Args:
            step: The connection step to run
        """
        await connection_manager.create_connection(step.config)

    async def _execute_command(self, step: Step):
        """Run the command described by one step on one host

        Args:
            step: The command step to run
        """
        await connection_manager.run_command(step.config)

    async def _execute_batch(self, step: Step):
        """Run the batch command described by one step on each of its hosts

        Args:
            step: The batch step to run
        """
        for connection_name in step.config.connection_name_list:
            await connection_manager.run_command(step.config.to_command_config(connection_name))

    async def _execute_create_forward(self, step: Step):
        """Open the tunnel described by one step

        Args:
            step: The forward step to run
        """
        await connection_manager.create_forward(step.config)

    async def _execute_wait(self, step: Step):
        """Pause for the number of seconds described by one step, counting down as it waits

        Args:
            step: The wait step to run
        """
        elapsed_time = 0
        start_time = time()
        while elapsed_time < step.config.time_s:
            elapsed_time = time() - start_time
            step.progress = f"{int(step.config.time_s - elapsed_time)} seconds remaining"
            await asyncio.sleep(0.25)

    async def _execute_block(self, step: Step):
        """Hold the script open until interrupted or until the timeout is reached

        Args:
            step: The block step to run

        Raises:
            TimeoutError: If the timeout is reached and the step is set to raise on timeout
        """
        start_time = time()
        elapsed_time = 0
        try:
            while step.config.timeout_s is None or elapsed_time < step.config.timeout_s:
                elapsed_time = time() - start_time
                step.progress = f"{int(elapsed_time)} seconds elapsed"
                await asyncio.sleep(0.25)
            if step.config.raise_on_timeout:
                raise TimeoutError(f"Blocking timed out after {int(elapsed_time)} seconds")
        except asyncio.CancelledError:
            asyncio.current_task().uncancel()

    async def _execute_comment(self, step: Step):
        """Do nothing because a comment only shows its text in the panel

        Args:
            step: The comment step, shown by the panel and otherwise left alone
        """
