# pragma-group.github.io

Static site for the [PRAGMA Group](https://github.com/pragma-group/main) —
Public Review and Advisory Group for Mailing Analysis.

The root of this site is a complete mirror of the
[WG21 (ISO C++ Standards Committee)](https://www.open-std.org/jtc1/sc22/wg21/)
website, browsable at
[pragma-group.github.io/jtc1/sc22/wg21/](https://pragma-group.github.io/jtc1/sc22/wg21/).

---

## What is here

- **`jtc1/sc22/wg21/`** — Full WG21 paper archive (1989–present): HTML, PDF, PS,
  and supporting files. Links are rewritten to relative paths for offline browsing.
- **`icons/`**, **`pics/`** — Page-requisite assets (Apache directory icons, ISO/IEC logos).
- **`index.html`** — Redirects to the WG21 index page.

## How it is maintained

A [GitHub Actions workflow](.github/workflows/update-mirror.yml) triggered by
manual dispatch runs an incremental crawl of `www.open-std.org`, skips
already-published immutable papers, and pushes only the changed files.
Immutable papers (those under a dated `YYYY/` subdirectory or matching the
`p####r#` / `n####` naming pattern) are never re-fetched once downloaded.

The crawler and link-rewriter scripts live in
[`.github/workflows/assets/`](.github/workflows/assets/).
See the [script README](.github/workflows/assets/README.md) for full usage
and design documentation.

## Why this mirror exists

PRAGMA evaluates WG21 proposals against disclosed principles and publishes
advisory assessments each mailing cycle. The mirror provides a stable,
self-contained reference for the agentic analysis pipeline and ensures paper
content remains accessible independent of upstream availability.

All governance and process documents for the group are in
[pragma-group/main](https://github.com/pragma-group/main).
