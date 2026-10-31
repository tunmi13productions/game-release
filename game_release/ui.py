"""Plain output for a screen reader: one short line at a time, no symbols or tables."""
from __future__ import annotations


def say(text: str = "") -> None:
    print(text, flush=True)


def ask(question: str) -> bool:
    """A Y or N question. Anything but Y is no, and so is no keyboard at all."""
    try:
        return input(f"{question} (Y/N): ").strip().upper() == "Y"
    except EOFError:
        return False


def problems(heading: str, found: list) -> bool:
    """Say a list of problems under a heading. True when there were none."""
    if not found:
        return True
    say(heading)
    for line in found:
        say("  " + line)
    return False
