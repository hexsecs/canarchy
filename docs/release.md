# Release Workflow

## Goal

This page describes how to prepare and publish a CANarchy release, with TestPyPI recommended before the first real PyPI publication and for any release workflow changes.

## Prerequisites

Before publishing, confirm:

* package metadata in `pyproject.toml` is complete and correct
* `src/canarchy/__init__.py` contains the intended release version
* `CHANGELOG.md` has an `Unreleased` section and the upcoming release is summarized clearly
* `README.md` renders correctly as the long project description

Publishing credentials:

* preferred: PyPI trusted publishing via GitHub Actions OIDC
* fallback: a scoped PyPI API token stored as a GitHub Actions secret

For the first public release, use TestPyPI first.

## Recommended Release Order

1. Update version metadata in `src/canarchy/__init__.py`.
2. Move relevant entries from `CHANGELOG.md` `Unreleased` into a new versioned release section.
3. Commit the release preparation changes.
4. Tag the release with `vX.Y.Z`.
5. Build and verify artifacts locally from the release version.
6. Publish to TestPyPI first if this is the first release or if the release workflow changed.
7. Publish to PyPI from the same release version or tag.
8. Create the GitHub release notes from the full versioned changelog section for `X.Y.Z`; do not summarize or shorten the release notes.
9. After the release is cut and the release artifacts are published, advance `src/canarchy/__init__.py` on `main` to the next development version in a follow-up commit.

## Development Version Naming

After cutting release `X.Y.Z`, `main` shall advance to `X.Y.(Z+1).dev0` in the follow-up commit that reopens development after the release artifacts are built and published, unless a different next-version target is explicitly planned and documented before or as part of the release.

Examples:

* after `0.4.0`, set `src/canarchy/__init__.py` to `0.4.1.dev0`
* after `1.2.3`, set `src/canarchy/__init__.py` to `1.2.4.dev0`

Rules:

* keep release tags on the stable version only, such as `v0.4.0`
* keep unreleased work on `main` on a `.devN` version string
* build and publish release artifacts from the stable release version, not from the post-release `.dev0` version
* update the version metadata in the same commit or immediate follow-up commit that reopens development on `main` after the release artifacts are published
* if the next planned release target is a minor or major bump instead of the next patch version, document that decision explicitly and set the `.dev0` version accordingly

## Local Verification

Build artifacts:

```bash
uv build
```

Check package metadata rendering:

```bash
uvx twine check dist/*
```

Verify the wheel installs and the entry point works:

```bash
tmpdir=$(mktemp -d)
uv venv "$tmpdir/.venv"
uv pip install --python "$tmpdir/.venv/bin/python" dist/*.whl
"$tmpdir/.venv/bin/canarchy" --version
```

Recommended additional checks:

```bash
uv run pytest
uv run --group docs mkdocs build --strict
```

## TestPyPI First-Publish Flow

Recommended for the first public release:

1. Publish the built artifacts to TestPyPI.
2. Create a clean virtual environment.
3. Install from TestPyPI.
4. Verify `canarchy --version` and a small representative command such as `canarchy config show --json`.
5. Only then publish the same release to PyPI.

## GitHub Actions Publish Workflow

The repository includes a manual GitHub Actions workflow at `.github/workflows/publish.yml`.

How to use it:

1. Open the `publish` workflow in GitHub Actions.
2. Run it manually with `repository=testpypi` for the first dry run.
3. Verify the published package from TestPyPI.
4. Run it again with `repository=pypi` for the real publication.

Workflow behavior:

* builds sdist and wheel artifacts with `uv build`
* runs `twine check` before any upload
* publishes to separate GitHub environments for `testpypi` and `pypi`
* is structured for PyPI trusted publishing via GitHub OIDC

## Trusted Publishing

Preferred long-term setup:

* configure a PyPI project for CANarchy
* enable trusted publishing from the GitHub repository
* restrict publication to the intended release workflow and branch/tag conditions

If trusted publishing is not ready yet, use an API token with the narrowest possible scope and store it only in GitHub Actions secrets.

## Notes

* Release tags should match the package version exactly, prefixed with `v`.
* GitHub release notes should use the complete text from the matching `CHANGELOG.md` version section verbatim.
* If the release introduces breaking CLI or output-contract changes, bump the major version according to the documented SemVer policy.
* If publication metadata or workflow changes, repeat the TestPyPI path before the next real PyPI release.
