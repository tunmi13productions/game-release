"""Setting a game up: its venv, its release.json, its workflow and its release.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .config import CONFIG_NAME, SYSTEMS, Config
from .ui import ask, say

TOOL_REPO = "tunmi13productions/game-release"

# The whole of a game's workflow. Everything it does lives in the tool's own repository,
# so a fix there reaches every game without touching this file.
WORKFLOW_TEXT = f"""# Builds every system in release.json and publishes a release when a version tag is pushed.
# Run from the Actions page, or from release.py's Test the GitHub build, it builds and publishes nothing.
# Everything it does lives in {TOOL_REPO}, so this file never needs to change.
name: Release

on:
  push:
    tags: ['v*']
  workflow_dispatch:

concurrency:
  group: release-${{{{ github.ref }}}}
  cancel-in-progress: false

jobs:
  release:
    permissions:
      contents: write
    uses: {TOOL_REPO}/.github/workflows/build.yml@main
"""

SHIM_TEXT = '''r"""Builds and releases this game. Its settings are in release.json.

Run it with the game's venv, like env\\Scripts\\python release.py, for a menu.
The tool itself is game-release, shared by every game, so a fix to it reaches them all."""
from game_release.cli import main

main()
'''


def tool_source() -> str:
    here = Path(__file__).resolve().parents[1]
    return str(here) if (here / "pyproject.toml").is_file() else f"git+https://github.com/{TOOL_REPO}@main"


def venv_python(root: Path, venv: str) -> Path:
    folder = root / venv
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def setup_venv(cfg: Config) -> bool:
    """Make the game's venv if needed and install its requirements and this tool into it.
    The local copy of the tool is installed editable, so changing it changes every game."""
    python = venv_python(cfg.root, cfg.venv)
    if python.is_file() and subprocess.run([str(python), "-c", ""], capture_output=True).returncode != 0:
        say(f"The venv {cfg.venv} is broken. The Python it was made from is probably gone.")
        if not ask(f"Delete {cfg.venv} and make it again"):
            return False
        import shutil
        shutil.rmtree(cfg.root / cfg.venv)
    elif not python.is_file() and (cfg.root / cfg.venv).exists():
        say(f"{cfg.venv} is there but is not a venv for this system, so it was left alone. "
            "Set venv in release.json to another folder name.")
        return False
    if not python.is_file():
        say(f"Making the venv {cfg.venv} with {sys.executable}.")
        if subprocess.run([sys.executable, "-m", "venv", str(cfg.root / cfg.venv)]).returncode != 0:
            say("The venv could not be made.")
            return False
    steps = [[str(python), "-m", "pip", "install", "--upgrade", "pip"]]
    if (cfg.root / "requirements.txt").is_file():
        steps.append([str(python), "-m", "pip", "install", "-r", "requirements.txt"])
    source = tool_source()
    steps.append([str(python), "-m", "pip", "install", *(["-e", source] if Path(source).is_dir() else [source])])
    for step in steps:
        say("Running: " + " ".join(step[2:]))
        if subprocess.run(step, cwd=cfg.root).returncode != 0:
            say("That step failed. What pip said is above.")
            return False
    say(f"The venv is ready. Build with {python.relative_to(cfg.root)} release.py")
    return True


def guess_entry(root: Path) -> str:
    for name in ("main.py", "game.py", "app.py"):
        if (root / name).is_file():
            return name
    return "main.py"


def init(root: Path) -> bool:
    """Write release.json, the workflow and release.py for a game that has none."""
    config = root / CONFIG_NAME
    if config.exists():
        say(f"{CONFIG_NAME} is already here, so it was left alone.")
    else:
        slug = root.name.lower().replace("-", "_").replace(" ", "_")
        data = {
            "name": root.name.replace("-", " "),
            "entry": guess_entry(root),
            "executable": root.name.replace("-", "").replace(" ", ""),
            "archive": slug,
            "version": {"file": guess_entry(root), "pattern": "VERSION = \"([^\"]+)\""},
            "assets": [p for p in ("sounds", "readme.txt", "changelog.txt") if (root / p).exists()],
            "native_packages": [],
            "nuitka_args": {"all": [], "windows": [], "linux": [], "macos": []},
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "systems": list(SYSTEMS),
        }
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        say(f"Wrote {CONFIG_NAME}. Check its name, version and native_packages before building.")
    workflow = root / ".github" / "workflows" / "release.yml"
    if workflow.exists() and not ask(f"{workflow.relative_to(root)} is already there. Replace it"):
        say("The workflow was left alone.")
    else:
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(WORKFLOW_TEXT, encoding="utf-8")
        say(f"Wrote {workflow.relative_to(root)}.")
    shim = root / "release.py"
    if shim.exists() and shim.read_text(encoding="utf-8") != SHIM_TEXT:
        if not ask("release.py is already there. Replace it with the shared tool's"):
            say("release.py was left alone.")
            return True
    shim.write_text(SHIM_TEXT, encoding="utf-8")
    say("Wrote release.py.")
    return True
