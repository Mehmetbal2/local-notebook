"""Resolve chat citations against the map that was in effect when an answer was written.

Every stored tool message carries a snapshot of the session's citation map. Earlier
versions did not persist the session's citation counter, so each new turn started
numbering again at ``citation_0`` and overwrote keys from previous turns. Merging all
snapshots into one map therefore resolves an old answer's ``[citation_3]`` to a later
turn's source — possibly from a different work. Resolving per turn avoids that.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


def citation_identity(meta: Mapping[str, Any]) -> tuple:
    """A key that is the same for two citations exactly when they point at the same source passage."""
    kind = meta.get("type") or ("web" if meta.get("url") and not meta.get("file_name") else "segment")
    if kind == "web":
        return ("web", meta.get("url") or meta.get("title"))
    if meta.get("image_id") or kind == "image":
        return ("image", meta.get("file_id"), meta.get("image_id") or meta.get("image_index"))
    return ("segment", meta.get("file_id"), meta.get("segment_id"))


def turn_citation_maps(messages: Sequence[Mapping[str, Any]]) -> list[dict]:
    """For each message, the citation map as it stood at the end of that message's turn.

    A turn is a user message and everything after it up to the next user message.
    ``messages`` are dicts with ``role`` and, for tool messages, ``citations`` (a dict).
    """
    result: list[dict] = [{} for _ in messages]
    cumulative: dict = {}
    turn_start = 0

    def close_turn(end: int) -> None:
        snapshot = dict(cumulative)
        for index in range(turn_start, end):
            result[index] = snapshot

    for index, message in enumerate(messages):
        if message.get("role") == "user" and index > turn_start:
            close_turn(index)
            turn_start = index
        if message.get("role") == "tool" and isinstance(message.get("citations"), dict):
            cumulative.update(message["citations"])
    close_turn(len(messages))
    return result


def max_citation_index(keys: Iterable[str]) -> int:
    """Highest N among keys of the form ``citation_N`` (-1 when there are none)."""
    highest = -1
    for key in keys:
        if isinstance(key, str) and key.startswith("citation_"):
            suffix = key[len("citation_"):]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return highest
