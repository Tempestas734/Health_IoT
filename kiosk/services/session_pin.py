from __future__ import annotations

from secrets import randbelow
from typing import Any

from django.core.cache import cache


PIN_SESSION_KEY = "session_pin"
PIN_LENGTH = 6
SNAPSHOT_TIMEOUT_SECONDS = 12 * 60 * 60


def normalize_session_pin(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    digits_only = "".join(character for character in str(value) if character.isdigit())
    if len(digits_only) != PIN_LENGTH:
        return None
    return digits_only


def _cache_key(session_pin: str) -> str:
    return f"professional-session:{session_pin}"


def generate_session_pin() -> str:
    return f"{randbelow(10**PIN_LENGTH):0{PIN_LENGTH}d}"


def create_unique_session_pin(*, max_attempts: int = 25) -> str:
    for _ in range(max_attempts):
        candidate = generate_session_pin()
        if cache.get(_cache_key(candidate)) is None:
            return candidate
    raise RuntimeError("Unable to generate a unique session PIN.")


def publish_session_snapshot(session_pin: str, snapshot: dict[str, Any]) -> None:
    cache.set(_cache_key(session_pin), snapshot, SNAPSHOT_TIMEOUT_SECONDS)


def get_session_snapshot(session_pin: str) -> dict[str, Any] | None:
    normalized_pin = normalize_session_pin(session_pin)
    if not normalized_pin:
        return None
    snapshot = cache.get(_cache_key(normalized_pin))
    return snapshot if isinstance(snapshot, dict) else None
