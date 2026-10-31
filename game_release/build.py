"""Builds a game with Nuitka for the system this runs on.

Nuitka only builds for the system it runs on, so a Windows build is made on Windows, a
Linux build on Linux or in WSL, and a Mac build on a Mac, which is what GitHub's Mac
runners are for.

A build lands in dist/<archive>-<system>. On Windows and Linux that folder holds the
executable, its libraries and the game's assets. On a Mac it holds <name>.app, made the
way Sixth Sense Reborn makes its own:
- the program and its libraries in Contents/MacOS, the assets in Contents/Resources,
  with a link in Contents/MacOS to each, so a game that loads assets relative to its
  executable finds them;
- the version and the oldest macOS it opens on written into Info.plist, which Nuitka's
  command line cannot set, so an older Mac says the system is too old instead of failing;
- signed again ad hoc, because changing the app breaks the signature it had, and Apple
  Silicon refuses to open an app with a broken signature.
A console build on a Mac is a plain folder instead, to see why a game will not start.
"""
from __future__ import annotations

import importlib.util
import os
import plistlib
import re
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path

from . import natives as natives_mod
from .config import SPOKEN_SYSTEMS, Config, family, this_system
from .ui import say

MAC_NOTE_NAME = "If the game will not open on your Mac.txt"
MAC_NOTE = """This game is not from the App Store, and Apple has not checked it, so macOS may refuse to open it the first time, or say it is damaged. It is not damaged.

To open it, open Terminal, from Applications, then Utilities. Type the following, with a space at the end, but do not press Return yet:

xattr -dr com.apple.quarantine

Then drag {app} from Finder into the Terminal window, which adds its location, and press Return. The game opens normally from then on.

Or, in Finder, press Control and click the game, choose Open, then choose Open again in the warning.
"""


class BuildError(Exception):
    pass


def requirement_mismatches(cfg: Config) -> list:
    """Packages pinned with == in requirements.txt whose installed version differs.

    Building with the wrong Python is how the prism._prism_cffi startup crash happened:
    the global Python had a newer prism than the game was pinned to."""
    path = cfg.root / "requirements.txt"
    if not path.is_file():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        marker = ""
        if ";" in line:
            line, marker = (part.strip() for part in line.split(";", 1))
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)\s*==\s*([^\s,]+)$", line)
        if not match:
            continue
        name, wanted = re.sub(r"\[.*\]", "", match.group(1)), match.group(2)
        try:
            have = installed_version(name)
        except PackageNotFoundError:
            if not marker:
                found.append(f"{name} {wanted} is not installed")
            continue
        if have != wanted:
            found.append(f"{name} is {have}, and requirements.txt wants {wanted}")
    return found


def problems(cfg: Config) -> list:
    """Everything that would stop a build here, in plain words."""
    found = []
    system = this_system()
    if system is None:
        found.append(f"builds are made on Windows, Linux or a Mac, and this is {sys.platform}")
        return found
    if sys.maxsize <= 2 ** 32:
        found.append("this is 32-bit Python, and builds need 64-bit")
    if importlib.util.find_spec("nuitka") is None:
        found.append("Nuitka is not installed in this Python. Run the setup step, or pip install nuitka")
    if not (cfg.root / cfg.entry).is_file():
        found.append(f"the entry script {cfg.entry} is not there")
    for asset in cfg.assets:
        if not (cfg.root / asset).exists():
            found.append(f"the asset {asset} is not there")
    missing = natives_mod.find(cfg.native_packages, cfg.native_exclude, system).missing
    if missing:
        found.append("these packages in native_packages are not installed: " + ", ".join(missing))
    try:
        cfg.version()
    except Exception as error:
        found.append(str(error))
    return found


