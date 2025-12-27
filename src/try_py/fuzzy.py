"""Fuzzy matching and scoring algorithm."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


def calculate_score(
    try_dir: dict[str, Any],
    query_down: str,
    query_chars: list[str],
    ctime: datetime | None = None,
    mtime: datetime | None = None,
) -> float:
    """Calculate fuzzy match score for a directory.

    Scoring factors:
    - Date prefix bonus: +2.0 for YYYY-MM-DD- prefixed names
    - Character match: +1.0 per matched character
    - Word boundary bonus: +1.0 for matches at word boundaries
    - Proximity bonus: 2.0/sqrt(gap+1) for consecutive matches
    - Density multiplier: query_len / (last_pos + 1)
    - Length penalty: 10.0 / (text_len + 10.0)
    - Recency bonus: 3.0/sqrt(hours+1) based on mtime
    """
    text: str = try_dir["basename"]
    text_lower: str = try_dir["basename_down"]

    score = 0.0

    # Date-prefixed directory bonus
    if re.match(r"\d{4}-\d{2}-\d{2}-", text):
        score += 2.0

    # Fuzzy matching if query exists
    if query_down:
        query_len = len(query_chars)
        text_len = len(text_lower)

        last_pos = -1
        query_idx = 0
        i = 0

        while i < text_len:
            if query_idx >= query_len:
                break

            char = text_lower[i]

            if char == query_chars[query_idx]:
                # Base point
                score += 1.0

                # Word boundary bonus
                is_boundary = i == 0 or not text_lower[i - 1].isalnum()
                if is_boundary:
                    score += 1.0

                # Proximity bonus
                if last_pos >= 0:
                    gap = i - last_pos - 1
                    score += 2.0 / math.sqrt(gap + 1)

                last_pos = i
                query_idx += 1

            i += 1

        # All query chars must match
        if query_idx < query_len:
            return 0.0

        # Density bonus
        if last_pos >= 0:
            score *= query_len / (last_pos + 1)

        # Length penalty
        score *= 10.0 / (len(text) + 10.0)

    # Recency bonus based on mtime
    if mtime:
        now = datetime.now()
        hours_since = (now - mtime).total_seconds() / 3600.0
        score += 3.0 / math.sqrt(hours_since + 1)

    return score


def highlight_matches(text: str, query: str) -> str:
    """Wrap matched characters with highlight tokens."""
    if not query:
        return text

    result = ""
    text_lower = text.lower()
    query_lower = query.lower()
    query_chars = list(query_lower)
    query_index = 0

    for i, char in enumerate(text):
        if query_index < len(query_chars) and text_lower[i] == query_chars[query_index]:
            result += f"{{b}}{char}{{/b}}"
            query_index += 1
        else:
            result += char

    return result


def highlight_matches_for_selection(text: str, query: str, is_selected: bool) -> str:
    """Wrap matched characters with highlight tokens, selection-aware."""
    return highlight_matches(text, query)
