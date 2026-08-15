from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .models import SandboxCommand, SandboxCommandResult, SandboxHandle, SandboxLimits


CancelCheck = Callable[[], bool]


class SandboxUnavailableError(RuntimeError):
    pass


class SandboxSecurityError(ValueError):
    pass


class SandboxProvider(ABC):
    name = "unavailable"
    available = False

    @abstractmethod
    def create(self, *, owner_id: str, job_id: str, limits: SandboxLimits) -> SandboxHandle: ...

    @abstractmethod
    def destroy(self, handle: SandboxHandle) -> None: ...

    @abstractmethod
    def execute(self, handle: SandboxHandle, command: SandboxCommand, *, cancel_check: CancelCheck | None = None) -> SandboxCommandResult: ...

    @abstractmethod
    def write_file(self, handle: SandboxHandle, path: str, content: bytes) -> None: ...

    @abstractmethod
    def read_file(self, handle: SandboxHandle, path: str) -> bytes: ...

    @abstractmethod
    def list_files(self, handle: SandboxHandle) -> list[str]: ...

    @abstractmethod
    def list_directory(self, handle: SandboxHandle, path: str = ".") -> list[str]: ...

    @abstractmethod
    def stat(self, handle: SandboxHandle, path: str) -> dict: ...

    @abstractmethod
    def file_operation(self, handle: SandboxHandle, operation: str, path: str, destination: str | None = None) -> None: ...

    @abstractmethod
    def export_archive(self, handle: SandboxHandle) -> bytes: ...

    @abstractmethod
    def restore_archive(self, handle: SandboxHandle, archive: bytes) -> None: ...

    @abstractmethod
    def toolchains(self, handle: SandboxHandle) -> dict[str, str]: ...


class UnavailableSandboxProvider(SandboxProvider):
    def _raise(self):
        raise SandboxUnavailableError("sandbox_unavailable")

    def create(self, **_kwargs): self._raise()
    def destroy(self, _handle): return None
    def execute(self, *_args, **_kwargs): self._raise()
    def write_file(self, *_args, **_kwargs): self._raise()
    def read_file(self, *_args, **_kwargs): self._raise()
    def list_files(self, *_args, **_kwargs): self._raise()
    def list_directory(self, *_args, **_kwargs): self._raise()
    def stat(self, *_args, **_kwargs): self._raise()
    def file_operation(self, *_args, **_kwargs): self._raise()
    def export_archive(self, *_args, **_kwargs): self._raise()
    def restore_archive(self, *_args, **_kwargs): self._raise()
    def toolchains(self, *_args, **_kwargs): return {}
