"""Defines the connection_manager singleton"""

# Standard libraries
import threading

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
    connection_list: list[SshConnection] = field(
        init=False,
        factory=list,
        validator=validators.deep_iterable(
            member_validator=validators.instance_of(SshConnection),
            iterable_validator=validators.instance_of(list),
        ),
    )
    _lock: threading.Lock = field(init=False, factory=threading.Lock, validator=validators.instance_of(threading.Lock))

    async def create_connection(self, config: SshConnectionConfig):
        with self._lock:
            connection = SshConnection.from_config(config)
            await connection.create_connection()
            self.connection_list.append(connection)

    async def create_forward(self, config: ForwardConfig):
        with self._lock:
            connection = self.get_connection(config.connection_name)
            await connection.create_forward(config)

    async def run_command(self, config: CommandConfig):
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
        for connection in self.connection_list:
            if connection.config.name == name:
                return connection
        raise KeyError(f'No SSH connection found with name "{name}"')

    async def close_all(self):
        with self._lock:
            for connection in self.connection_list:
                await connection.close()
            self.connection_list.clear()


connection_manager = ConnectionManager()
