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


def _issue_tag(version: str) -> str:
    """`0.4.1` -> `ISSUE 04.1`: drop the leading `0.`, zero-pad the minor."""
    _, minor, patch = version.split(".")[:3]
    return f"ISSUE {int(minor):02d}.{patch}"


def _latest_released_version() -> str:
    """The newest versioned heading in the changelog, i.e. the last release."""
    changelog = (HOMEPAGE_DIR.parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert match is not None, "changelog has no versioned release heading"
    return match.group(1)


def test_release_labels_match_the_released_version(homepage: str) -> None:
    """The hero and install labels must advertise the current release.

    `docs/docs_site.md` requires both to be updated on each release, but
    nothing enforced it, so 0.10.0 was prepared with the page still
    advertising 0.9.2 (caught in review on #557).

    The labels track the released version, not `__version__`, because
    between releases `main` carries a `.devN` version that has never
    shipped -- advertising it would be wrong. On a `.dev` version the
    expected label therefore comes from the newest changelog release
    heading; on a final version it must equal `__version__` itself, which
    is what catches a release commit that forgot to update the page.
    """
    from canarchy import __version__

    if ".dev" in __version__:
        expected = _latest_released_version()
    else:
        expected = __version__
        assert expected == _latest_released_version(), (
            f"__version__ is {expected} but the newest changelog release is "
            f"{_latest_released_version()}; promote the [Unreleased] section"
        )

    assert f"canarchy v{expected}" in homepage, (
        f"install shell tag does not advertise {expected}; "
        "see docs/docs_site.md on updating the homepage on each release"
    )
    assert _issue_tag(expected) in homepage, (
        f"hero issue tag is not {_issue_tag(expected)!r}; "
        "see docs/docs_site.md on updating the homepage on each release"
    )


def test_issue_tag_convention_matches_shipped_releases() -> None:
    """Pin the padding rule against the labels real releases used."""
    assert _issue_tag("0.4.1") == "ISSUE 04.1"
    assert _issue_tag("0.7.0") == "ISSUE 07.0"
    assert _issue_tag("0.9.2") == "ISSUE 09.2"
    assert _issue_tag("0.10.0") == "ISSUE 10.0"
