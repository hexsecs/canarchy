---
description: "Maintainer reference for CANarchy ecosystem listings, search-engine submission, and launch copy."
---

# Distribution and launch packet

Prepared for [issue #484](https://github.com/hexsecs/canarchy/issues/484).
Submission status and follow-up decisions belong on that issue. The text below
is draft material for maintainer review, not evidence that a submission occurred.
Recheck destination rules and the released version before sending.

## Project facts and destinations

CANarchy is a Python 3.12+ CLI-first CAN security research toolkit with JSON/JSONL
events, J1939 workflows, and an MCP server. It is licensed GPL-3.0-or-later.

| Purpose | Destination |
| --- | --- |
| Source and issues | <https://github.com/hexsecs/canarchy> |
| Try the tool | <https://pypi.org/project/canarchy/> |
| Homepage | <https://hexsecs.github.io/canarchy/> |
| Documentation | <https://hexsecs.github.io/canarchy/docs/> |
| Releases | <https://github.com/hexsecs/canarchy/releases> |

On 2026-09-06, PyPI reported version **0.9.2**. Launch copy for that version must
not advertise the guided-fuzz archive or other fixes still under `Unreleased`.

## A demo without CAN hardware

With [uv installed](https://docs.astral.sh/uv/getting-started/installation/), run
these commands in a POSIX shell. The version pin makes the example reproducible.

```bash
uvx --from canarchy==0.9.2 canarchy --version
CANARCHY_TRANSPORT_BACKEND=scaffold uvx --from canarchy==0.9.2 canarchy capture can0 --jsonl
```

The second command emits typed JSON events from deterministic synthetic traffic
and exits. Here `can0` is a scaffold channel name; no adapter or real CAN
interface is required. This demonstrates the output contract, not live vehicle
capture. For real adapters and protocol examples, link the documentation.

## Awesome lists

### Awesome Vehicle Security: already listed

The [Python section](https://github.com/jaredthecoder/awesome-vehicle-security#python)
already links `hexsecs/canarchy` (checked 2026-09-06). Do not submit a duplicate.
If a description refresh is useful, this is proposed replacement copy:

```markdown
- [CANarchy](https://github.com/hexsecs/canarchy) - CLI-first CAN security research toolkit with J1939 workflows, structured JSON events, and an MCP server.
```

Its [contribution rules](https://github.com/jaredthecoder/awesome-vehicle-security/blob/master/contributing.md)
require checking earlier suggestions, one suggestion per PR, a descriptive
commit/PR title, and a repository link in the commit body. New entries go at the
bottom of their category; an update should edit the existing entry in place.

### Awesome MCP Servers: candidate

Use [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
as a community listing candidate. Its [contribution rules](https://github.com/punkpeye/awesome-mcp-servers/blob/main/CONTRIBUTING.md)
call for one server per line, a relevant category, alphabetical ordering, and
formatting consistent with neighboring entries. The README had no CANarchy
entry on 2026-09-06; its Security section is a suitable target. Before opening
a PR, recheck the README and search open/closed PRs for `canarchy` and
`hexsecs/canarchy` to avoid duplicating an earlier suggestion.

Proposed entry (Python implementation, local server):

```markdown
- [hexsecs/canarchy](https://github.com/hexsecs/canarchy) 🐍 🏠 - Local MCP server for CAN capture analysis, J1939 workflows, and structured security research tools, backed by the CANarchy CLI.
```

## Official MCP registry

Proposed registry name: `io.github.hexsecs/canarchy`.

The [official quickstart](https://modelcontextprotocol.io/registry/quickstart)
describes GitHub namespace authentication and the publisher. The registry is
currently in preview. Prepare metadata with `mcp-publisher init`, review it,
then authenticate as the namespace owner with `mcp-publisher login github`.
Run `mcp-publisher publish` only when the release and metadata are ready.

The [PyPI ownership rules](https://modelcontextprotocol.io/registry/package-types#pypi-packages)
require this marker in the package description published on PyPI:

```html
<!-- mcp-name: io.github.hexsecs/canarchy -->
```

The 0.9.2 PyPI description did **not** contain that marker on 2026-09-06.
Adding it only to GitHub's README is insufficient: include it in a new package
release before registry submission. In the generated `server.json`, use the
chosen name, `registryType: pypi`, identifier `canarchy`, the actual published
version, and stdio transport. Configure and test package arguments so the client
runs `canarchy mcp serve`, not bare `canarchy`. Follow the current publisher
schema rather than copying an npm example. No registry manifest is installed
by this documentation change.

Proposed registry description:

> Analyze CAN traffic and J1939 protocols with structured tools for security research.

After publication, verify the entry through the registry and test installation
in an MCP client. Record its URL and tested version on #484. An accepted registry
entry does not guarantee inclusion in every downstream directory.

## Show HN draft

The [Show HN guidelines](https://news.ycombinator.com/showhn.html) ask for
something people can try and an author available to discuss it. Submit when
the maintainer can answer questions. Use the repository URL, whose README
includes installation and examples.

**Title:** Show HN: CANarchy – A CLI and MCP toolkit for CAN bus research

**URL:** <https://github.com/hexsecs/canarchy>

**Author comment draft:**

> I built CANarchy for CAN bus security research and protocol exploration.
> The CLI is the main interface; commands emit structured events for scripts,
> and an MCP server exposes research workflows to compatible clients.
>
> You can try the event stream without CAN hardware. Install uv, then run
> `CANARCHY_TRANSPORT_BACKEND=scaffold uvx --from canarchy==0.9.2 canarchy capture can0 --jsonl`
> in a POSIX shell. This uses synthetic traffic, so it shows the data format
> without connecting to a vehicle.
>
> The project includes J1939 workflows, DBC decoding, and capture analysis.
> It requires Python 3.12+ and is GPL-3.0-or-later. I'd welcome feedback on
> the CLI and event format, particularly from people building repeatable
> CAN analysis workflows.

## Release announcements

Follow the [release workflow](release.md) for packaging and verification.
GitHub release notes must contain the full versioned changelog section.
Use the short announcement below separately; replace the version and release
URL after the release exists, and include only features in that release.

> CANarchy VERSION is available: a CLI-first toolkit for CAN security research,
> with structured events, J1939 workflows, and MCP integration. Release notes:
> RELEASE_URL. Installation and a demo without hardware:
> https://github.com/hexsecs/canarchy#readme

## Search-engine submission

Both URLs returned HTTP 200 and parseable sitemap XML on 2026-09-06:

| Sitemap | Observed URLs |
| --- | ---: |
| <https://hexsecs.github.io/canarchy/sitemap.xml> | 1 |
| <https://hexsecs.github.io/canarchy/docs/sitemap.xml> | 41 |

Only host-root `robots.txt` is authoritative; this project's
`/canarchy/robots.txt` cannot control crawling for `hexsecs.github.io`.
See [Google's robots.txt guidance](https://developers.google.com/search/docs/crawling-indexing/robots/intro).
Direct submission helps discovery and reporting; it is not a prerequisite for
all discovery and does not guarantee indexing, as explained in
[Google's sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).

1. In [Google Search Console](https://search.google.com/search-console), select
   or create the URL-prefix property `https://hexsecs.github.io/canarchy/`.
   Follow the [ownership verification instructions](https://support.google.com/webmasters/answer/9008080).
   For HTML-tag verification, put the exact account-provided tag in the
   `<head>` of `src/homepage/index.html`, deploy, verify the live source, and
   complete verification in Search Console. Retain the tag across deployments.
2. In that property's Sitemaps report, submit `sitemap.xml` and
   `docs/sitemap.xml`. Check their fetch status; inspect the homepage and a
   representative documentation URL if indexing needs investigation.
3. Add or select the site in [Bing Webmaster Tools](https://www.bing.com/webmasters/).
   Complete its offered ownership verification, then submit both full URLs
   through [Sitemaps](https://www.bing.com/webmasters/help/sitemaps-3b5cf6ed).
4. Record submission dates and fetch outcomes on #484. Recheck errors after
   processing; submission and successful fetching are separate from indexing.

Verification requires the owner's account and its generated token. No token
is fabricated here, and no search-engine or external community submission is
performed by this packet.
