"""Packs a build folder into the archive a release carries, as Sixth Sense Reborn does.

Windows gets a zip, which it opens with nothing installed. Linux and Mac get a gzipped
tar, which keeps the executable bit and symbolic links, and a Mac app needs both.
With archive_folder on in release.json, everything sits under one folder named after the
archive, as Sixth Sense Reborn does. It is off by default, as the games have always
shipped: the executable at the top of the zip. The archive is written under a
.part name and renamed only when whole, so a half-written one never looks finished.
"""
from __future__ import annotations

import os
import tarfile
import time
import zipfile
from pathlib import Path

from .ui import say

_STEPS = 4


def pack(build_dir: Path, archive: Path, top: str | None) -> Path:
    partial = archive.with_name(archive.name + ".part")
    for old in (archive, partial):
        if old.exists():
            old.unlink()
    tar = archive.name.endswith(".tar.gz")
    entries = []
    for dirpath, dirs, names in os.walk(build_dir):
        dirs.sort()
        # a link to a folder is not walked into: a tar keeps it as a link
        entries += [os.path.join(dirpath, d) for d in dirs if os.path.islink(os.path.join(dirpath, d))]
        entries += [os.path.join(dirpath, n) for n in sorted(names)]
    say(f"Packing {len(entries)} files into {archive.name}. Leave this open until it says it is done.")
    started = time.perf_counter()
    marks = {len(entries) * step // _STEPS for step in range(1, _STEPS)}
    if tar:
        box = tarfile.open(partial, "w:gz", compresslevel=6)

        def put(full, inside):
            box.add(full, inside, recursive=False)
    else:
        box = zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6)

        def put(full, inside):
            if not os.path.islink(full):
                box.write(full, inside)
    with box:
        for count, full in enumerate(entries, 1):
            inside = os.path.relpath(full, build_dir).replace(os.sep, "/")
            if top:
                inside = top + "/" + inside
            put(full, inside)
            if count in marks:
                say(f"  {count} of {len(entries)} files packed.")
    os.replace(partial, archive)
    say(f"The archive is done: {archive.name}, {archive.stat().st_size / (1 << 20):.0f} megabytes, "
        f"in {time.perf_counter() - started:.0f} seconds.")
    return archive
