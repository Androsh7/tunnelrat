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
    time_s: int = Field(alias="time")


class BlockConfig(BaseModel):
    timeout_s: int | None = Field(alias="timeout", default=None)
    exit_on_timeout: bool


class CommentConfig(BaseModel):
    body: str


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
    step_number: int = Field(ge=1)
    step_type: StepTypes
    config: STEP_MODELS

    @classmethod
    def from_dict(cls, step_dict: dict, step_number: int):
        step_type = StepTypes(list(step_dict.keys())[0])
        config_model = STEP_TO_MODEL[step_type]

        return cls(
            step_type=step_type,
            step_number=step_number,
            config=config_model(name=f"step_{step_number}", **(step_dict.get(step_type) or {})),
        )


@define
class Script:
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
                except TimeoutError:
                    if not step.config.exit_on_timeout:
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