def nuitka_command(cfg: Config, system: str, version: str, console: bool, natives, out: Path) -> list:
    exe = cfg.executable + (".exe" if system == "windows" else "")
    cmd = [sys.executable, "-m", "nuitka", "--standalone", "--assume-yes-for-downloads",
           "--follow-imports", "--nofollow-import-to=*.tests",
           "--nofollow-import-to=setuptools", "--nofollow-import-to=distutils",
           "--remove-output", f"--output-dir={out}", f"--output-filename={exe}"]
    if system == "windows":
        cmd.append(f"--windows-console-mode={'force' if console else 'disable'}")
    if family(system) == "macos" and not console:
        cmd += ["--macos-create-app-bundle", f"--macos-app-name={cfg.name}",
                f"--macos-app-version={version}", f"--macos-signed-app-name={cfg.bundle_id}"]
    if natives.hidden_extensions and importlib.util.find_spec("_cffi_backend"):
        cmd.append("--include-module=_cffi_backend")
    cmd += cfg.nuitka_for(system)
    cmd.append(cfg.entry)
    return cmd


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, symlinks=True)
    else:
        shutil.copy2(src, dest)


def copy_natives(natives, code_dir: Path, system: str) -> int:
    copied = 0
    for src, rel in natives.files:
        target = code_dir / rel
        if not target.exists():
            _copy(src, target)
            copied += 1
    if system == "windows" and natives.hidden_extensions:
        dll = natives_mod.python3_dll()
        if dll and not (code_dir / dll.name).exists():
            _copy(dll, code_dir / dll.name)
            copied += 1
    return copied


def copy_assets(cfg: Config, resource_dir: Path, code_dir: Path) -> None:
    linked = set()
    for asset in cfg.assets:
        rel = Path(asset.rstrip("/\\"))
        _copy(cfg.root / rel, resource_dir / rel)
        say(f"  {rel.as_posix()}")
        if resource_dir != code_dir:
            top = rel.parts[0]
            if top not in linked:
                link = code_dir / top
                if not link.exists():
                    link.symlink_to(os.path.relpath(resource_dir / top, code_dir))
                linked.add(top)


def finish_app(app: Path, cfg: Config, version: str) -> None:
    plist_path = app / "Contents" / "Info.plist"
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)
    info["CFBundleShortVersionString"] = version
    info["CFBundleVersion"] = version
    info["CFBundleDisplayName"] = cfg.name
    info["LSMinimumSystemVersion"] = cfg.macos_minimum
    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def build(cfg: Config, console: bool = False) -> Path:
    """Build for this system and return the build folder."""
    system = this_system()
    version = cfg.version()
    natives = natives_mod.find(cfg.native_packages, cfg.native_exclude, system)
    out = cfg.root / "build" / "nuitka"
    if out.exists():
        shutil.rmtree(out)
    dest = cfg.build_folder(system)
    if dest.exists():
        shutil.rmtree(dest)

    say(f"Building {cfg.name} {version} for {SPOKEN_SYSTEMS[system]}{', with a console' if console else ''}.")
    say(f"Found {natives.summary()} to add after Nuitka.")
    cmd = nuitka_command(cfg, system, version, console, natives, out)
    say("Starting Nuitka. This takes several minutes.")
    if subprocess.run(cmd, cwd=cfg.root).returncode != 0:
        raise BuildError("Nuitka failed. What it said is above.")

    apps = sorted(out.glob("*.app"))
    stem = Path(cfg.entry).stem
    if apps:
        app = dest / f"{cfg.name}.app"
        dest.mkdir(parents=True)
        shutil.move(str(apps[0]), str(app))
        code_dir = app / "Contents" / "MacOS"
        resource_dir = app / "Contents" / "Resources"
        resource_dir.mkdir(exist_ok=True)
    else:
        built = out / f"{stem}.dist"
        if not built.is_dir():
            raise BuildError(f"Nuitka finished, but there is no {built.name} folder in {out}.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(built), str(dest))
        app = None
        code_dir = resource_dir = dest

    copied = copy_natives(natives, code_dir, system)
    say(f"Added {copied} native files Nuitka could not see.")
    say("Copying assets:")
    copy_assets(cfg, resource_dir, code_dir)
    if app:
        say("Writing the version into the app, and signing it again.")
        finish_app(app, cfg, version)
        (dest / MAC_NOTE_NAME).write_text(MAC_NOTE.format(app=app.name), encoding="utf-8")
    shutil.rmtree(cfg.root / "build" / "nuitka", ignore_errors=True)
    say(f"The build is in {dest}.")
    return dest
