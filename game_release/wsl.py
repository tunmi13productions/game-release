"""Builds the Linux release from Windows inside WSL, the way Kaskade does.

The game is copied into the WSL distro's own home folder, which builds far faster than
/mnt, and built there with a venv of its own that lasts between builds. The archive
comes back to the game's dist folder. Ubuntu 22.04 by default, since a Linux build only
runs on systems whose C library is at least as new as the one it was built on.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import Config
from .ui import say

EXCLUDES = [".git", "env", "venv", ".venv", "__pycache__", "build", "dist", "*.dist", "*.build",
            "*.zip", "*.tar.gz", "*.log", "nuitka-crash-report.xml"]

SETUP_SCRIPT = r"""set -e
PYTHON="$1"
sudo apt-get update
sudo apt-get install -y build-essential patchelf ccache rsync software-properties-common
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
fi
sudo apt-get install -y "$PYTHON" "$PYTHON-dev" "$PYTHON-venv"
echo
echo "WSL is ready to build."
"""


def wsl_path(path: Path) -> str:
    """D:\\a\\b becomes /mnt/d/a/b."""
    path = path.resolve()
    return f"/mnt/{path.drive[0].lower()}" + path.as_posix()[len(path.drive):]


def distro_installed(name: str) -> bool:
    try:
        listed = subprocess.run(["wsl", "-l", "-q"], capture_output=True).stdout
    except OSError:
        return False
    names = [n.strip() for n in listed.decode("utf-16-le", errors="ignore").splitlines() if n.strip()]
    return name in names


def _bash(cfg: Config, script: str, *args) -> int:
    return subprocess.run(["wsl", "-d", cfg.wsl_distro, "--", "bash", "-lc", script, "bash", *args]).returncode


def _check(cfg: Config) -> bool:
    if sys.platform != "win32":
        say("Building in WSL is for Windows. On Linux, choose Build for this computer.")
        return False
    if not distro_installed(cfg.wsl_distro):
        say(f"The WSL distro {cfg.wsl_distro} is not installed. Install it with:")
        say(f"  wsl --install -d {cfg.wsl_distro}")
        say("then choose Set up WSL from this menu.")
        return False
    return True


def setup(cfg: Config) -> bool:
    if not _check(cfg):
        return False
    say(f"Setting up {cfg.wsl_distro} to build. It will ask for your Linux password.")
    return _bash(cfg, SETUP_SCRIPT, cfg.wsl_python) == 0


def tool_source() -> str:
    """Where WSL installs this tool from: the local copy when there is one, so an
    unpushed change is used, or GitHub."""
    here = Path(__file__).resolve().parents[1]
    if (here / "pyproject.toml").is_file():
        return wsl_path(here)
    return "git+https://github.com/tunmi13productions/game-release@main"


def build_linux(cfg: Config, console: bool = False) -> bool:
    if not _check(cfg):
        return False
    home = f"~/game-builds/{cfg.archive}"
    excludes = " ".join(f"--exclude='{e}'" for e in EXCLUDES)
    script = f"""set -e
command -v rsync >/dev/null || {{ echo "WSL is not set up yet. Choose Set up WSL first."; exit 1; }}
mkdir -p {home}
echo "Copying the game into WSL."
rsync -a --delete {excludes} --exclude='.release-venv' '{wsl_path(cfg.root)}/' {home}/
cd {home}
if [ ! -x .release-venv/bin/python ]; then
    echo "Making a venv for building. This happens once."
    {cfg.wsl_python} -m venv .release-venv
fi
.release-venv/bin/python -m pip install --quiet --upgrade pip
if [ -f requirements.txt ]; then .release-venv/bin/python -m pip install --quiet -r requirements.txt; fi
.release-venv/bin/python -m pip install --quiet --force-reinstall --no-deps '{tool_source()}'
.release-venv/bin/python -m pip install --quiet nuitka ordered-set zstandard
.release-venv/bin/python -m game_release build {'--console' if console else ''}
mkdir -p '{wsl_path(cfg.root)}/dist'
cp dist/*-linux.tar.gz '{wsl_path(cfg.root)}/dist/'
"""
    say(f"Building the Linux release in {cfg.wsl_distro}.")
    if _bash(cfg, script) != 0:
        say("The Linux build in WSL failed. What it said is above.")
        return False
    say(f"The Linux archive is in {cfg.root / 'dist'}.")
    return True
