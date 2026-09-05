"""The published homepage must be readable without executing JavaScript.

Crawlers that do not run scripts -- and every social scraper -- see only the
HTML payload, so the landing page is plain HTML and CSS with no build step and
no browser-side framework or compiler.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HOMEPAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "homepage"


@pytest.fixture(scope="module")
def homepage() -> str:
    return (HOMEPAGE_DIR / "index.html").read_text(encoding="utf-8")


def _strip_scripts(html: str) -> str:
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)


def test_homepage_ships_a_stylesheet() -> None:
    assert (HOMEPAGE_DIR / "site.css").is_file()


def test_no_browser_side_compiler_or_framework(homepage: str) -> None:
    assert not re.search(r"babel", homepage, re.IGNORECASE)
    assert not re.search(r"react(-dom)?\.(development|production)", homepage, re.IGNORECASE)
    assert 'type="text/babel"' not in homepage


@pytest.mark.parametrize(
    "phrase",
    [
        "CANarchy",
        "J1939",
        "stream-first runtime",
        "MCP SERVER",
        "pip install canarchy",
        "Provider-backed DBC",
    ],
)
def test_key_content_is_in_the_initial_payload(homepage: str, phrase: str) -> None:
    assert phrase in _strip_scripts(homepage)


def test_headings_and_links_are_static_markup(homepage: str) -> None:
    body = _strip_scripts(homepage)
    assert "<h1" in body
    assert body.count("<h2") >= 7
    assert 'href="/canarchy/docs/getting_started"' in body
    assert 'href="https://github.com/hexsecs/canarchy"' in body


def test_empty_react_mount_point_is_gone(homepage: str) -> None:
    assert 'id="root"' not in homepage


def test_metadata_is_preserved(homepage: str) -> None:
    assert '<link rel="canonical" href="https://hexsecs.github.io/canarchy/" />' in homepage
    assert 'property="og:image"' in homepage
    assert '"@type": "SoftwareApplication"' in homepage
