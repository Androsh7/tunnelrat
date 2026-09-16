"""Defines the Forward class"""

# Standard libraries
import asyncio
import contextlib
import threading

# Third-party libraries
import fabric
from pydantic import BaseModel, Field, PrivateAttr

# Project libraries
from tunnelrat.constants import LOADER_INJECTED_KEY, ForwardTypes


class ForwardConfig(BaseModel):
    """Describe a forward step that tunnels a port through one host"""

    name: str = Field(
        description="Identifier of the forward, assigned from the step number by the script loader",
        json_schema_extra={LOADER_INJECTED_KEY: True},
    )
    forward_type: ForwardTypes = Field(
        alias="type",
        description="Direction of the tunnel, local binds the port on this machine and remote binds it on the host",
    )
    connection_name: str = Field(alias="via", description="Name of the host from the hosts block to tunnel through")
    local_host: str = Field(default="127.0.0.1", description="Address of the local end of the tunnel")
    local_port: int = Field(ge=1, le=65535, description="Port number of the local end of the tunnel")
    remote_host: str = Field(default="127.0.0.1", description="Address of the remote end of the tunnel")
    remote_port: int = Field(ge=1, le=65535, description="Port number of the remote end of the tunnel")

    def __str__(self) -> str:
        """Return the tunnel drawn as an arrow from one end to the other"""
        if self.forward_type == ForwardTypes.LOCAL:
            return (
                "SSH forward: "
                f'{self.local_host}:{self.local_port} -> "{self.connection_name}" '
                f"-> {self.remote_host}:{self.remote_port}"
            )
        if self.forward_type == ForwardTypes.REMOTE:
            return (
                "SSH forward: "
                f'{self.local_host}:{self.local_port} <- "{self.connection_name}" '
                f"<- {self.remote_host}:{self.remote_port}"
            )
        raise KeyError(f"Invalid forward type {self.forward_type}")

    def to_fabric_forward_kwargs(self) -> dict[str, int | str]:
        """Return the keyword arguments fabric needs to open this tunnel

        Returns:
            The two ends of the tunnel keyed the way fabric expects them
        """
        return {
            "local_host": self.local_host,
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
        }


class SshForward(BaseModel):
    """Hold one live tunnel and the fabric context manager keeping it open"""

    config: ForwardConfig
    _fabric_connection: fabric.Connection | None = PrivateAttr(default=None)
    _connection_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _fabric_forward: contextlib._GeneratorContextManager | None = PrivateAttr(default=None)
    running: bool = Field(init=False, default=False)

    def __str__(self) -> str:
        """Return the tunnel drawn as an arrow from one end to the other"""
        return str(self.config).replace("SSH forward: ", "")

    def _create_sync(self):
        """Open the tunnel on the calling thread

        Raises:
            ValueError: If the forward type is neither local nor remote
        """
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
            self._fabric_forward = forward_func(**self.config.to_fabric_forward_kwargs())

            # Connect to the forward
            self._fabric_forward.__enter__()
            self.running = True

    async def create(self):
        """Open the tunnel without blocking the event loop"""
        await asyncio.to_thread(self._create_sync)

    def _close_sync(self):
        """Close the tunnel on the calling thread"""
        assert self.running
        with self._connection_lock:
            self._fabric_forward.__exit__(None, None, None)
            self.running = False
            self._fabric_forward = None

    async def close(self):
        """Close the tunnel without blocking the event loop"""
        await asyncio.to_thread(self._close_sync)
