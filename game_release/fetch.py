"""Downloads files a game keeps out of its repository, like its sounds, before a build.

Each entry in fetch in release.json has a url, and either extract_to, a folder a zip is
unpacked into, or save_as, a file name. A destination that is already there is left
alone, so a local build uses the files you already have, and GitHub's machines, which
start empty, download them. Christmas Dash's sounds are hosted this way, because every
.ogg is kept out of its repository.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .config import Config
from .ui import say


def fetch(cfg: Config, force: bool = False) -> bool:
    for item in cfg.fetch:
        url = item["url"]
        target = item.get("extract_to") or item.get("save_as")
        dest = cfg.root / target
        if dest.exists() and not force:
            say(f"{target} is already here, so it was not downloaded.")
            continue
        say(f"Downloading {target} from {url}.")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "game-release"})
            with urllib.request.urlopen(request, timeout=300) as response:
                data = response.read()
        except OSError as error:
            say(f"The download failed: {error}")
            return False
        say(f"Downloaded {len(data) / (1 << 20):.0f} megabytes.")
        if "extract_to" in item:
            staging = Path(tempfile.mkdtemp(dir=cfg.root))
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    archive.extractall(staging)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(staging), str(dest))
            except (zipfile.BadZipFile, OSError) as error:
                shutil.rmtree(staging, ignore_errors=True)
                say(f"The download is not a zip that could be unpacked: {error}")
                return False
            say(f"Unpacked {sum(1 for p in dest.rglob('*') if p.is_file())} files into {target}.")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    return True
