"""Finds the native libraries a game's packages load by hand, which Nuitka cannot see.

Nuitka follows Python imports, and the libraries those imports link against. It cannot
see a library a package opens itself at runtime, like cyal's OpenAL32.dll, prism's
prism.dll, sound_lib's BASS files, or libsndfile in _soundfile_data. So every package
named in native_packages has its native files copied into the build after Nuitka has
finished, at the same path they have under site-packages, so each package's own lookup
finds them. A file Nuitka already put there is left alone.

Only this system's kind of library is taken: .dll and .pyd on Windows, .so on Linux,
.dylib and .so on a Mac. A package that ships every system's files, like sound_lib,
so only carries the right ones.

Two more things Nuitka cannot see:
- A Linux wheel repaired by auditwheel keeps the libraries its code links against in a
  sibling <distribution>.libs folder, outside the package. prism's libprism.so finds
  its own through a relative path to there, so the folder is copied too.
- A compiled extension module in a folder that is not a package, like prismatoid 0.18's
  prism/_native/_prism_cffi, is imported through a path the package adds at runtime.
  It needs cffi's _cffi_backend module, which no code imports by name, and on Windows
  it links the stable ABI's python3.dll, which nothing else uses. Without those a
  build dies at startup with No module named prism._prism_cffi.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from importlib.metadata import packages_distributions
from pathlib import Path

from .config import family

_LIBRARY = {
    "windows": re.compile(r"\.(dll|pyd)$", re.IGNORECASE),
    "linux": re.compile(r"\.so(\.\d+)*$"),
    "macos": re.compile(r"\.(dylib|so)$"),
}
# Names compiled Python extension modules have: buffer.cp312-win_amd64.pyd,
# buffer.cpython-312-x86_64-linux-gnu.so, _prism_cffi.abi3.so.
_EXTENSION = re.compile(r"(\.pyd$|\.cpython-|\.abi3\.|\.cp\d+-)")


@dataclass
class Natives:
    files: list = field(default_factory=list)   # (source path, path inside the build)
    hidden_extensions: list = field(default_factory=list)
    missing: list = field(default_factory=list)

    def summary(self) -> str:
        return f"{len(self.files)} native files"


def _package_dir(name: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0])


def find(packages, exclude, system: str) -> Natives:
    """The native files of packages, for system, with paths relative to site-packages."""
    pattern = _LIBRARY[family(system)]
    found = Natives()
    seen = set()
    distributions = packages_distributions()

    def add(path: Path, site: Path):
        rel = path.relative_to(site).as_posix()
        if rel in seen or any(fnmatch.fnmatch(rel, glob) for glob in exclude):
            return
        seen.add(rel)
        found.files.append((path, rel))
        if _EXTENSION.search(path.name) and not (path.parent / "__init__.py").exists():
            found.hidden_extensions.append(rel)

    for name in packages:
        pkg = _package_dir(name)
        if pkg is None:
            found.missing.append(name)
            continue
        site = pkg.parent
        for path in sorted(pkg.rglob("*")):
            if path.is_file() and pattern.search(path.name):
                add(path, site)
        for dist in distributions.get(name, []):
            for libs in (site / f"{dist}.libs", site / f"{dist.replace('-', '_')}.libs"):
                if libs.is_dir():
                    for path in sorted(libs.rglob("*")):
                        if path.is_file():
                            add(path, site)
    return found


def python3_dll() -> Path | None:
    """The stable ABI's python3.dll, which a hidden extension module links on Windows."""
    path = Path(sys.base_prefix) / "python3.dll"
    return path if path.is_file() else None
