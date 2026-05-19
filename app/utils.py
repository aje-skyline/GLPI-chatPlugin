"""Shared utilities for GLPI AI Gateway.

Single source of truth for agent-output sanitization so that crew_services.py
and main.py use identical logic and the function is only maintained in one place.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Agent output sanitizer ────────────────────────────────────────────────────

_AGENT_LINE_PATTERN = re.compile(
    r"^\s*(Thought|Action\s+Input|Action|Observation|I need to|I will|I should|"
    r"Let me|I'll|First,?\s+I|Now\s+I)\s*[:\-]",
    re.IGNORECASE,
)


def sanitize_agent_output(raw: str) -> str:
    """Remove leaked internal agent format (Thought/Action/Observation) from text.

    Single canonical implementation — imported by both ``crew_services`` and
    ``main`` so the logic never diverges between the two call-sites.

    Strategy (applied in order):
      1. If ``Final Answer:`` present → take only text after it.
      2. Drop all lines starting with internal agent keywords; also drop
         every subsequent line until the next blank line (entire "block").
      3. Strip whitespace.
      4. If result is empty → log a warning and return ``raw`` (better to
         show a dirty answer than no answer at all).

    Args:
        raw: Raw string from ``crew.kickoff()`` or any agent output.

    Returns:
        Clean string ready to display to the user.
    """
    if not raw:
        return raw

    text = raw.strip()

    # Strategy 1: take after 'Final Answer:' (case-insensitive)
    fa_match = re.search(r"(?i)final\s+answer\s*:", text)
    if fa_match:
        text = text[fa_match.end():].strip()

    # Strategy 2: drop lines starting with internal agent keywords and the
    # rest of their "block" (everything until the next blank line).
    lines = text.splitlines()
    clean_lines: list[str] = []
    skip_until_blank = False

    for line in lines:
        stripped = line.strip()

        if skip_until_blank:
            if stripped == "":
                skip_until_blank = False
            continue

        if _AGENT_LINE_PATTERN.match(stripped):
            skip_until_blank = True
            continue

        clean_lines.append(line)

    cleaned = "\n".join(clean_lines).strip()

    if not cleaned:
        logger.warning("sanitize_agent_output: cleaned output is empty, returning raw")
        return raw.strip()

    return cleaned