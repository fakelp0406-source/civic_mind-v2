"""Handle-verified file operations for the document catalogue (standard library only).

Path checks made *before* an operation (``documents.path_problem`` and ``resolves_within``) can
be defeated if a directory is swapped for a symlink or junction between the check and the
operation. The functions here close that gap where the platform allows it: they **open the file
first** and then ask the operating system where the opened handle really is
(``GetFinalPathNameByHandleW`` on Windows, ``/proc/self/fd`` on Linux, ``F_GETPATH`` on macOS).
Only if that final path lies inside the permitted directory is the handle used.

* ``read_verified`` - read a regular file, bounded by ``max_bytes``; the bytes returned are the
  bytes of the verified handle (one read, so a hash and a parse of them describe the same file).
* ``write_new_verified`` - create a file that must not exist (``O_EXCL``), verify the handle,
  then write. An existing file is never overwritten.
* ``write_or_match_verified`` - as above, or confirm an existing file holds exactly these bytes.
* ``move_verified`` - rename a file and verify **afterwards** that the destination is inside its
  folder and holds the same bytes as the verified source. A rename by path cannot be bound to a
  handle with the standard library, so a swap during the rename is detected, not prevented.

On a platform where the final path of a handle cannot be determined, every function raises
``UnsafePath`` (fail closed). ``O_NOFOLLOW`` is added where the platform defines it.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path

from civicmind.catalog.documents import path_problem, resolves_within

_READ = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
_CREATE = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)  # fmt: skip


class UnsafePath(ValueError):
    """A path is malformed, escapes its permitted directory, or cannot be verified."""


class TooLarge(ValueError):
    """A file is larger than the permitted limit (it was not read beyond the limit)."""

    def __init__(self, size: int, limit: int):
        self.size, self.limit = size, limit
        super().__init__(f"file has at least {size} bytes; the limit is {limit}")


def _final_path_windows(fd: int) -> str:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final = kernel32.GetFinalPathNameByHandleW
    get_final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    n = get_final(msvcrt.get_osfhandle(fd), buffer, len(buffer), 0)  # normalized, DOS name
    if n == 0 or n >= len(buffer):
        error = ctypes.get_last_error()
        raise UnsafePath(f"cannot determine the final path of a handle (error {error})")
    path = buffer.value
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    return path[4:] if path.startswith("\\\\?\\") else path


def final_path(fd: int) -> Path:
    """Where the open file descriptor ``fd`` really is (links resolved by the OS)."""
    if sys.platform == "win32":
        return Path(_final_path_windows(fd))
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))  # type: ignore[attr-defined]
        return Path(raw.split(b"\0", 1)[0].decode())
    raise UnsafePath(f"handle verification is not supported on {sys.platform}; refusing")


def _inside(path: Path, limit: Path) -> bool:
    p, lim = os.path.normcase(str(path)), os.path.normcase(str(limit))
    try:
        return os.path.commonpath([p, lim]) == lim
    except ValueError:  # different drives
        return False


def _limits(root: Path, bases: tuple[str, ...]) -> list[Path]:
    resolved = root.resolve()
    return [resolved / base for base in bases]


def _check_rel(rel: str) -> None:
    problem = path_problem(rel)
    if problem:
        raise UnsafePath(problem)


def _verify_handle(fd: int, root: Path, bases: tuple[str, ...]) -> Path:
    where = final_path(fd)
    if not any(_inside(where, limit) for limit in _limits(root, bases)):
        raise UnsafePath(f"the opened file is outside {' or '.join(f'{b}/' for b in bases)}")
    return where


def read_verified(root: str | Path, rel: str, bases: tuple[str, ...], max_bytes: int) -> bytes:
    """Bytes of the regular file ``root/rel``, verified to be inside one of ``bases``."""
    root = Path(root)
    _check_rel(rel)
    fd = os.open(root / rel, _READ)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise UnsafePath(f"{rel} is not a regular file")
        _verify_handle(fd, root, bases)
        size = os.fstat(fd).st_size
        if size > max_bytes:
            raise TooLarge(size, max_bytes)
        chunks, total = [], 0
        while chunk := os.read(fd, min(1 << 20, max_bytes + 1 - total)):
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:  # grew while reading
                raise TooLarge(total, max_bytes)
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_new_verified(root: str | Path, rel: str, base: str, data: bytes) -> None:
    """Create ``root/rel`` (it must not exist) inside ``base`` and write ``data``."""
    root = Path(root)
    _check_rel(rel)
    parent = Path(rel).parent.as_posix()
    if not resolves_within(root, parent, base):
        raise UnsafePath(f"{parent} resolves outside {base}/")
    (root / parent).mkdir(parents=True, exist_ok=True)
    fd = os.open(root / rel, _CREATE, 0o644)
    where = None
    try:
        where = final_path(fd)
        if not any(_inside(where, limit) for limit in _limits(root, (base,))):
            raise UnsafePath(f"the created file is outside {base}/")
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        if where is not None:  # remove only the file this call created, at its real location
            Path(where).unlink(missing_ok=True)
        raise
    os.close(fd)


def write_or_match_verified(root: str | Path, rel: str, base: str, data: bytes) -> str:
    """Write a new file, or confirm the existing one holds ``data``. Returns
    ``"written"`` or ``"identical"``; an existing file with other bytes raises ``UnsafePath``."""
    try:
        write_new_verified(root, rel, base, data)
        return "written"
    except FileExistsError:
        try:
            existing = read_verified(root, rel, (base,), max_bytes=len(data))
        except TooLarge:  # longer than ``data``: certainly different
            raise UnsafePath(f"{rel} already exists with different bytes") from None
        if existing != data:
            raise UnsafePath(f"{rel} already exists with different bytes") from None
        return "identical"


def move_verified(
    root: str | Path, src_rel: str, src_base: str, dst_rel: str, dst_base: str, max_bytes: int
) -> None:
    """Rename ``src_rel`` (inside ``src_base``) to ``dst_rel`` (inside ``dst_base``).

    The source is read through a verified handle first and hashed; after the rename the
    destination is read through a verified handle and must hold the same bytes. A destination
    that already exists is never replaced. A swap during the rename itself is detected
    (``UnsafePath``), not prevented.
    """
    root = Path(root)
    _check_rel(dst_rel)
    before = hashlib.sha256(read_verified(root, src_rel, (src_base,), max_bytes)).hexdigest()
    parent = Path(dst_rel).parent.as_posix()
    if not resolves_within(root, parent, dst_base):
        raise UnsafePath(f"{parent} resolves outside {dst_base}/")
    target = root / dst_rel
    if os.path.lexists(target):
        raise FileExistsError(f"{dst_rel} already exists; not replaced")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(root / src_rel, target)  # fails on Windows if the target appeared meanwhile
    after = hashlib.sha256(read_verified(root, dst_rel, (dst_base,), max_bytes)).hexdigest()
    if after != before:
        raise UnsafePath(f"{dst_rel} does not hold the verified source bytes; possible path swap")


__all__ = [
    "TooLarge",
    "UnsafePath",
    "final_path",
    "move_verified",
    "read_verified",
    "write_new_verified",
    "write_or_match_verified",
]
