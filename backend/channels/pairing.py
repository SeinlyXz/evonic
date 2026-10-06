"""Pairing code generation and validation.

Generates uppercase alphanumeric pairing codes with a ``EVN-`` prefix, e.g.
``EVN-AB12``. The random payload uses an unambiguous character set (excludes
0/O and 1/I/L) to avoid visual mistyping.
"""
from __future__ import annotations

from typing import Optional

import random
import re

# Prefix that marks a pairing code in free text. Distinctive enough that
# ordinary chat ("Hi khodam", "thanks", ...) is never taken for a code.
_PREFIX = "EVN-"
# Number of random characters after the prefix.
_CODE_LEN = 4
# Unambiguous characters: removed 0, O, 1, I, L to prevent visual mistyping.
# This is a subset of the uppercase alphanumeric set [A-Z0-9].
_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Canonical form: EVN-XXXX (uppercase alphanumeric payload).
_PATTERN = re.compile(r"^EVN-[A-Z0-9]{%d}$" % _CODE_LEN)

# Finds an EVN-XXXX code embedded in arbitrary text. The hyphen is required and
# the match is anchored on word boundaries, so a word such as "EVNEWS" is not
# mistaken for a code.
_EXTRACT_RE = re.compile(r"\bEVN-([A-Z0-9]{%d})\b" % _CODE_LEN)


def generate_pair_code() -> str:
    """Generate a pairing code in canonical form, e.g. ``EVN-AB12``."""
    return _PREFIX + "".join(random.choices(_CHARS, k=_CODE_LEN))


def format_pair_code(raw: str) -> str:
    """Return the canonical, uppercase display form of a pairing code."""
    return raw.upper()


def validate_pair_code(code: Optional[str]) -> bool:
    """Check that *code* matches the canonical ``EVN-XXXX`` format."""
    return bool(code is not None and _PATTERN.match(code))


def extract_pair_code(text: Optional[str]) -> str | None:
    """Extract an ``EVN-XXXX`` pairing code from arbitrary text.

    Only codes carrying the ``EVN-`` prefix and an uppercase alphanumeric
    payload are recognised, so ordinary words are never treated as pairing
    attempts. Matching is case-insensitive; the result is normalised to
    uppercase and returned in canonical form (``EVN-XXXX``), or ``None`` when
    no code is present.
    """
    if not text or not isinstance(text, str):
        return None
    m = _EXTRACT_RE.search(text.upper())
    if not m:
        return None
    return _PREFIX + m.group(1)
