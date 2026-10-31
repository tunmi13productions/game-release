"""Tags a release and lets GitHub build and publish it, as Sixth Sense Reborn does.

On your computer, release checks that everything is committed and pushed, then tags the
commit with the game's version, like v0.2, and pushes the tag. The tag starts the
game's .github/workflows/release.yml, which builds every system in release.json on
GitHub's own machines, packs each one, and publishes one GitHub release carrying them
all. A release is only published when every system built, so a broken build never goes
out half done. Nothing here moves or deletes a tag or release that already exists, or
replaces a file already on one.

ci-plan, ci-build and ci-release are what the workflow runs. They are not for typing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import build as build_mod
from . import fetch, package
from .config import SPOKEN_SYSTEMS, SYSTEMS, Config, this_system
from .ui import ask, problems, say

WORKFLOW = "release.yml"
GH_FALLBACK = r"C:\Program Files\GitHub CLI\gh.exe"


def run(cmd, cwd, capture=True):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    except OSError as error:
        return False, str(error)
    out = ((result.stdout or "") + (result.stderr or "")).strip() if capture else ""
    return result.returncode == 0, out


def gh_path() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    return GH_FALLBACK if os.path.isfile(GH_FALLBACK) else None


def git(cfg, *args, capture=True):
    return run(["git", *args], cfg.root, capture)


def gh(cfg, *args, capture=True):
    path = gh_path()
    if not path:
        return False, "the GitHub CLI, gh, is not installed"
    return run([path, *args], cfg.root, capture)


# --- release notes -------------------------------------------------------------------

_HEADING = re.compile(r"^v?\d+(\.\d+)+\S*:?$", re.IGNORECASE)


def release_notes(cfg: Config, version: str) -> str:
    """The changelog lines under a heading that is this version, like 2.0 or v2.0:, up to
    the next version heading. A game with no changelog, or none for this version, gets a
    plain line instead."""
    if cfg.changelog:
        try:
            lines = (cfg.root / cfg.changelog).read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        names = {version, version + ":", "v" + version, "v" + version + ":"}
        for i, line in enumerate(lines):
            if line.strip().lower() in {n.lower() for n in names}:
                body = []
                for following in lines[i + 1:]:
                    if _HEADING.match(following.strip()):
                        break
                    body.append(following)
                text = "\n".join(body).strip()
                if text:
                    return text
    return f"{cfg.name} {version}."


# --- on your computer ----------------------------------------------------------------

def readiness(cfg: Config, tag: str) -> list:
    found = []
    if not (cfg.root / ".github" / "workflows" / WORKFLOW).is_file():
        found.append(f"there is no .github/workflows/{WORKFLOW}. Run game-release init to make it")
    ok, out = git(cfg, "status", "--porcelain")
    if not ok:
        found.append("this is not a git repository, or git is not installed")
        return found
    if out:
        found.append("there are changes that are not committed. Commit them first")
    ok, branch = git(cfg, "rev-parse", "--abbrev-ref", "HEAD")
    ok, upstream = git(cfg, "rev-parse", "--abbrev-ref", "@{u}")
    if not ok:
        found.append(f"the branch {branch} has never been pushed")
    else:
        git(cfg, "fetch", "--quiet")
        ok, ahead = git(cfg, "rev-list", "--count", f"{upstream}..HEAD")
        if ok and ahead != "0":
            found.append(f"{ahead} commits are not pushed. Push them first")
    ok, _ = git(cfg, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
    if ok:
        found.append(f"the tag {tag} already exists here. Raise the version first")
    ok, out = git(cfg, "ls-remote", "--tags", "origin", tag)
    if ok and out:
        found.append(f"the tag {tag} already exists on GitHub. Raise the version first")
    if not gh_path():
        found.append("the GitHub CLI, gh, is not installed. It is needed to follow the build")
    else:
        ok, _ = gh(cfg, "auth", "status")
        if not ok:
            found.append("the GitHub CLI is not signed in. Run gh auth login")
    return found


def tag_release(cfg: Config) -> bool:
    version = cfg.version()
    tag = cfg.tag(version)
    say(f"{cfg.name} version {version} would be released as the tag {tag}.")
    if not problems("It cannot be released yet:", readiness(cfg, tag)):
        return False
    say(f"GitHub will build: {', '.join(SPOKEN_SYSTEMS[s] for s in cfg.systems)}.")
    say("The notes will be:")
    for line in release_notes(cfg, version).splitlines()[:5]:
        say("  " + line)
    if not ask(f"Tag {tag} and push it, which starts the release"):
        say("Nothing was tagged.")
        return False
    ok, out = git(cfg, "tag", "-a", tag, "-m", f"{cfg.name} {version}")
    if not ok:
        say("The tag could not be made: " + out)
        return False
    ok, out = git(cfg, "push", "origin", tag)
    if not ok:
        say("The tag could not be pushed: " + out)
        say(f"It is still here. Push it with git push origin {tag}, or delete it with git tag -d {tag}.")
        return False
    say(f"{tag} is pushed. GitHub is building now, which takes about 15 to 30 minutes.")
    say("Choose Check on GitHub's builds from the menu to hear how it is going.")
    return True


def test_workflow(cfg: Config) -> bool:
    ok, branch = git(cfg, "rev-parse", "--abbrev-ref", "HEAD")
    say(f"This builds every system on GitHub from the pushed {branch} branch, and publishes nothing.")
    say("Mac builds use more of your GitHub minutes than the others.")
    if not ask("Start the test build"):
        return False
    ok, out = gh(cfg, "workflow", "run", WORKFLOW, "--ref", branch)
    say("Started. Choose Check on GitHub's builds to hear how it goes." if ok else "It could not start: " + out)
    return ok


def status(cfg: Config) -> None:
    ok, out = gh(cfg, "run", "list", "--workflow", WORKFLOW, "--limit", "5",
                 "--json", "displayTitle,status,conclusion,event,headBranch,createdAt,url")
    if not ok:
        say("GitHub's builds could not be read: " + out)
        return
    runs = json.loads(out or "[]")
    if not runs:
        say("There are no builds yet.")
        return
    for r in runs:
        state = r["conclusion"] or r["status"].replace("_", " ")
        kind = "release" if r["event"] == "push" else "test build"
        say(f"{r['headBranch']}, a {kind}, started {r['createdAt'][:16].replace('T', ' at ')}: {state}.")
    say("The newest one is at " + runs[0]["url"])


# --- on GitHub -----------------------------------------------------------------------

def ci_plan(cfg: Config) -> int:
    matrix = {"include": [{"system": s, "runner": SYSTEMS[s]["runner"]} for s in cfg.systems]}
    print("matrix=" + json.dumps(matrix))
    print("python=" + cfg.python)
    print("tag=" + cfg.tag())
    return 0


def ci_build(cfg: Config, tag: str) -> int:
    version = cfg.version_from_tag(tag)
    if version is None or version != cfg.version():
        say(f"The tag {tag} does not match the version in {cfg.version_file}, which is {cfg.version()}. Nothing was built.")
        return 1
    if not fetch.fetch(cfg):
        return 1
    if not problems("The build cannot start:", build_mod.problems(cfg)):
        return 1
    mismatched = build_mod.requirement_mismatches(cfg)
    if not problems("The installed packages do not match requirements.txt:", mismatched):
        return 1
    try:
        folder = build_mod.build(cfg)
    except Exception as error:
        say(f"The build failed: {error}")
        return 1
    system = this_system()
    package.pack(folder, cfg.root / "dist" / cfg.archive_name(version, system),
                 cfg.archive if cfg.archive_folder else None)
    return 0


# A tag's archives go straight onto the release, never through the workflow's artifact
# storage: in a private repository, artifacts count against the account's storage quota
# and release files do not, and Christmas Dash's old workflow once filled that quota.
# So ci-draft makes the release as a draft, which players cannot see, each build job
# uploads its own archive with ci-upload, and ci-release publishes the draft only once
# every system's archive is on it. A build that failed leaves the draft hidden, and
# re-running that one job adds the missing archive.

def _release_state(cfg: Config, tag: str):
    """(exists, is_draft, asset names) for the release of tag."""
    ok, out = gh(cfg, "release", "view", tag, "--json", "isDraft,assets")
    if not ok:
        return False, False, set()
    data = json.loads(out)
    return True, data["isDraft"], {a["name"] for a in data["assets"]}


def ci_draft(cfg: Config, tag: str) -> int:
    version = cfg.version_from_tag(tag)
    if version is None:
        say(f"{tag} is not a release tag for this game.")
        return 1
    exists, draft, _ = _release_state(cfg, tag)
    if exists:
        say(f"The release for {tag} is already there{' as a draft' if draft else ''}, so builds add what it lacks.")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(release_notes(cfg, version) + "\n")
        notes_file = f.name
    try:
        ok, _ = gh(cfg, "release", "create", tag, "--draft", "--verify-tag",
                   "--title", f"{cfg.name} {version}", "--notes-file", notes_file, capture=False)
    finally:
        os.remove(notes_file)
    say(f"A draft release for {tag} is ready for the builds." if ok else "The draft release could not be made.")
    return 0 if ok else 1


def ci_upload(cfg: Config, tag: str) -> int:
    version = cfg.version_from_tag(tag)
    name = cfg.archive_name(version, this_system())
    path = cfg.root / "dist" / name
    if not path.is_file():
        say(f"There is no {name} to upload.")
        return 1
    exists, _, have = _release_state(cfg, tag)
    if not exists:
        say(f"There is no release for {tag} to upload to.")
        return 1
    if name in have:
        say(f"{name} is already on the release, so it is left alone.")
        return 0
    ok, _ = gh(cfg, "release", "upload", tag, str(path), capture=False)
    say(f"{name} is on the release." if ok else f"{name} could not be uploaded.")
    return 0 if ok else 1


def ci_release(cfg: Config, tag: str, folder: str | None, dry_run: bool) -> int:
    version = cfg.version_from_tag(tag)
    if version is None:
        say(f"{tag} is not a release tag for this game.")
        return 1
    wanted = [cfg.archive_name(version, s) for s in cfg.systems]
    title = f"{cfg.name} {version}"
    if dry_run:
        found = {p.name: p for p in Path(folder).rglob("*") if p.is_file()} if folder else {}
        missing = [w for w in wanted if w not in found]
        if not problems(f"{len(missing)} archives are missing:", missing):
            return 1
        say(f"A test run publishes nothing. The tag {tag} would publish {title} with:")
        for w in wanted:
            say(f"  {w}, {found[w].stat().st_size / (1 << 20):.0f} megabytes")
        return 0
    exists, draft, have = _release_state(cfg, tag)
    if not exists:
        say(f"There is no release for {tag}.")
        return 1
    missing = [w for w in wanted if w not in have]
    if not problems(f"Nothing was published, and the release stays a hidden draft. {len(missing)} archives are missing:", missing):
        return 1
    if not draft:
        say(f"{title} was already published, with every archive.")
        return 0
    ok, _ = gh(cfg, "release", "edit", tag, "--draft=false", capture=False)
    say(f"{title} is published." if ok else "The release could not be published. What gh said is above.")
    return 0 if ok else 1
