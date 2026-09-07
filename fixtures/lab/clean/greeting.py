"""A tiny, deliberately boring module: nothing here should trip a linter or a type checker."""

from __future__ import annotations


def greeting(name: str) -> str:
    return f"Hello, {name}!"
