"""The game-release command and its menu.

With nothing after it, it offers a numbered menu and waits for Enter at the end, so you
can hear how it went. Each menu choice is also a command:

    build             build for this computer and pack the archive
    build --console   a test build that keeps a console window, to see why a game will not start
    build --no-archive  build without packing
    linux             build the Linux release in WSL, from Windows
    setup-wsl         set up the WSL distro to build, once
    release           tag the version and push it, so GitHub builds and publishes every system
    test-workflow     have GitHub build every system and publish nothing
    status            hear how GitHub's latest builds went
    check             say what would stop a build or a release
    setup             make the game's venv and install everything into it
    init              write release.json, the workflow and release.py for a new game

    fetch             download what fetch in release.json names again, like hosted sounds

The workflow runs ci-plan, ci-draft, ci-build, ci-upload and ci-release; they are not for typing.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import build as build_mod
from . import fetch, package, project, release, wsl
from .config import SPOKEN_SYSTEMS, ConfigError, load, this_system
from .ui import ask, problems, say


def do_build(cfg, console=False, archive=True) -> bool:
    if not fetch.fetch(cfg):
        return False
    if not problems("The build cannot start:", build_mod.problems(cfg)):
        return False
    mismatched = build_mod.requirement_mismatches(cfg)
    if mismatched:
        problems("This Python's packages do not match requirements.txt:", mismatched)
        say("A build with the wrong versions can fail on players' computers. Use the game's venv.")
        if not ask("Build anyway"):
            return False
    try:
        folder = build_mod.build(cfg, console=console)
    except (build_mod.BuildError, OSError) as error:
        say(f"The build failed: {error}")
        return False
    if archive and not console:
        package.pack(folder, cfg.root / "dist" / cfg.archive_name(cfg.version(), this_system()),
                     cfg.archive if cfg.archive_folder else None)
    return True


def do_check(cfg) -> None:
    system = this_system()
    say(f"{cfg.name}, version {cfg.version()}, released as {cfg.tag()}.")
    say(f"This computer builds for {SPOKEN_SYSTEMS.get(system, 'nothing')}.")
    ok = problems("A build here would stop because:", build_mod.problems(cfg))
    ok = problems("These packages do not match requirements.txt:", build_mod.requirement_mismatches(cfg)) and ok
    ok = problems("A release would stop because:", release.readiness(cfg, cfg.tag())) and ok
    if ok:
        say("Nothing is in the way of a build or a release.")


MENU = [
    ("Build for this computer", lambda cfg: do_build(cfg)),
    ("Build a console test build, to see startup errors", lambda cfg: do_build(cfg, console=True)),
    ("Build the Linux release in WSL", lambda cfg: wsl.build_linux(cfg)),
    ("Release: tag this version, and GitHub builds and publishes every system", release.tag_release),
    ("Check on GitHub's builds", release.status),
    ("Test the GitHub build, publishing nothing", release.test_workflow),
    ("Check what would stop a build or a release", do_check),
    ("Set up the game's venv", project.setup_venv),
    ("Set up WSL to build Linux", wsl.setup),
]


def menu(cfg) -> None:
    say(f"{cfg.name} {cfg.version()}. Choose by number, or press Enter to leave.")
    for number, (label, _) in enumerate(MENU, 1):
        say(f"{number}. {label}")
    try:
        choice = input("Choice: ").strip()
    except EOFError:
        return
    if not choice:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
        say("That is not one of the choices.")
        return
    label, action = MENU[int(choice) - 1]
    say(label + ".")
    action(cfg)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="game-release", description="Build and release a game.")
    sub = parser.add_subparsers(dest="command")
    b = sub.add_parser("build")
    b.add_argument("--console", action="store_true")
    b.add_argument("--no-archive", action="store_true")
    li = sub.add_parser("linux")
    li.add_argument("--console", action="store_true")
    for name in ("setup-wsl", "release", "test-workflow", "status", "check", "setup", "init", "ci-plan",
                 "fetch"):
        sub.add_parser(name)
    sub.add_parser("ci-build").add_argument("tag")
    for name in ("ci-draft", "ci-upload", "ci-release"):
        p = sub.add_parser(name)
        p.add_argument("tag")
        p.add_argument("--test", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "init":
        project.init(Path.cwd())
        return
    try:
        cfg = load()
    except ConfigError as error:
        say(str(error))
        sys.exit(1)
    os.chdir(cfg.root)

    if args.command is None:
        try:
            menu(cfg)
        except ConfigError as error:
            say(str(error))
        try:
            input("Press Enter to close.")
        except EOFError:
            pass
        return
    actions = {
        "build": lambda: do_build(cfg, args.console, not args.no_archive),
        "linux": lambda: wsl.build_linux(cfg, args.console),
        "setup-wsl": lambda: wsl.setup(cfg),
        "release": lambda: release.tag_release(cfg),
        "test-workflow": lambda: release.test_workflow(cfg),
        "status": lambda: release.status(cfg) or True,
        "check": lambda: do_check(cfg) or True,
        "setup": lambda: project.setup_venv(cfg),
        "ci-plan": lambda: release.ci_plan(cfg) == 0,
        "fetch": lambda: fetch.fetch(cfg, force=True),
        "ci-build": lambda: release.ci_build(cfg, args.tag) == 0,
        "ci-draft": lambda: release.ci_draft(cfg, args.tag, args.test) == 0,
        "ci-upload": lambda: release.ci_upload(cfg, args.tag, args.test) == 0,
        "ci-release": lambda: release.ci_release(cfg, args.tag, args.test) == 0,
    }
    try:
        ok = actions[args.command]()
    except ConfigError as error:
        say(str(error))
        ok = False
    sys.exit(0 if ok else 1)
