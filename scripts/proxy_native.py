"""Off-device helpers for ``check_proxy_compat.py``: ELF exports and a simulated hasher.

Nothing here loads a native library. Bundled ``libraproxy_rchash.so`` files are ARM builds, so
their exported symbols are read from the ELF file itself, and hashing is simulated by
:class:`SimulatedRcHash`, which stands in for the library behind the proxy's real Python
wrapper. Only a device can test the native code (TESTING.md, "RAOfflineProxy compatibility").
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import re
import struct
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS64 = 2
_ELFDATA2LSB = 1  # little-endian
_SHT_DYNSYM = 11
_STB_GLOBAL, _STB_WEAK = 1, 2
_STT_FUNC = 2
_SHN_UNDEF = 0
_HASH_STRIDE = 33  # rc_hash's char[33] per candidate, as in rom_hashing
_BOUND_FUNCTION = re.compile(r"\blibrary\.(raproxy_[a-z0-9_]+)\b")


class ElfError(ValueError):
    """The file isn't an ELF shared library we can read."""


def elf_function_exports(path: Path) -> set[str]:
    """Return the functions an ELF shared library defines in its dynamic symbol table.

    Args:
        path: The ``.so`` file (any architecture, 32 or 64-bit, either byte order).

    Returns:
        Names of defined global or weak functions.

    Raises:
        ElfError: The file isn't a readable ELF file.
    """
    data = path.read_bytes()
    if data[:4] != _ELF_MAGIC or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ElfError(f"{path} is not an ELF file")
    wide = data[4] == _ELFCLASS64
    order = "<" if data[5] == _ELFDATA2LSB else ">"
    if wide:
        shoff, shentsize, shnum = (
            struct.unpack_from(order + "Q", data, 0x28)[0],
            *struct.unpack_from(order + "HH", data, 0x3A),
        )
        section = order + "IIQQQQIIQQ"
        symbol = order + "IBBHQQ"
    else:
        shoff, shentsize, shnum = (
            struct.unpack_from(order + "I", data, 0x20)[0],
            *struct.unpack_from(order + "HH", data, 0x2E),
        )
        section = order + "IIIIIIIIII"
        symbol = order + "IIIBBH"
    try:
        sections = [struct.unpack_from(section, data, shoff + i * shentsize) for i in range(shnum)]
    except struct.error as exc:
        raise ElfError(f"{path}: truncated section table") from exc
    exports: set[str] = set()
    for header in sections:
        if header[1] != _SHT_DYNSYM:
            continue
        offset, size, link, entsize = header[4], header[5], header[6], header[9]
        strings_offset = sections[link][4]
        for start in range(offset, offset + size, entsize):
            fields = struct.unpack_from(symbol, data, start)
            if wide:
                name, info, _other, shndx = fields[0], fields[1], fields[2], fields[3]
            else:
                name, info, _other, shndx = fields[0], fields[3], fields[4], fields[5]
            if (
                shndx == _SHN_UNDEF
                or info & 0xF != _STT_FUNC
                or info >> 4
                not in (
                    _STB_GLOBAL,
                    _STB_WEAK,
                )
            ):
                continue
            end = data.index(b"\0", strings_offset + name)
            exports.add(data[strings_offset + name : end].decode("ascii", "replace"))
    return exports


def bound_functions(wrapper_source: str) -> set[str]:
    """Return the native functions a ``rom_hashing.py`` source calls (``library.raproxy_*``)."""
    return set(_BOUND_FUNCTION.findall(wrapper_source))


def _write_hashes(buffer: ctypes.Array, hashes: list[str], limit: int) -> int:
    """Fill an rc_hash candidate buffer: 32 hex characters and a NUL per candidate."""
    hashes = hashes[:limit]
    for index, value in enumerate(hashes):
        chunk = value.encode("ascii") + b"\0"
        ctypes.memmove(ctypes.addressof(buffer) + index * _HASH_STRIDE, chunk, len(chunk))
    return len(hashes)


def _md5(data: bytes) -> str:
    """Return a lower-case hex MD5 (fixture identifiers, not security)."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


class SimulatedRcHash:
    """Stands in for ``libraproxy_rchash`` with the call signatures ``rom_hashing`` uses.

    Hashes are deterministic, so the same file gives the same candidates through any caller:
    a file's content (two candidates, to check their order), an archive's file name (rc_hash's
    arcade rule) and nothing for a ``.chd`` (an unreadable disc image). A simulated ``.7z`` is
    JSON mapping entry names to contents.
    """

    def raproxy_hash_file(self, path: bytes, buffer: ctypes.Array, limit: int) -> int:
        """Hash a file like ``raproxy_hash_file``."""
        file = Path(path.decode("utf-8"))
        suffix = file.suffix.lower()
        if suffix == ".chd":
            return 0
        if suffix in {".zip", ".7z"}:
            return _write_hashes(buffer, [_md5(b"arcade:" + file.name.encode())], limit)
        content = file.read_bytes()
        return _write_hashes(buffer, [_md5(content), _md5(b"alt:" + content)], limit)

    def raproxy_7z_list_entries(
        self, path: bytes, buffer: ctypes.Array, size: int, limit: int
    ) -> int:
        """List a simulated ``.7z`` like ``raproxy_7z_list_entries``."""
        names = list(self._seven_zip(path))[:limit]
        packed = b"".join(name.encode("utf-8") + b"\0" for name in names)[:size]
        ctypes.memmove(ctypes.addressof(buffer), packed, len(packed))
        return len(names)

    def raproxy_hash_7z_entry(
        self, path: bytes, entry: bytes, buffer: ctypes.Array, limit: int
    ) -> int:
        """Hash a simulated ``.7z`` entry like ``raproxy_hash_7z_entry``."""
        content = self._seven_zip(path).get(entry.decode("utf-8"))
        if content is None or content == "!unreadable":
            return 0
        return _write_hashes(buffer, [_md5(content.encode())], limit)

    @staticmethod
    def _seven_zip(path: bytes) -> dict[str, str]:
        """Read a simulated ``.7z``: a JSON object of entry names and contents."""
        try:
            data = json.loads(Path(path.decode("utf-8")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
