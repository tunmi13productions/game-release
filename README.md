# game-release

One build and release tool for every tunmi13productions Python game. Each game keeps only a release.json saying what is different about it, and a three-line release.py that never changes. Fix something here and every game gets the fix.

It builds with Nuitka for Windows, Linux, Mac with Apple Silicon, and Mac with an Intel processor. Your own computer builds its own system, WSL builds Linux from Windows, and GitHub's machines build all four for a release. The release flow and the Mac app follow Sixth Sense Reborn's releaser. The WSL build follows Kaskade's.

## Using it in a game

Run the game's release.py with the game's venv for a numbered menu, for example env\Scripts\python release.py. The choices are:

1. Build for this computer. Builds into dist, in a folder named after the archive and the system, and packs the archive beside it.
2. Build a console test build. Keeps a console window, so a startup error is shown. On a Mac this is a plain folder instead of an app.
3. Build the Linux release in WSL. From Windows only.
4. Release. Checks that everything is committed and pushed, then tags the version, like v0.2, and pushes the tag. GitHub then builds every system and publishes one release with all of them. A release is only published if every system built.
5. Check on GitHub's builds. Says how the latest builds went.
6. Test the GitHub build. Builds every system on GitHub and publishes nothing. The archives land on a hidden draft release called test-build, to download and try.
7. Check what would stop a build or a release.
8. Set up the game's venv. Makes it if needed, installs requirements.txt, and installs this tool. A local copy of this tool is installed editable, so editing it changes every game at once.
9. Set up WSL to build Linux. Once per WSL distro.

Each choice is also a command, like game-release build, game-release release or game-release check.

Nothing here moves or deletes a tag or a release that already exists, or replaces a file already on one.

## Adding a new game

In the game's folder, with the tool installed, run game-release init. It writes:

- release.json, filled in with guesses. Check the name, the version, and native_packages.
- .github/workflows/release.yml, about ten lines that call this repository's shared workflow.
- release.py, the three-line menu launcher.

Then run release.py and choose Set up the game's venv.

## release.json

Required:

- name: what players see, like Behind Closed Doors. The Mac app is called this.
- entry: the script the game starts from, like main.py.
- executable: the program's name, without .exe.
- archive: the archive's base name, like behind_closed_doors. A release's archives are named after it and the system: behind_closed_doors_windows.zip, behind_closed_doors_linux.tar.gz, behind_closed_doors_macos_arm64.tar.gz and behind_closed_doors_macos_x86_64.tar.gz. The game's files sit at the top of each archive, as your games have always shipped.
- version: where the version lives. Either a file whose first line is the version, or an object with file and pattern, where pattern is a regular expression with one group, like {"file": "main.py", "pattern": "^VERSION = \"([^\"]+)\""}.

Optional:

- assets: files and folders copied beside the program, like sounds and readme.txt. On a Mac they go in the app's Resources folder, with a link beside the program, so loading them relative to the executable still works.
- native_packages: packages that load native libraries by hand, which Nuitka cannot see. Every game lists its own, since not every game uses the same audio library. For example cyal, prism and _soundfile_data for a game on OpenAL with libsndfile, or sound_lib and prism for a game on BASS. Their libraries for the system being built are copied into the build at the same place they have in site-packages.
- licenses: how the libraries' licenses ship, which most open source licenses require. folder, the default, adds a licenses folder with one folder per library. file adds one licenses.txt beside the readme, with a heading for each library. off adds none. The libraries are Python itself, every package in native_packages, and every package in license_packages.
- license_packages: more packages whose licenses ship, that have no native files to bundle, like pygame.
- native_exclude: patterns of native files to leave out, matched against their path in site-packages, like sound_lib/lib/x86/*.
- nuitka_args: extra Nuitka arguments, under all, windows, linux, macos, or one exact system like macos-arm64.
- changelog: a changelog file. A release's notes are the lines under a heading that is the version, like 2.0 or v2.0:, up to the next version heading.
- archive_name: a different pattern for archive names, where {archive}, {system} and {version} are filled in. {archive}_{system} by default. {archive}_{version}_{system} would add the version.
- archive_folder: true puts everything inside one folder named archive, as Sixth Sense Reborn does. False by default.
- fetch: files kept out of the repository, like sounds, that a build downloads first. Each entry has a url, and either extract_to, a folder a zip is unpacked into, or save_as, a file name. A local build skips any that are already there, so your own copy is used. GitHub's machines start empty, so they always download. The fetch command downloads them again on purpose. For example: "fetch": [{"url": "https://games.tunmi13.com/assets/christmas_dash/sounds.zip", "extract_to": "sounds"}]
- tag_prefix: what goes before the version in a tag. v by default.
- python: the Python version GitHub builds with. 3.12 by default.
- systems: which of windows, linux, macos-arm64 and macos-x86_64 a release carries. All four by default.
- macos: bundle_id, like com.tunmi13.behindcloseddoors, and minimum, the oldest macOS the app opens on, 11.0 by default.
- venv: the game's venv folder. env by default.
- wsl: distro, Ubuntu-22.04 by default, and python, the Python to build with there.

## What a game needs to run on a Mac and Linux

- Load assets relative to the executable. A Mac app started from Finder starts in the root folder, not the game's. Changing to the executable's folder when compiled, like os.chdir(os.path.dirname(sys.executable)), is enough.
- Every native library it loads must have a Mac and Linux build. cyal, prism, soundfile and sound_lib all do.
- The first time, macOS may refuse to open a game that is not from the App Store. Every Mac archive carries a text file saying how to open it anyway.

## Things the tool handles that were bugs before

- Building with the wrong Python. A build checks the installed packages against the versions pinned in requirements.txt. A newer prism in the global Python once crashed a build at startup with No module named prism._prism_cffi.
- That prism module, and any compiled module in a folder that is not a package, is copied in, along with cffi's _cffi_backend and, on Windows, python3.dll, which it needs and Nuitka cannot see.
- A Linux wheel repaired by auditwheel keeps its libraries in a .libs folder beside the package, and that folder is copied too.

## Costs

GitHub gives a free account 2,000 build minutes a month for private repositories, and Mac minutes count ten times. A full release builds two Macs, so use Test the GitHub build when something changed in how a game builds, not before every release.

Private repositories also have a small storage allowance for the month, and workflow artifacts count against it, even ones kept for a day. Christmas Dash's builds filled it twice. So archives never go through artifacts at all. A tag makes a hidden draft release, each build uploads its archive straight onto it, and the draft is published only when every system's archive is there. If one system fails, the draft stays hidden, and re-running that one job finishes it. A test build uploads to a hidden draft release called test-build instead, which is never published. Each test build replaces the last, and you can download its archives from the repository's releases page to try.
