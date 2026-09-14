"""Defines the Connection class"""

# Standard libraries
import asyncio
import threading
from pathlib import Path
from typing import Any

# Third-party libraries
import fabric
from pydantic import BaseModel, Field, PrivateAttr

from tunnelrat.constants import DEFAULT_SSH_CONNECTION_TIMEOUT_S, OSTypes

# Project libraries
from tunnelrat.ssh.forward import ForwardConfig, SshForward


class SshConnectionConfig(BaseModel):
    name: str
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    os: OSTypes
    username: str = Field(alias="user")
    password: str | None = Field(default=None)
    ssh_key_path: Path | None = Field(default=None)
    ssh_key_password: str | None = Field(default=None)
    sudo_password: str | None = Field(default=None)
    ssh_connect_timeout_s: int = Field(default=DEFAULT_SSH_CONNECTION_TIMEOUT_S, alias="timeout")

    def to_fabric_connect_kwargs(self) -> dict[str, Any]:
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


class SshConnection(BaseModel):
    config: SshConnectionConfig
    _forward_list: list[SshForward] = PrivateAttr(init=False, default_factory=list)
    _fabric_connection: fabric.Connection | None = PrivateAttr(init=False, default=None)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @classmethod
    def from_config(cls, config: SshConnectionConfig):
        return cls(
            name=config.name,
            config=config,
        )

    def _create_connection_sync(self):
        assert self._fabric_connection is None
        with self._lock:
            self._fabric_connection = fabric.Connection(**self.config.to_fabric_connect_kwargs())
            self._fabric_connection.create_session()

    def _disconnect_sync(self):
        assert self._fabric_connection is not None
        with self._lock:
            for forward in self._forward_list:
                if forward.running:
                    forward._close_sync()
            self._fabric_connection.close()
            self._fabric_connection = None

    def _run_command_sync(self, script: str, sudo: bool = False) -> fabric.Result:
        assert self._fabric_connection is not None
        run_kwargs = {"warn": True, "hide": True}
        with self._lock:
            if sudo:
                return self._fabric_connection.sudo(script, **run_kwargs)
            return self._fabric_connection.run(script, **run_kwargs)

    async def create_forward(self, forward_config: ForwardConfig) -> SshForward:
        assert self._fabric_connection is not None
        with self._lock:
            forward = SshForward(
                config=forward_config,
                _fabric_connection=self._fabric_connection,
            )
            await forward.create()
            self._forward_list.append(forward)

    def get_forward_list(self) -> list[SshForward]:
        return self._forward_list

    def get_forward(self, name: str) -> SshForward | None:
        for forward in self._forward_list:
            if forward.config.name == name:
                return forward
        return None

    async def delete_forward(self, name: str):
        with self._lock:
            forward_index = None
            for index, forward in enumerate(self._forward_list):
                if forward.config.name == name:
                    forward_index = index
                    break
            if forward_index is None:
                return None

            await self._forward_list[forward_index].close()
            await self._forward_list.pop(forward_index)

    async def create_connection(self):
        await asyncio.to_thread(self._create_connection_sync)

    async def close(self):
        await asyncio.to_thread(self._disconnect_sync)

    async def run_command(self, script: str, sudo: bool = False) -> fabric.Result:
        return await asyncio.to_thread(self._run_command_sync, script=script, sudo=sudo)
