"""Helpers for comma.ai commaCarSegments dataset manifests and LFS URLs."""

from __future__ import annotations

import os
from typing import Any

import requests

from canarchy.dataset_provider import DatasetError


DEFAULT_REPO = "https://huggingface.co/datasets/commaai/commaCarSegments"
DEFAULT_BRANCH = "main"


def repo_url() -> str:
    return os.environ.get("COMMA_CAR_SEGMENTS_REPO", DEFAULT_REPO).rstrip("/")


def branch() -> str:
    return os.environ.get("COMMA_CAR_SEGMENTS_BRANCH", DEFAULT_BRANCH)


def raw_url(path: str) -> str:
    return f"{repo_url()}/raw/{branch()}/{path.lstrip('/')}"


def fetch_database() -> dict[str, list[str]]:
    """Fetch commaCarSegments database.json from the configured repo."""
    url = raw_url("database.json")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise DatasetError(
            code="COMMA_SEGMENTS_MANIFEST_UNAVAILABLE",
            message="Failed to fetch commaCarSegments database.json.",
            hint="Check network access, HuggingFace availability, and COMMA_CAR_SEGMENTS_REPO/BRANCH.",
        ) from exc
    if not isinstance(data, dict):
        raise DatasetError(
            code="COMMA_SEGMENTS_MANIFEST_MALFORMED",
            message="commaCarSegments database.json did not contain a platform mapping.",
            hint="Refresh from the upstream dataset or report an upstream format change.",
        )
    return {str(platform): list(routes) for platform, routes in data.items() if isinstance(routes, list)}


def segment_entries(
    *, platform: str | None = None, limit: int | None = None, database: dict[str, list[str]] | None = None
) -> list[dict[str, Any]]:
    """Return stable replay file entries for commaCarSegments."""
    db = database if database is not None else fetch_database()
    platforms = [platform] if platform else sorted(db)
    entries: list[dict[str, Any]] = []
    for platform_name in platforms:
        routes = db.get(platform_name)
        if routes is None:
            raise DatasetError(
                code="COMMA_SEGMENTS_PLATFORM_NOT_FOUND",
                message=f"commaCarSegments platform '{platform_name}' was not found.",
                hint="Use `canarchy datasets replay catalog:comma-car-segments --list-files --json` to list available platforms.",
            )
        for route_ref in routes:
            route, segment = split_route_segment(str(route_ref))
            path = segment_path(route, segment)
            index = len(entries)
            entries.append(
                {
                    "id": str(index),
                    "name": f"{platform_name}:{route}/{segment}",
                    "platform": platform_name,
                    "route": route,
                    "segment": segment,
                    "format": "comma-rlog",
                    "size_bytes": None,
                    "source_url": raw_url(path),
                    "path": path,
                }
            )
            if limit is not None and len(entries) >= limit:
                return entries
    return entries


def split_route_segment(value: str) -> tuple[str, str]:
    """Parse database route refs into openpilot route and segment identifiers."""
    stripped = value.strip().rstrip("/")
    if stripped.endswith("/s"):
        stripped = stripped[:-2]
    parts = stripped.split("/")
    if len(parts) >= 3:
        return f"{parts[0]}|{parts[1]}", parts[2]
    if len(parts) == 2 and "|" in parts[0]:
        return parts[0], parts[1]
    raise DatasetError(
        code="COMMA_SEGMENTS_MANIFEST_MALFORMED",
        message=f"Could not parse commaCarSegments route reference '{value}'.",
        hint="Expected route references like '<dongle>/<route>/<segment>/s'.",
    )


def segment_path(route: str, segment: str) -> str:
    return f"segments/{route.replace('|', '/')}/{segment}/rlog.zst"


def resolve_lfs_url(pointer_or_file_url: str) -> str:
    """Resolve a HuggingFace raw URL to its LFS download URL when needed."""
    try:
        head = requests.head(pointer_or_file_url, timeout=30)
        content_type = head.headers.get("content-type", "")
        if "text/plain" not in content_type:
            return pointer_or_file_url
        pointer = requests.get(pointer_or_file_url, timeout=30)
        pointer.raise_for_status()
        oid, size = parse_lfs_pointer(pointer.text)
        return lfs_download_url(oid, int(size))
    except requests.RequestException as exc:
        raise DatasetError(
            code="COMMA_SEGMENTS_URL_UNAVAILABLE",
            message="Failed to resolve commaCarSegments LFS download URL.",
            hint="Check network access and HuggingFace LFS availability.",
        ) from exc


def parse_lfs_pointer(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    try:
        oid_key, oid_raw = lines[1].split(" ", 1)
        size_key, size = lines[2].split(" ", 1)
        hash_name, oid = oid_raw.split(":", 1)
    except (IndexError, ValueError) as exc:
        raise DatasetError(
            code="COMMA_SEGMENTS_LFS_POINTER_MALFORMED",
            message="HuggingFace LFS pointer for commaCarSegments was malformed.",
            hint="Retry later or report an upstream LFS pointer format change.",
        ) from exc
    if oid_key != "oid" or size_key != "size" or hash_name != "sha256":
        raise DatasetError(
            code="COMMA_SEGMENTS_LFS_POINTER_MALFORMED",
            message="HuggingFace LFS pointer for commaCarSegments had unexpected fields.",
            hint="Retry later or report an upstream LFS pointer format change.",
        )
    return oid, size


def lfs_download_url(oid: str, size: int) -> str:
    payload = {
        "operation": "download",
        "transfers": ["basic"],
        "objects": [{"oid": oid, "size": size}],
        "hash_algo": "sha256",
    }
    headers = {
        "Accept": "application/vnd.git-lfs+json",
        "Content-Type": "application/vnd.git-lfs+json",
    }
    response = requests.post(f"{repo_url()}.git/info/lfs/objects/batch", json=payload, headers=headers, timeout=30)
    try:
        response.raise_for_status()
        obj = response.json()["objects"][0]
        return obj["actions"]["download"]["href"]
    except (requests.RequestException, KeyError, IndexError) as exc:
        raise DatasetError(
            code="COMMA_SEGMENTS_URL_UNAVAILABLE",
            message="Failed to obtain commaCarSegments LFS download URL.",
            hint="Check HuggingFace LFS availability and dataset access permissions.",
        ) from exc
