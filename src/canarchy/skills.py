"""Skill provider error types."""

from __future__ import annotations


class SkillError(Exception):
    def __init__(self, *, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
