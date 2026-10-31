"""Gathers the licenses of the libraries a build carries, and ships them one of three ways.

Most open source licenses let a game redistribute a library only with its license and
copyright notice alongside. licenses in release.json chooses how:
- folder: a licenses folder, with one folder per library holding its files as shipped.
- file: one licenses.txt, with a heading for each library, beside the readme.
- off: none at all.
folder is the default.

The libraries are every package in native_packages and license_packages, plus Python
itself. A package's licenses come from its install metadata and from license files in
the package folder, like pygame's LGPL.txt and libsndfile's COPYING.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import sysconfig
from importlib import metadata
from importlib.metadata import packages_distributions
from pathlib import Path

MODES = ("folder", "file", "off")
_LICENSE = re.compile(r"^(COPYING|LICEN[SC]E|NOTICE|L?GPL)([.-].*)?$", re.IGNORECASE)


def _package_dir(name: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0])


def _python_license() -> Path | None:
    for folder in (Path(sys.base_prefix), Path(sysconfig.get_paths()["stdlib"])):
        path = folder / "LICENSE.txt"
        if path.is_file():
            return path
    return None


def gather(packages) -> list:
    """(source file, name inside the licenses) for every license found, in a steady order."""
    found = []
    seen = set()

    def add(src: Path, name: str):
        if name.lower() not in seen and src.is_file():
            seen.add(name.lower())
            found.append((src, name))

    python = _python_license()
    if python:
        add(python, "python/LICENSE.txt")
    distributions = packages_distributions()
    for package in packages:
        dists = distributions.get(package, []) or [package]
        label = dists[0]
        for dist in dists:
            try:
                entries = metadata.distribution(dist).files or []
            except metadata.PackageNotFoundError:
                entries = []
            for entry in entries:
                parts = entry.parts
                if len(parts) < 2 or not parts[0].endswith(".dist-info"):
                    continue
                if parts[1] == "licenses" and len(parts) > 2:
                    inside = list(parts[2:])
                elif len(parts) == 2 and _LICENSE.match(parts[1]):
                    inside = [parts[1]]
                else:
                    continue
                add(Path(entry.locate()), "/".join([label, *inside]))
        pkg = _package_dir(package)
        if pkg:
            for path in sorted(pkg.rglob("*")):
                if path.is_file() and _LICENSE.match(path.name) and path.suffix.lower() not in (".py", ".pyc"):
                    add(path, f"{label}/{path.name}")
    return found


def _txt(name: str) -> str:
    """A name with no extension gets .txt, so Windows opens it instead of asking how."""
    return name if "." in Path(name).name else name + ".txt"


def ship(found, mode: str, dest: Path) -> str:
    """Write the licenses into dest the chosen way, and say what was done."""
    if mode == "off" or not found:
        return "No licenses were added, since licenses is off." if mode == "off" else "No licenses were found."
    if mode == "folder":
        for src, name in found:
            target = dest / "licenses" / _txt(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        return f"Added a licenses folder with {len(found)} files."
    parts = ["The licenses of the libraries this game is built with.\n"]
    for src, name in found:
        text = src.read_text(encoding="utf-8", errors="replace").strip()
        library, _, file = name.partition("/")
        parts.append(f"\n\n{library}, {file}\n\n{text}\n")
    (dest / "licenses.txt").write_text("".join(parts), encoding="utf-8")
    return f"Added licenses.txt, holding {len(found)} licenses."
