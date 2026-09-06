"""Every user-facing docs page carries its own meta description.

`mkdocs-material` falls back to the site-wide `site_description` for any page
without `description:` front matter, so a page added without one silently ships
the same meta description as every other page. Internal specification and
record pages are exempt: they are excluded from the sitemap and marked
noindex instead (see `overrides/`).
"""

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# Kept in step with overrides/main.html and overrides/sitemap.xml.
INTERNAL_PREFIXES = ("design/", "tests/", "benchmarks/")

MAX_DESCRIPTION_LENGTH = 200


def _user_facing_pages() -> list[pathlib.Path]:
    pages = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        relative = path.relative_to(DOCS_DIR).as_posix()
        if relative.startswith(INTERNAL_PREFIXES):
            continue
        pages.append(path)
    return pages


def _description(path: pathlib.Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    for line in text[4:end].splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def test_there_are_user_facing_pages() -> None:
    assert len(_user_facing_pages()) >= 40


@pytest.mark.parametrize(
    "page", _user_facing_pages(), ids=lambda p: p.relative_to(DOCS_DIR).as_posix()
)
def test_page_has_a_description(page: pathlib.Path) -> None:
    description = _description(page)
    assert description, (
        f"{page.relative_to(DOCS_DIR)} has no `description:` front matter, so it would "
        "inherit the site-wide meta description"
    )
    assert len(description) <= MAX_DESCRIPTION_LENGTH


def test_descriptions_are_unique() -> None:
    seen: dict[str, str] = {}
    duplicates = []
    for page in _user_facing_pages():
        description = _description(page)
        if description is None:
            continue
        name = page.relative_to(DOCS_DIR).as_posix()
        if description in seen:
            duplicates.append(f"{name} duplicates {seen[description]}")
        seen[description] = name
    assert not duplicates, duplicates


def test_internal_pages_are_excluded_from_the_crawl_surface() -> None:
    for override in ("main.html", "sitemap.xml"):
        text = (REPO_ROOT / "overrides" / override).read_text(encoding="utf-8")
        for prefix in INTERNAL_PREFIXES:
            assert f'"{prefix}"' in text, f"{override} does not cover {prefix}"
