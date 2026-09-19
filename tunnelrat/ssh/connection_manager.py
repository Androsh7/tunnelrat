"""Defines the connection_manager singleton"""

# Standard libraries
import asyncio

# Third-party libraries
from attrs import define, field, validators

from tunnelrat.commands.linux import generate_linux_command
from tunnelrat.commands.windows import generate_windows_command
from tunnelrat.constants import OSTypes
from tunnelrat.script import CommandConfig

# Project libraries
from tunnelrat.ssh.connection import SshConnection, SshConnectionConfig
from tunnelrat.ssh.forward import ForwardConfig


@define
class ConnectionManager:
    """Hold every open ssh connection and run steps against them"""

    connection_list: list[SshConnection] = field(
        init=False,
        factory=list,
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(SshConnection),
            iterable_validator=validators.instance_of(list),
        ),
    )
    _lock: asyncio.Lock = field(init=False, factory=asyncio.Lock, validator=validators.instance_of(asyncio.Lock))

    async def create_connection(self, config: SshConnectionConfig):
        """Open one ssh connection and keep track of it

        Args:
            config: The host to connect to
        """
        async with self._lock:
            connection = SshConnection.from_config(config)
            await connection.create_connection()
            self.connection_list.append(connection)

    async def create_forward(self, config: ForwardConfig):
        """Open one tunnel through an already open connection

        Args:
            config: The tunnel to open, naming the host to tunnel through
        """
        async with self._lock:
            connection = self.get_connection(config.connection_name)
            await connection.create_forward(config)

    async def run_command(self, config: CommandConfig):
        """Run one command on the host it names and write any captured output

        Args:
            config: The command to run, naming the host and the output files

        Raises:
            KeyError: If the host has an operating system with no command builder
        """
        connection = self.get_connection(config.connection_name)

        if connection.config.os == OSTypes.WINDOWS:
            command = generate_windows_command(script=config.script, executable=config.executable)
        elif connection.config.os == OSTypes.LINUX:
            command = generate_linux_command(script=config.script, executable=config.executable)
        else:
            raise KeyError(f"Invalid OS type {connection.config.os}")

        result = await connection.run_command(script=command, sudo=config.sudo)
        if config.stdout_file is not None:
            config.stdout_file.write_text(result.stdout)
        if config.stderr_file is not None:
            config.stderr_file.write_text(result.stderr)

    def get_connection(self, name: str) -> SshConnection:
        """Return the open connection with one name

        Args:
            name: The identifier of the host to look up

        Raises:
            KeyError: If no open connection has that name

        Returns:
            The matching open connection
        """
        for connection in self.connection_list:
            if connection.config.name == name:
                return connection
        raise KeyError(f'No SSH connection found with name "{name}"')

    async def close_all(self):
        """Close every open connection and forget them all"""
        async with self._lock:
            for connection in self.connection_list:
                await connection.close()
            self.connection_list.clear()


connection_manager = ConnectionManager()
