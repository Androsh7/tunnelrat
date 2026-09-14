"""Defines the Forward class"""

# Standard libraries
import asyncio
import contextlib
import threading

# Third-party libraries
import fabric
from pydantic import BaseModel, Field, PrivateAttr

# Project libraries
from tunnelrat.constants import ForwardTypes


class ForwardConfig(BaseModel):
    name: str
    forward_type: ForwardTypes = Field(alias="type")
    connection_name: str = Field(alias="via")
    local_host: str = Field(default="127.0.0.1")
    local_port: int = Field(ge=1, le=65535)
    remote_host: str = Field(default="127.0.0.1")
    remote_port: int = Field(ge=1, le=65535)

    def __str__(self) -> str:
        if self.forward_type == ForwardTypes.LOCAL:
            return f'{self.local_host}:{self.local_port} -> "{self.connection_name}" -> {self.remote_host}:{self.remote_port}'
        if self.forward_type == ForwardTypes.REMOTE:
            return f'{self.local_host}:{self.local_port} <- "{self.connection_name}" <- {self.remote_host}:{self.remote_port}'
        raise KeyError(f"Invalid forward type {self.forward_type}")

    def to_fabric_forward_kwargs(self) -> dict[str, int | str]:
        return {
            "local_host": self.local_host,
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
        }


class SshForward(BaseModel):
    config: ForwardConfig
    _fabric_connection: fabric.Connection | None = PrivateAttr()
    _connection_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _fabric_forward: contextlib._GeneratorContextManager | None = PrivateAttr(default=None)
    running: bool = Field(init=False, default=False)

    def _create_sync(self):
        assert not self.running

        with self._connection_lock:
            # Get the correct remote function
            forward_func = None
            if self.config.forward_type == ForwardTypes.LOCAL:
                forward_func = self._fabric_connection.forward_local
            elif self.config.forward_type == ForwardTypes.REMOTE:
                forward_func = self._fabric_connection.forward_remote
            else:
                raise ValueError(f"Invalid forward type {self.config.forward_type}")

            # Create the fabric forward
            self._fabric_forward = forward_func(self.config.to_fabric_forward_kwargs())

            # Connect to the forward
            self._fabric_forward.__enter__()
            self.running = True

    async def create(self):
        await asyncio.to_thread(self._start_sync)

    def _close_sync(self):
        assert self.running
        with self._connection_lock:
            self._fabric_forward.__exit__(None, None, None)
            self.running = False
            self._fabric_forward = None

    async def close(self):
        await asyncio.to_thread(self._close_sync)
