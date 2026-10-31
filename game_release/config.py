"""Reads a game's release.json, the one file that says how that game is built and released."""
from __future__ import annotations

import json
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "release.json"

# Every system a release can carry: the GitHub runner that builds it, and the kind of
# archive it is packed into. Windows opens a zip with nothing installed. Linux and Mac
# get a gzipped tar, which keeps the executable bit and symbolic links, and a Mac app
# needs both. Ubuntu 22.04 builds Linux, since a build only runs on systems with a C
# library at least as new as the one it was built on (Kaskade's reason), and 22.04's is
# old enough for most players. The Mac runners are the ones Sixth Sense Reborn proved.
SYSTEMS = {
    "windows": {"runner": "windows-latest", "archive": "zip"},
    "linux": {"runner": "ubuntu-22.04", "archive": "tar.gz"},
    "macos-arm64": {"runner": "macos-15", "archive": "tar.gz"},
    "macos-x86_64": {"runner": "macos-15-intel", "archive": "tar.gz"},
}

SPOKEN_SYSTEMS = {
    "windows": "Windows",
    "linux": "Linux",
    "macos-arm64": "Mac with Apple Silicon",
    "macos-x86_64": "Mac with an Intel processor",
}


class ConfigError(Exception):
    pass


def this_system() -> str | None:
    """The SYSTEMS name for the computer this runs on, or None if it has no build."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos-arm64" if platform.machine() == "arm64" else "macos-x86_64"
    return None


def family(system: str) -> str:
    """windows, linux or macos."""
    return system.split("-")[0]


@dataclass
class Config:
    root: Path
    name: str
    entry: str
    executable: str
    archive: str
    version_file: str
    version_pattern: str | None
    tag_prefix: str = "v"
    archive_template: str = "{archive}_{system}"
    archive_folder: bool = False
    fetch: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    native_packages: list = field(default_factory=list)
    native_exclude: list = field(default_factory=list)
    licenses: str = "folder"
    license_packages: list = field(default_factory=list)
    nuitka_args: dict = field(default_factory=dict)
    python: str = "3.12"
    systems: list = field(default_factory=lambda: list(SYSTEMS))
    bundle_id: str = ""
    macos_minimum: str = "11.0"
    changelog: str | None = None
    venv: str = "env"
    wsl_distro: str = "Ubuntu-22.04"
    wsl_python: str = "python3.12"

    def version(self) -> str:
        """The game's version, read from version_file with version_pattern, or the file's first line."""
        path = self.root / self.version_file
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ConfigError(f"the version file {self.version_file} could not be read: {error}")
        if self.version_pattern:
            match = re.search(self.version_pattern, text, re.MULTILINE)
            if not match:
                raise ConfigError(f"the version pattern found nothing in {self.version_file}")
            return match.group(1).strip()
        first = text.strip().splitlines()
        if not first:
            raise ConfigError(f"{self.version_file} is empty, so there is no version")
        return first[0].strip()

    def tag(self, version: str | None = None) -> str:
        return self.tag_prefix + (version or self.version())

    def version_from_tag(self, tag: str) -> str | None:
        return tag[len(self.tag_prefix):] if tag.startswith(self.tag_prefix) and len(tag) > len(self.tag_prefix) else None

    def nuitka_for(self, system: str) -> list:
        """Extra Nuitka arguments: those for every system, then the family's, then the exact system's."""
        args = list(self.nuitka_args.get("all", []))
        args += self.nuitka_args.get(family(system), [])
        if system != family(system):
            args += self.nuitka_args.get(system, [])
        return args

    def build_folder(self, system: str) -> Path:
        return self.root / "dist" / f"{self.archive}-{system}"

    def archive_name(self, version: str, system: str) -> str:
        """Like behind_closed_doors_windows.zip, from archive_name in release.json, where
        {archive}, {system} and {version} are filled in. The system uses underscores."""
        base = self.archive_template.format(archive=self.archive, system=system.replace("-", "_"),
                                            version=version)
        return f"{base}.{SYSTEMS[system]['archive']}"


def find_root(start: Path | None = None) -> Path:
    """The folder holding release.json: the start folder or the nearest one above it."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / CONFIG_NAME).is_file():
            return folder
    raise ConfigError(f"there is no {CONFIG_NAME} here or in any folder above {here}. "
                      "Run game-release init in the game's folder to make one.")


def _list(data, key):
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} in {CONFIG_NAME} must be a list of text")
    return value


def _licenses(data) -> str:
    mode = data.get("licenses", "folder")
    if mode not in ("folder", "file", "off"):
        raise ConfigError('licenses must be "folder", "file" or "off"')
    return mode


def _fetch(data) -> list:
    items = data.get("fetch", [])
    if not isinstance(items, list):
        raise ConfigError("fetch must be a list")
    for item in items:
        if not isinstance(item, dict) or "url" not in item or not (
                "extract_to" in item or "save_as" in item):
            raise ConfigError("each fetch entry needs a url, and extract_to or save_as")
    return items


def load(start: Path | None = None) -> Config:
    root = find_root(start)
    try:
        data = json.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
    except ValueError as error:
        raise ConfigError(f"{CONFIG_NAME} is not valid JSON: {error}")
    if not isinstance(data, dict):
        raise ConfigError(f"{CONFIG_NAME} must hold one object, in curly brackets")
    for key in ("name", "entry", "executable", "archive", "version"):
        if key not in data:
            raise ConfigError(f"{CONFIG_NAME} has no {key}, and it needs one")
    version = data["version"]
    if isinstance(version, str):
        version_file, version_pattern = version, None
    elif isinstance(version, dict) and "file" in version:
        version_file, version_pattern = version["file"], version.get("pattern")
    else:
        raise ConfigError('version must be a file name, or {"file": ..., "pattern": ...} with one group')
    systems = _list(data, "systems") or list(SYSTEMS)
    unknown = [s for s in systems if s not in SYSTEMS]
    if unknown:
        raise ConfigError(f"unknown systems {', '.join(unknown)}. The systems are {', '.join(SYSTEMS)}")
    nuitka_args = data.get("nuitka_args", {})
    if not isinstance(nuitka_args, dict):
        raise ConfigError('nuitka_args must be an object like {"all": [...], "windows": [...]}')
    macos = data.get("macos", {})
    wsl = data.get("wsl", {})
    archive = data["archive"]
    return Config(
        root=root,
        name=data["name"],
        entry=data["entry"],
        executable=data["executable"],
        archive=archive,
        version_file=version_file,
        version_pattern=version_pattern,
        tag_prefix=data.get("tag_prefix", "v"),
        archive_template=data.get("archive_name", "{archive}_{system}"),
        archive_folder=bool(data.get("archive_folder", False)),
        fetch=_fetch(data),
        assets=_list(data, "assets"),
        native_packages=_list(data, "native_packages"),
        native_exclude=_list(data, "native_exclude"),
        licenses=_licenses(data),
        license_packages=_list(data, "license_packages"),
        nuitka_args=nuitka_args,
        python=str(data.get("python", "3.12")),
        systems=systems,
        bundle_id=macos.get("bundle_id") or "com.tunmi13." + re.sub(r"[^A-Za-z0-9]", "", archive).lower(),
        macos_minimum=str(macos.get("minimum", "11.0")),
        changelog=data.get("changelog"),
        venv=data.get("venv", "env"),
        wsl_distro=wsl.get("distro", "Ubuntu-22.04"),
        wsl_python=wsl.get("python", "python" + str(data.get("python", "3.12"))),
    )
