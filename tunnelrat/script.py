"""Defines the script class"""

# Standard libraries
import asyncio
from pathlib import Path

# Third-party libraries
import yaml
from attrs import define, field, validators
from loguru import logger
from pydantic import BaseModel, Field

# Project libraries
from tunnelrat.constants import StepTypes
from tunnelrat.ssh.command import BatchCommandConfig, CommandConfig
from tunnelrat.ssh.connection import SshConnectionConfig
from tunnelrat.ssh.connection_manager import connection_manager
from tunnelrat.ssh.forward import ForwardConfig


class WaitConfig(BaseModel):
    """Describe a wait step that pauses the script for a fixed time"""

    time_s: int = Field(alias="time", description="Seconds to pause before moving on to the next step")


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


class CommentConfig(BaseModel):
    """Describe a comment step that prints a message to the console"""

    body: str = Field(description="Text to print when the step is reached")


STEP_MODELS = CommandConfig | ForwardConfig | WaitConfig | BlockConfig | CommentConfig | BatchCommandConfig
STEP_TO_MODEL: dict[StepTypes, STEP_MODELS] = {
    StepTypes.COMMAND: CommandConfig,
    StepTypes.BATCH_COMMAND: BatchCommandConfig,
    StepTypes.FORWARD: ForwardConfig,
    StepTypes.WAIT: WaitConfig,
    StepTypes.BLOCK: BlockConfig,
    StepTypes.COMMENT: CommentConfig,
}


class StepConfig(BaseModel):
    """Wrap one step of a script with its position and the model describing it"""

    step_number: int = Field(ge=1, description="Position of the step in the steps list, counted from one")
    step_type: StepTypes = Field(description="Kind of step, taken from the single key of the step entry")
    config: STEP_MODELS = Field(description="Settings of the step, validated against the model for its type")

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
            config=config_model(name=f"step_{step_number}", **(step_dict.get(step_type) or {})),
        )


@define
class Script:
    """Hold the hosts and the ordered steps parsed out of one script file"""

    host_list: list[SshConnectionConfig] = field(
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(SshConnectionConfig),
            iterable_validator=validators.instance_of(list),
        )
    )
    step_list: list[StepConfig] = field(
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(StepConfig),
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

        host_list = []
        logger.debug(f"Loading host configs from script {yaml_path}")
        for host_name, host_dict in script_dict["hosts"].items():
            logger.debug(f"Loading SSH config for {host_name}")
            host_list.append(SshConnectionConfig(name=host_name, **host_dict))

        logger.debug(f"Loading step configs from script {yaml_path}")
        step_list = []
        for step_number, step_dict in enumerate(script_dict["steps"], start=1):
            logger.debug(f"Loading step {step_number}/{len(script_dict['steps'])}")
            step_list.append(StepConfig.from_dict(step_dict=step_dict, step_number=step_number))

        return cls(
            host_list=host_list,
            step_list=step_list,
        )

    async def run_script(self, dry_run: bool = False):
        """Open every host connection, run every step in order and then clean up

        Args:
            dry_run: Whether to walk the script without opening connections or running commands

        Raises:
            KeyError: If a step has a type that has no execution path
        """
        for host_number, host in enumerate(self.host_list, start=1):
            logger.info(
                f"Creating connection {host_number}/{len(self.host_list)} for host {host.name} ({host.username}@{host.host}:{host.port})"
            )
            if not dry_run:
                await connection_manager.create_connection(host)
            else:
                logger.warning("DRY RUN - NO CONNECTIONS INITIATED")

        for step in self.step_list:
            logger.info(f"Running step {step.step_number}/{len(self.step_list)}")

            # Run a command
            if step.step_type == StepTypes.COMMAND:
                logger.info(f"Running command on host {step.config.connection_name}: {step.config.script}")
                if not dry_run:
                    await connection_manager.run_command(step.config)
                else:
                    logger.warning("DRY RUN - NO COMMAND EXECUTED")

            # Run a batch command
            if step.step_type == StepTypes.BATCH_COMMAND:
                logger.info(
                    f"Running batch command on hosts ({', '.join(step.config.connection_name_list)}): {step.config.script}"
                )
                for connection_name in step.config.connection_name_list:
                    if not dry_run:
                        await connection_manager.run_command(step.config.to_command_config(connection_name))
                    else:
                        logger.warning("DRY RUN - NO BATCH COMMAND EXECUTED")

            # Create a forward
            elif step.step_type == StepTypes.FORWARD:
                logger.info(f"Creating forward: {step.config}")
                if not dry_run:
                    await connection_manager.create_forward(step.config)
                else:
                    logger.warning("DRY RUN - NO FORWARD CREATED")

            # Wait for some time
            elif step.step_type == StepTypes.WAIT:
                logger.info(f"Waiting for {step.config.time_s} second{'s' if step.config.time_s > 1 else ''}")
                await asyncio.sleep(step.config.time_s)

            # Block with an optional timeout
            elif step.step_type == StepTypes.BLOCK:
                timeout_str = "" if step.config.timeout_s is None else f" timeout in {step.config.timeout_s} seconds"
                logger.info(f"Blocking (exit with CTRL + C){timeout_str}")
                try:
                    if step.config.timeout_s:
                        with asyncio.timeout(step.config.timeout_s):
                            await asyncio.Event().wait()
                    else:
                        await asyncio.Event().wait()
                except asyncio.TimeoutError:
                    if step.config.raise_on_timeout:
                        raise
                except asyncio.CancelledError:
                    asyncio.current_task().uncancel()

            # Write a Comment
            elif step.step_type == StepTypes.COMMENT:
                logger.info(f'Writing comment "{step.config.body}"')
                print(step.config.body)

            else:
                raise KeyError(f"Invalid step type {step.step_type}")

        logger.info("Performing connection cleanup")
        await connection_manager.close_all()
