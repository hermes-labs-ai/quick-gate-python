"""Same shape as the clean fixture, with one real type error: greeting() returns int, not str."""

from __future__ import annotations


def greeting(name: str) -> str:
    return 42
