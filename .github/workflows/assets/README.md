# WG21 Mirror

A local mirror of the [WG21 (ISO C++ Standards Committee)](https://www.open-std.org/jtc1/sc22/wg21/)
website, built with a polite incremental crawler that skips re-downloading
already-published papers and rewrites links for offline browsing.

---

## Contents

```
wg21-mirror/
├── update-mirror.py          # Main crawler and link-rewriter (run this)
├── rewrite-links.py          # Standalone link-rewriting utility
├── requirements.txt          # Python dependency: requests>=2.28.0
├── crawl.log                 # Log from the initial full download
├── update-YYYY-MM-DD.log     # Logs from subsequent incremental runs
└── www.open-std.org/         # Mirrored content tree
    └── jtc1/sc22/wg21/
        └── docs/
            ├── papers/       # Papers from 1989 to present (by year)
            ├── cwg_index.html
            ├── lwg-index.html
            └── ...
```

**Mirror statistics (initial download, 2026-03-02):**

| Extension | Count |
|-----------|-------|
| `.html` | 5,876 |
| `.pdf` | 5,073 |
| `.htm` | 420 |
| `.ps` | 300 |
| `.asc` | 258 |
| `.txt` | 55 |
| `.md` | 39 |
| `.css` | 11 |
| `.gif` / `.png` | 11 |
| `.zip` | 6 |
| **Total** | **~12,200** |

Disk usage: ~3.2 GB. Papers span 1989–present.

**What is excluded:**

- `/jtc1/sc22/wg21/docs/mailings/` — password-protected member mailings
- `/jtc1/sc22/wg21/prot/` — password-protected area
- `.tar.gz`, `.tar`, `.bz2`, `.xz`, `.tgz`, `.tar.z` — large source archives
- HTML pages, PDFs, and documents from sibling working groups (wg14, wg15,
  sc22 root, etc.) — only page-requisite images and CSS from outside the
  WG21 subtree are fetched

---

## Prerequisites

Python 3.8+ and one dependency:

```bash
pip install -r requirements.txt
# or: pip install requests
```

---

## Usage

### Incremental update (typical use)

Re-fetches all non-paper pages (index files, issues lists, standards) and
skips already-published immutable papers:

```bash
python update-mirror.py \
  --mirror-dir ~/wg21-mirror \
  --threads 3 \
  --wait 0.5 \
  2>update-$(date +%F).log
```

On first run (empty mirror directory), this performs a full download. On
subsequent runs it is an incremental update: only non-paper HTML pages are
re-fetched; paper files that already exist are skipped entirely.

### GitHub Actions

```yaml
- name: Update WG21 mirror
  run: |
    pip install requests
    python update-mirror.py \
      --mirror-dir ${{ github.workspace }}/wg21-mirror \
      --threads 3 \
      --wait 0.5 \
      2>update-$(date +%F).log
```

The script exits with code 1 if any fetch or write error occurs, so CI will
fail loudly on network or disk problems. All diagnostic output goes to
stderr so GitHub Actions' log capture picks it up automatically.

### Standalone link rewrite (manual use)

`rewrite-links.py` is also embedded inside `update-mirror.py` and runs
automatically after every fetch. Use it standalone to re-process files
without re-downloading:

```bash
find ~/wg21-mirror -name "*.html" | python rewrite-links.py --mirror-dir ~/wg21-mirror
```

---

## Script reference

### `update-mirror.py`

The main script. Runs two phases:

**Phase 1 — Crawl and fetch**

A breadth-first crawler using `N` worker threads (`--threads`, default 3).
Each worker thread shares a queue of `(url, follow_links)` items.

- Starts at `https://www.open-std.org/jtc1/sc22/wg21/`
- Follows HTML links within the WG21 subtree (`follow=True`)
- Downloads but does not follow links to page-requisite resources outside
  the WG21 subtree (images, CSS) — `follow=False`
- Skips links to sibling working groups (wg14, wg15, etc.) entirely
- Applies a polite wait of `--wait` seconds (default 0.5 s) with a ×1–2
  random jitter between requests
- Skips immutable papers that already exist locally (see below)
- Saves files under `MIRROR_DIR/www.open-std.org/...` mirroring the URL path

**Phase 2 — Link rewriting**

After fetching, every HTML file downloaded in this run is processed by a
pool of `(cpu_count − 1)` worker processes that rewrite absolute
`https://www.open-std.org/...` links to relative paths, making the mirror
browsable offline via `file://`.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--mirror-dir DIR` | `~/wg21-mirror` | Root directory of the local mirror |
| `--threads N` | `3` | Parallel download threads (1–10) |
| `--wait SECS` | `0.5` | Base wait between requests in seconds |
| `--no-random-wait` | off | Disable ×1–2 random jitter on the wait |
| `--verbose` / `-v` | off | Show DEBUG-level log lines |

**Exit codes:** 0 = success, 1 = one or more fetch/write errors.

### `rewrite-links.py`

Standalone link rewriter. Reads file paths from stdin and rewrites every
`https://www.open-std.org/...` link in `href`, `src`, `action`, and `data`
attributes to a relative path.

- Memory: flat — each of the `(cpu_count − 1)` worker processes holds
  exactly one file at a time
- Only files containing at least one rewritable link are written back
- Files not found on disk are reported as `MISSING` (error)

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--mirror-dir DIR` | `~/wg21-mirror` | Root directory of the local mirror |
| `--verbose` / `-v` | off | Print per-file REWRITTEN/UNCHANGED to stdout |

**Exit codes:** 0 = success, 1 = rewrite errors, 2 = bad arguments or no stdin.

---

## Key design decisions

### Paper immutability

Once a WG21 paper is published, it never changes. A file is treated as an
immutable paper if:

1. It lives under `/docs/papers/YYYY/` (a dated year directory), **and** is
   not a known mutable file (`index.html`, `lwg-index.html`, `sd-*.html`, etc.)
2. **Or** its filename stem matches the WG21 naming pattern:
   `p####r#`, `d####r#`, `n####` (with optional letter suffixes)

On incremental runs, immutable papers that already exist locally are skipped
entirely — no HTTP request is made. This is the single biggest bandwidth
optimisation: in the first full crawl, 2,617 papers were already skipped on
first encounter by this logic (redirects that resolved to already-downloaded
files).

### No `If-Modified-Since`

The script does not send `If-Modified-Since` headers. Git resets file
modification times on checkout, so mtimes cannot be trusted across
machines or CI environments. The WG21 Apache server also ignores
`If-Modified-Since` for HTML responses. Conditional GET is therefore
unreliable; the paper-immutability optimisation is used instead for the
large-content subset where it matters.

### Redirect handling

When a URL without a trailing slash (e.g. `/jtc1/sc22/wg21`) redirects to
the slash version (`/jtc1/sc22/wg21/`), the local path is computed from the
**final** URL (`resp.url`) rather than the requested URL. This prevents a
file/directory name collision on all operating systems. The redirect target's
canonical URL is also added to the visited set to prevent a double-fetch.

### Out-of-scope domains

Links from WG21 pages to sibling working groups (wg14, wg15, etc.) and to
the sc22 root are silently skipped: only page-requisite resource files (`.gif`,
`.png`, `.jpg`, `.css`, `.js`, `.svg`, `.ico`) from outside the WG21 subtree
are downloaded. This prevents out-of-scope content and avoids Windows
path-collision errors (`WinError 183`) from no-slash/slash redirect cycles
on directories with case-insensitive names.

---

## Log files

All output goes to stderr. Redirect to a file to preserve the log:

```bash
python update-mirror.py ... 2>update-2026-03-02.log
```

**Log levels:**

| Level | Meaning |
|-------|---------|
| `INFO 200 URL` | File downloaded successfully |
| `INFO SKIP [paper]` | Immutable paper already on disk (verbose only) |
| `INFO Phase 1 done ...` | Phase 1 summary: counts of HTML, other, skipped, errors |
| `INFO Phase 2: rewriting ...` | Link rewriting started |
| `INFO Done. Fetch: Xs, Rewrite: Xs` | Timing summary |
| `WARNING NET ERR URL` | Network error (connection reset, timeout) |
| `WARNING Retrying ...` | urllib3 retry on stale connection (benign) |
| `WARNING Completed with N error(s)` | Run finished with errors — re-run to retry |
| `ERROR WRITE FAIL` | File could not be saved to disk |
| `ERROR MKDIR FAIL` | Parent directory could not be created |

**Kept logs:**

| File | Description |
|------|-------------|
| `crawl.log` | Initial full download (2026-03-02, 9303 s / ~2 h 35 m, 12,279 files fetched) |
| `update-2026-03-02.log` | First incremental update (2026-03-02, 170 s / ~3 min, 27 HTML + 24 other, 501 papers skipped, 0 errors) |
| `update-YYYY-MM-DD.log` | Subsequent incremental update runs |
