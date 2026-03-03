#!/usr/bin/env python3
"""
update-mirror.py — WG21 mirror incremental updater
====================================================

Usage
-----
    python update-mirror.py [options]

Options
-------
    --mirror-dir DIR   Root of the local mirror  (default: ~/wg21-mirror)
    --threads N        Parallel download threads, 1-10  (default: 3)
    --wait SECS        Base polite wait between requests  (default: 0.5)
    --no-random-wait   Disable x1-2 jitter on the wait time
    --verbose / -v     Show DEBUG-level log lines

Key behaviours
--------------
Paper immutability optimisation
    Any file under /docs/papers/YYYY/ (a year sub-directory) is treated as
    an immutable, published paper and is SKIPPED if it already exists locally.
    This avoids re-requesting thousands of unchanged PDFs, HTMLs and PS files
    on every run -- the single biggest source of redundant server traffic.

    Outside yearly paper directories, filenames whose stem matches the WG21
    standard naming conventions (p####r#, d####r#, n####) are also treated as
    immutable once they exist locally.

Non-paper files always re-fetched
    Index pages, issues lists, and standards documents are always re-fetched.
    If-Modified-Since is NOT used: file mtimes are reset by git checkout and
    cannot be trusted across machines, so timestamp-based conditional GETs
    would produce wrong 304 responses after a git pull on a different host.
    The WG21 Apache server ignores If-Modified-Since for HTML anyway.
    Non-paper PDFs/ZIPs are a small set (TR18015.pdf, standards drafts) and
    the cost of always re-downloading them is negligible.

Parallel link rewriting
    After fetching, every HTML file downloaded in this run is post-processed
    by a pool of (cpu_count - 1) worker processes that rewrite absolute
    https://www.open-std.org/... links to relative paths, so the mirror is
    browsable offline via file://.

Cross-platform
    Works on Ubuntu (primary target), macOS and Windows.
    Requires: pip install requests
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import platform
import re
import sys
import threading
import time
import random
from html.parser import HTMLParser
from pathlib import Path
from queue import Queue
from urllib.parse import urljoin, urlparse, unquote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("Missing dependency - run: pip install requests")

# ── constants ──────────────────────────────────────────────────────────────────

ORIGIN    = "https://www.open-std.org"
BASE_PATH = "/jtc1/sc22/wg21/"

EXCLUDE_PATHS = frozenset([
    "/jtc1/sc22/wg21/docs/mailings",
    "/jtc1/sc22/wg21/prot",
])

# Extensions whose archives are never useful to mirror
REJECT_SUFFIXES = frozenset([
    ".tar.gz", ".tar", ".bz2", ".xz", ".tgz", ".tar.z",
])

# Page-requisite resource extensions: the only types fetched when a link
# falls outside BASE_PATH.  HTML pages, PDFs, and other documents from
# sibling working groups (wg14, wg15, …) are excluded — they are outside
# the scope of this WG21 mirror and their no-slash/slash redirect cycle
# causes Windows path-collision errors (WinError 183).
_RESOURCE_SUFFIXES = frozenset([
    ".gif", ".png", ".jpg", ".jpeg", ".ico",
    ".css", ".js", ".svg", ".webp",
])

# Detects a YYYY year segment in the papers path, e.g. /docs/papers/2024/
_IN_PAPERS_YEAR = re.compile(r"/docs/papers/\d{4}/", re.ASCII)

# Filename-stem patterns for papers published outside a dated subdirectory.
# Covers: p3293r2  d2429r3  n4296  N0220R2  N0349a
_PAPER_STEM = re.compile(
    r"^(?:[pd]\d+r\d+|n\d+(?:[ra-z]\d*)?)$",
    re.IGNORECASE | re.ASCII,
)

# Known non-paper filenames that live inside year directories
_MUTABLE_NAMES = frozenset([
    "index.html", "index.htm",
    "lwg-index.html", "lwg-status.html", "lwg-toc.html",
    "sd-1.html", "sd-2.html",
])

USER_AGENT = (
    "WG21Mirror/2.0 (polite incremental crawler; "
    "contact: wg21mirror@cppalliance.org)"
)

# Link-rewriting regex used in _rewrite_worker (module-level for multiprocessing)
_LINK_RE = re.compile(
    r"(?P<attr>(?:href|src|action|data)=)"
    r"(?P<q>[\"'])"
    r"(?:https://www\.open-std\.org)"
    r"(?P<path>/[^\"'#?]*)?"
    r"(?P<rest>[#?][^\"']*)?"
    r"(?P=q)",
    re.IGNORECASE,
)


# ── multiprocessing worker (must be module-level for pickling) ─────────────────

def _rewrite_worker(arg: tuple[str, str]) -> str:
    """
    Rewrite absolute https://www.open-std.org/... links in one HTML file to
    relative paths.  Accepts (filepath_str, mirror_dir_str) so it can be
    pickled by multiprocessing.Pool on any platform.

    Returns a status line:
        REWRITTEN <path>   - file was modified and written back
        UNCHANGED <path>   - no absolute origin links found (no write)
        MISSING   <path>   - file does not exist on disk
        ERROR     <path>: <reason>
    """
    filepath, mirror_dir_str = arg
    path = Path(filepath).resolve()
    mirror_root = Path(mirror_dir_str).resolve()

    if not path.is_file():
        return f"MISSING   {filepath}"

    def _rel(url_path: str) -> str | None:
        target = (mirror_root / url_path.lstrip("/")).resolve()
        if not target.exists():
            return None
        try:
            return os.path.relpath(target, path.parent).replace("\\", "/")
        except ValueError:
            return None  # cross-drive on Windows - leave absolute

    changed = False

    def _replacer(m: re.Match) -> str:
        nonlocal changed
        rel = _rel(m.group("path") or "/")
        if rel is None:
            return m.group(0)
        changed = True
        rest = m.group("rest") or ""
        q    = m.group("q")
        return f"{m.group('attr')}{q}{rel}{rest}{q}"

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR     {filepath}: {exc}"

    rewritten = _LINK_RE.sub(_replacer, original)

    if changed:
        try:
            path.write_text(rewritten, encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"ERROR     {filepath}: {exc}"
        return f"REWRITTEN {filepath}"

    return f"UNCHANGED {filepath}"


# ── link-rewrite orchestrator ──────────────────────────────────────────────────

def rewrite_links(paths: list[str], mirror_dir: Path) -> int:
    """
    Rewrite links in every HTML file in *paths*.
    Returns the number of rewrite errors (0 = clean).
    """
    if not paths:
        logging.info("rewrite: no HTML files to process")
        return 0

    n_cores   = multiprocessing.cpu_count()
    n_workers = max(1, n_cores - 1)
    logging.info(
        "rewrite: %d file(s), %d worker(s) of %d cores",
        len(paths), n_workers, n_cores,
    )
    args = [(p, str(mirror_dir)) for p in paths]
    rewritten = unchanged = errors = 0

    try:
        with multiprocessing.Pool(processes=n_workers) as pool:
            for status in pool.imap_unordered(_rewrite_worker, args, chunksize=1):
                logging.debug(status)
                if status.startswith("REWRITTEN"):
                    rewritten += 1
                elif status.startswith("UNCHANGED"):
                    unchanged += 1
                else:
                    # ERROR or MISSING - surface at WARNING so CI always sees it
                    logging.warning("rewrite worker: %s", status)
                    errors += 1
    except Exception as exc:
        logging.error("rewrite pool failed: %s", exc)
        errors += 1

    logging.info(
        "rewrite: done - %d rewritten, %d unchanged, %d errors",
        rewritten, unchanged, errors,
    )
    return errors


# ── HTML link extractor ────────────────────────────────────────────────────────

class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        raw: str | None = None
        if tag in ("a", "link"):
            raw = a.get("href")
        elif tag in ("img", "script", "iframe"):
            raw = a.get("src")
        if raw and not raw.startswith(("mailto:", "javascript:", "#", "data:")):
            self.urls.append(urljoin(self.base_url, raw.strip()))


# ── HTTP session factory ───────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    s.headers["User-Agent"] = USER_AGENT
    return s


# ── crawler ────────────────────────────────────────────────────────────────────

class Crawler:
    """
    Breadth-first crawler of the WG21 website.

    n_threads worker threads share a Queue.  The main thread calls
    queue.join() to wait for all work to finish, then sends sentinels to
    shut the workers down cleanly.

    Items in the queue are (url, follow_links) tuples:
      follow_links=True  - parse HTML and enqueue discovered links
      follow_links=False - download only (page-requisite resources outside BASE_PATH)
    """

    def __init__(
        self,
        mirror_dir: Path,
        n_threads: int = 3,
        wait: float = 0.5,
        random_wait: bool = True,
    ) -> None:
        self.mirror_dir  = mirror_dir.resolve()
        self.n_threads   = n_threads
        self.wait        = wait
        self.random_wait = random_wait

        self._queue: Queue[tuple[str, bool] | None] = Queue()
        self._visited: set[str] = set()
        self._vis_lock   = threading.Lock()
        self._stats_lock = threading.Lock()
        self._newly_html: list[str] = []  # HTML files fetched this run
        self._tl = threading.local()      # per-thread requests.Session

        # Counters - all updates go through _inc()
        self._stats: dict[str, int] = {
            "papers_skipped":  0,   # immutable papers already on disk
            "rejected_ext":    0,   # rejected by extension filter
            "downloaded_html": 0,
            "downloaded_other": 0,
            "errors_4xx":      0,
            "errors_5xx":      0,
            "errors_net":      0,   # connection/timeout failures
            "errors_write":    0,   # disk write failures
        }

    def _inc(self, key: str, n: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] += n

    # ── helpers ──────────────────────────────────────────────────────────────

    def _session(self) -> requests.Session:
        if not hasattr(self._tl, "sess"):
            self._tl.sess = _make_session()
        return self._tl.sess

    def _local(self, url: str) -> Path:
        """Map a URL to its local mirror path (netloc stripped; path only)."""
        p   = urlparse(url)
        rel = unquote(p.path)
        if p.path.endswith("/"):
            rel = rel.rstrip("/") + "/index.html"
        # Normalise separators; filter empty parts from leading slash
        parts = [part for part in rel.replace("\\", "/").split("/") if part]
        if not parts:
            raise ValueError(f"Cannot map URL to local path: {url!r}")
        return self.mirror_dir.joinpath(*parts)

    def _excluded(self, path: str) -> bool:
        return any(path.startswith(e) for e in EXCLUDE_PATHS)

    def _reject_ext(self, path: str) -> bool:
        lower = path.lower()
        return any(lower.endswith(s) for s in REJECT_SUFFIXES)

    def _is_immutable_paper(self, url: str) -> bool:
        """
        Return True if the URL points to an immutable, published WG21 paper
        that should never be re-downloaded if already present locally.

        Two detection strategies:
        1. Path-based: file lives under /docs/papers/YYYY/ (a dated sub-directory).
           Everything there is a paper EXCEPT known mutable pages (index.html,
           lwg-*.html, sd-*.html) and Apache sort-view URLs (containing @).
        2. Stem-based: filename stem matches p####r#, d####r#, n#### patterns.
           Catches papers served from paths without a year segment.
        """
        p    = urlparse(url)
        path = p.path
        name = Path(unquote(path)).name
        if not name:
            return False

        if _IN_PAPERS_YEAR.search(path):
            # Inside a dated year directory - paper unless it is a mutable file
            if name.lower() in _MUTABLE_NAMES:
                return False
            if name.lower().startswith(("lwg", "sd-")):
                return False
            if "@" in name:  # Apache sort-view copy
                return False
            return True

        # Outside year directories - rely on filename stem pattern
        stem = Path(name).stem
        return bool(_PAPER_STEM.match(stem))

    @staticmethod
    def _canonical(url: str) -> str:
        """
        Return a normalised key for deduplication.

        Strips fragment and query string so that:
          https://example.com/page?C=N;O=D#anchor
        and
          https://example.com/page
        map to the same visited-set entry.

        The original URL (with query) is still used for the actual HTTP GET so
        we do not accidentally break pages that require query params.
        """
        p = urlparse(url)
        return p._replace(query="", fragment="").geturl()

    def _skip_download(self, url: str) -> tuple[bool, str]:
        """
        Return (should_skip, reason_string).
        reason_string is empty when should_skip is False.
        """
        p = urlparse(url)

        if self._reject_ext(p.path):
            return True, "ext"

        # Apache sort-view query strings - skip (duplicate directory listings)
        if p.query and re.search(r"C=[NMSD]", p.query):
            return True, "sort-view"

        # Immutable paper that already exists locally - the main optimisation
        if self._is_immutable_paper(url) and self._local(url).exists():
            return True, "paper"

        return False, ""

    def _enqueue(self, url: str, follow: bool) -> None:
        """
        Add url to the work queue if not already visited.

        Deduplication uses the canonical (query-and-fragment-stripped) form so
        that the same page requested with different sort params is only fetched
        once.  The original url (potentially with query) is what gets fetched,
        so pages that require query params still work.
        """
        key = self._canonical(url)
        if not key:
            return
        with self._vis_lock:
            if key in self._visited:
                return
            self._visited.add(key)
        self._queue.put((url, follow))

    # ── per-URL processing ───────────────────────────────────────────────────

    def _process(self, url: str, follow: bool) -> None:
        skip, reason = self._skip_download(url)
        if skip:
            if reason == "paper":
                self._inc("papers_skipped")
            elif reason == "ext":
                self._inc("rejected_ext")
            logging.debug("SKIP [%s]  %s", reason, url)
            return

        lp = self._local(url)
        final_url = url  # updated below if the server issues a redirect

        try:
            # Use response as a context manager so it is always closed, even on
            # early return for error status codes (prevents connection pool leak).
            with self._session().get(url, stream=True, timeout=30) as resp:
                # Recompute lp from the final URL after any server-side redirect.
                # This prevents a file/directory name clash when a no-slash URL
                # (e.g. /jtc1/sc22/wg21) redirects to the slash version
                # (/jtc1/sc22/wg21/) — the correct local path is then
                # wg21/index.html rather than a plain file named "wg21".
                final_url = resp.url
                if final_url != url:
                    final_p = urlparse(final_url)
                    if final_p.hostname == urlparse(url).hostname:
                        lp = self._local(final_url)
                        # Mark the redirect target as visited so it is not
                        # fetched a second time by another thread or iteration.
                        with self._vis_lock:
                            self._visited.add(self._canonical(final_url))

                code = resp.status_code

                if code == 304:
                    logging.debug("304   %s", url)
                    return

                if code in (401, 403, 404):
                    self._inc("errors_4xx")
                    logging.debug("%d    %s", code, url)
                    return

                if code != 200:
                    self._inc("errors_5xx")
                    logging.warning("%d    %s", code, url)
                    return

                ct      = resp.headers.get("Content-Type", "")
                is_html = "text/html" in ct or lp.suffix.lower() in (".html", ".htm")

                try:
                    lp.parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    self._inc("errors_write")
                    logging.error("MKDIR FAIL %s -> %s: %s", url, lp.parent, exc)
                    return

                try:
                    if is_html and follow:
                        # Read fully so we can parse outbound links without a
                        # second request.  HTML pages are small (< 1 MB).
                        body = resp.content
                        lp.write_bytes(body)
                    else:
                        # Stream large files (PDFs, ZIPs) chunk by chunk.
                        body = None
                        with lp.open("wb") as fh:
                            for chunk in resp.iter_content(chunk_size=65536):
                                fh.write(chunk)
                except OSError as exc:
                    self._inc("errors_write")
                    logging.error("WRITE FAIL %s -> %s: %s", url, lp, exc)
                    return

        except requests.RequestException as exc:
            self._inc("errors_net")
            logging.warning("NET ERR  %s - %s", url, exc)
            return

        logging.info("200   %s", url)

        if is_html:
            self._inc("downloaded_html")
            with self._stats_lock:
                self._newly_html.append(str(lp))
        else:
            self._inc("downloaded_other")

        # Parse links from HTML pages inside the WG21 subtree
        if is_html and follow and body:
            try:
                # Use final_url (after redirect) as the base for resolving
                # relative hrefs — ensures e.g. /wg21 (no slash) redirected
                # to /wg21/ produces correct absolute links for sub-pages.
                parser = _LinkParser(final_url)
                parser.feed(body.decode("utf-8", errors="replace"))
            except Exception as exc:
                logging.warning("HTML PARSE ERR %s: %s", url, exc)
                return

            for link in parser.urls:
                lp2 = urlparse(link)
                if lp2.netloc != "www.open-std.org":
                    continue
                if self._excluded(lp2.path):
                    continue
                in_base = lp2.path.startswith(BASE_PATH)
                if not in_base:
                    # Outside the WG21 subtree: only fetch page-requisite
                    # resources (images, CSS, JS).  Skip HTML pages, PDFs,
                    # and all other documents from sibling working groups
                    # (wg14, wg15, sc22 root, etc.) to prevent out-of-scope
                    # downloads and Windows path-collision errors.
                    ext = Path(unquote(lp2.path)).suffix.lower()
                    if ext not in _RESOURCE_SUFFIXES:
                        continue
                # Enqueue BEFORE task_done() is called (in _worker's finally)
                # so queue.join() in the main thread cannot return prematurely.
                self._enqueue(link, in_base)

    # ── worker thread ────────────────────────────────────────────────────────

    def _worker(self, wid: int) -> None:
        """
        Worker loop.

        IMPORTANT: task_done() is in the finally block that wraps the entire
        item-processing body, including the None sentinel check.  This ensures
        task_done() is always called exactly once per queue.get(), even if
        KeyboardInterrupt fires between get() and the try statement.
        """
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    # Sentinel: clean shutdown requested.
                    break
                url, follow = item
                try:
                    self._process(url, follow)
                except Exception as exc:
                    logging.warning("[w%d] unhandled: %s - %s", wid, url, exc)
            finally:
                # Called for normal items AND the None sentinel, ensuring
                # queue.join() never hangs regardless of how this loop exits.
                self._queue.task_done()

            sleep = self.wait * (random.uniform(1.0, 2.0) if self.random_wait else 1.0)
            time.sleep(sleep)

    # ── public entry point ───────────────────────────────────────────────────

    def run(self) -> list[str]:
        """Crawl the site and return list of HTML file paths downloaded this run."""
        start_url = ORIGIN + BASE_PATH
        logging.info("Phase 1: crawling from %s", start_url)
        self._enqueue(start_url, follow=True)

        threads = [
            threading.Thread(
                target=self._worker, args=(i,), daemon=True, name=f"crawler-{i}"
            )
            for i in range(self.n_threads)
        ]
        for t in threads:
            t.start()
        logging.debug("Started %d worker thread(s)", self.n_threads)

        self._queue.join()          # blocks until every task_done() has been called

        for _ in threads:           # send one sentinel per worker to stop them
            self._queue.put(None)
        for t in threads:
            t.join()

        return self._newly_html


# ── CLI entry point ────────────────────────────────────────────────────────────

def _log_startup(args: argparse.Namespace, mirror_dir: Path) -> None:
    """Emit a startup banner useful for diagnosing GitHub Actions failures."""
    logging.info("=== WG21 mirror update ===")
    logging.info("Python     : %s", sys.version.replace("\n", " "))
    logging.info("Platform   : %s", platform.platform())
    logging.info("requests   : %s", requests.__version__)
    logging.info("Mirror dir : %s", mirror_dir.resolve())
    logging.info("Threads    : %d", args.threads)
    logging.info(
        "Wait       : %.1fs%s",
        args.wait,
        " + x1-2 random jitter" if not args.no_random_wait else "",
    )
    logging.info("Verbose    : %s", args.verbose)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Incrementally update the local WG21 mirror.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--mirror-dir",
        default=str(Path.home() / "wg21-mirror"),
        help="Root directory of the local mirror",
    )
    ap.add_argument(
        "--threads", type=int, default=3,
        help="Parallel download threads (1-10; keep <=5 to stay polite)",
    )
    ap.add_argument(
        "--wait", type=float, default=0.5,
        help="Base wait between requests in seconds",
    )
    ap.add_argument(
        "--no-random-wait", action="store_true",
        help="Disable x1-2 random jitter on the wait time",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show DEBUG-level output",
    )
    args = ap.parse_args()

    # ── validate arguments ────────────────────────────────────────────────────
    if not (1 <= args.threads <= 10):
        ap.error(f"--threads must be between 1 and 10, got {args.threads}")
    if args.wait < 0:
        ap.error(f"--wait must be non-negative, got {args.wait}")

    # ── logging setup ─────────────────────────────────────────────────────────
    # Include date in timestamps: long runs can span midnight on a CI runner.
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,       # GitHub Actions captures stderr in the log
    )

    mirror_dir = Path(args.mirror_dir)
    try:
        mirror_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logging.error("Cannot create mirror directory %s: %s", mirror_dir, exc)
        sys.exit(1)

    _log_startup(args, mirror_dir)

    t_start = time.monotonic()

    # ── phase 1: crawl & fetch ────────────────────────────────────────────────
    crawler = Crawler(
        mirror_dir=mirror_dir,
        n_threads=args.threads,
        wait=args.wait,
        random_wait=not args.no_random_wait,
    )

    try:
        newly_html = crawler.run()
    except KeyboardInterrupt:
        logging.warning("Crawl interrupted by user (KeyboardInterrupt)")
        newly_html = crawler._newly_html  # process whatever was downloaded

    t_fetch = time.monotonic()
    s = crawler._stats

    logging.info(
        "Phase 1 done in %.0fs: "
        "%d HTML + %d other downloaded, "
        "%d papers skipped, "
        "%d rejected by extension, "
        "%d 4xx, %d 5xx, %d net errors, %d write errors",
        t_fetch - t_start,
        s["downloaded_html"],
        s["downloaded_other"],
        s["papers_skipped"],
        s["rejected_ext"],
        s["errors_4xx"],
        s["errors_5xx"],
        s["errors_net"],
        s["errors_write"],
    )

    # ── phase 2: rewrite links in newly downloaded HTML only ─────────────────
    logging.info("Phase 2: rewriting links in %d file(s)", len(newly_html))
    rewrite_errors = rewrite_links(newly_html, mirror_dir)

    t_end = time.monotonic()

    # ── final summary ─────────────────────────────────────────────────────────
    total_errors = (
        s["errors_net"] + s["errors_5xx"] + s["errors_write"] + rewrite_errors
    )
    logging.info(
        "Done. Fetch: %.0fs, Rewrite: %.0fs, Total: %.0fs",
        t_fetch - t_start,
        t_end - t_fetch,
        t_end - t_start,
    )

    if total_errors:
        logging.warning(
            "Completed with %d error(s) "
            "(net=%d, 5xx=%d, write=%d, rewrite=%d). "
            "Re-run to retry failed URLs.",
            total_errors,
            s["errors_net"], s["errors_5xx"], s["errors_write"], rewrite_errors,
        )
        sys.exit(1)

    logging.info("All done - no errors.")


if __name__ == "__main__":
    multiprocessing.freeze_support()   # required on Windows with spawn start-method
    main()
