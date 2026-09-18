"""Defines the Connection class"""

# Standard libraries
import asyncio
import threading
from pathlib import Path
from typing import Any

# Third-party libraries
import fabric
from pydantic import BaseModel, Field, PrivateAttr

from tunnelrat.constants import DEFAULT_SSH_CONNECTION_TIMEOUT_S, LOADER_INJECTED_KEY, OSTypes

# Project libraries
from tunnelrat.ssh.forward import ForwardConfig, SshForward


class SshConnectionConfig(BaseModel):
    """Describe one entry of the hosts block, the SSH target that steps refer to by name"""

    name: str = Field(
        description="Identifier of the host, taken from the key this entry sits under in the hosts block",
        json_schema_extra={LOADER_INJECTED_KEY: True},
    )
    host: str = Field(description="Hostname or address of the SSH server")
    port: int = Field(default=22, ge=1, le=65535, description="Port number the SSH server listens on")
    os: OSTypes = Field(description="Operating system of the host, which decides how commands are built")
    username: str = Field(alias="user", description="Username to authenticate as")
    password: str | None = Field(default=None, description="Password to authenticate with")
    ssh_key_path: Path | None = Field(default=None, description="Local path to the private key to authenticate with")
    ssh_key_password: str | None = Field(default=None, description="Passphrase protecting the private key")
    sudo_password: str | None = Field(default=None, description="Password used by steps that set sudo")
    ssh_connect_timeout_s: int = Field(
        default=DEFAULT_SSH_CONNECTION_TIMEOUT_S,
        alias="timeout",
        description="Seconds to wait for the SSH handshake before giving up",
    )

    def to_fabric_connect_kwargs(self) -> dict[str, Any]:
        """Return the keyword arguments fabric needs to open this connection

        Returns:
            The target, the credentials and the timeout keyed the way fabric expects them
        """
        config = None
        if self.sudo_password is not None:
            config = fabric.Config(overrides={"sudo": {"password": self.sudo_password}})

        connect_kwargs = {}
        if self.password:
            connect_kwargs.update({"password": self.password})
        if self.ssh_key_path:
            connect_kwargs.update({"key_filename": str(self.ssh_key_path)})
            if self.ssh_key_password:
                connect_kwargs.update({"passphrase": self.ssh_key_password})

        return {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "connect_kwargs": connect_kwargs,
            "config": config,
            "connect_timeout": self.ssh_connect_timeout_s,
        }

    def __str__(self) -> str:
        """Return the SSH target written as user, host and port

        Returns:
            The target in the form used in the step list
        """
        return f"SSH connection: {self.username}@{self.host}:{self.port}"


class SshConnection(BaseModel):
    """Hold one live SSH session and every forward opened through it"""

    config: SshConnectionConfig
    _forward_list: list[SshForward] = PrivateAttr(init=False, default_factory=list)
    _fabric_connection: fabric.Connection | None = PrivateAttr(init=False, default=None)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @classmethod
    def from_config(cls, config: SshConnectionConfig):
        """Return a connection that is not yet open for one host config

        Args:
            config: The host to connect to when create_connection is called
        """
        return cls(config=config)

    def __str__(self) -> str:
        """Return the SSH target this connection was built from

        Returns:
            The target in the form used in the step list
        """
        return str(self.config).replace("SSH connection: ", "")

    def _create_connection_sync(self):
        """Open the SSH session on the calling thread"""
        assert self._fabric_connection is None
        with self._lock:
            self._fabric_connection = fabric.Connection(**self.config.to_fabric_connect_kwargs())
            self._fabric_connection.create_session()

    def _disconnect_sync(self):
        """Close every running forward and then the SSH session on the calling thread"""
        assert self._fabric_connection is not None
        with self._lock:
            for forward in self._forward_list:
                if forward.running:
                    forward._close_sync()
            self._fabric_connection.close()
            self._fabric_connection = None

    def _run_command_sync(self, script: str, sudo: bool = False) -> fabric.Result:
        """Return the result of running one script on the calling thread

        Args:
            script: The command line or script body to run
            sudo: Whether to run the script through sudo

        Returns:
            The exit code and the captured output of the script
        """
        assert self._fabric_connection is not None
        run_kwargs = {"warn": True, "hide": True}
        with self._lock:
            if sudo:
                return self._fabric_connection.sudo(script, **run_kwargs)
            return self._fabric_connection.run(script, **run_kwargs)

    async def create_forward(self, forward_config: ForwardConfig) -> SshForward:
        """Open one tunnel through this connection and keep track of it

        Args:
            forward_config: The tunnel to open

        Returns:
            The tunnel that was opened
        """
        assert self._fabric_connection is not None
        forward = SshForward(config=forward_config)
        forward._fabric_connection = self._fabric_connection

        await forward.create()

        with self._lock:
            self._forward_list.append(forward)

        return forward

    def get_forward_list(self) -> list[SshForward]:
        """Return every tunnel opened through this connection

        Returns:
            The tunnels in the order they were opened, empty if there are none
        """
        return self._forward_list

    def get_forward(self, name: str) -> SshForward | None:
        """Return one tunnel opened through this connection

        Args:
            name: The identifier of the tunnel to look up

        Returns:
            The matching tunnel, or None if this connection has no tunnel by that name
        """
        for forward in self._forward_list:
            if forward.config.name == name:
                return forward
        return None

    async def delete_forward(self, name: str):
        """Close one tunnel and drop it from this connection

        Args:
            name: The identifier of the tunnel to close
        """
        with self._lock:
            forward_index = None
            for index, forward in enumerate(self._forward_list):
                if forward.config.name == name:
                    forward_index = index
                    break
            if forward_index is None:
                return None
            forward = self._forward_list.pop(forward_index)

        await forward.close()

    async def create_connection(self):
        """Open the SSH session without blocking the event loop"""
        await asyncio.to_thread(self._create_connection_sync)

    async def close(self):
        """Close the SSH session without blocking the event loop"""
        await asyncio.to_thread(self._disconnect_sync)

    async def run_command(self, script: str, sudo: bool = False) -> fabric.Result:
        """Return the result of running one script without blocking the event loop

        Args:
            script: The command line or script body to run
            sudo: Whether to run the script through sudo

        Returns:
            The exit code and the captured output of the script
        """
        return await asyncio.to_thread(self._run_command_sync, script=script, sudo=sudo)
