"""
Text handling for player commands.

Lives on its own because both the command parser and the cabinet router need
it, and importing one from the other closed a cycle: whichever module was
imported first left the other half-initialised.
"""

from __future__ import annotations

#: Uzbek latin uses several apostrophe glyphs interchangeably (o‘, o’, o`).
#: A typed command must match regardless of which one the keyboard produced.
_APOSTROPHES = ("‘", "’", "`", "´")


def normalize(text: str) -> str:
    lowered = text.lower()
    for glyph in _APOSTROPHES:
        lowered = lowered.replace(glyph, "'")
    return lowered.strip()
