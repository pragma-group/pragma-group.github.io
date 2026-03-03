#!/usr/bin/env python3
"""
rewrite-links.py -- Offline link rewriter for the WG21 mirror
=============================================================

Reads file paths from stdin (one per line) and rewrites every absolute
https://www.open-std.org/... URL found in href/src/action/data attributes to a
relative path, making the mirror browsable offline via file://.

Only files that exist on disk are processed; only files that contain at least
one rewritable link are written back.  Memory usage is flat: each worker holds
exactly one file at a time.

Usage
-----
    # Rewrite all HTML files (run from the repo root):
    find . -name "*.html" | python .github/workflows/assets/rewrite-links.py

    # Specify an explicit mirror location:
    find /path/to/repo -name "*.html" | python rewrite-links.py --mirror-dir /path/to/repo

Options
-------
    --mirror-dir DIR   Root of the repo / local mirror  (default: .)
    --verbose / -v     Print per-file REWRITTEN/UNCHANGED lines to stdout
                       (ERROR lines always go to stderr)

Exit codes
----------
    0 - all files processed with no errors
    1 - one or more files had rewrite errors (MISSING or ERROR status)
    2 - bad arguments or stdin is a tty
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import platform
import re
import sys
from pathlib import Path


# ── link pattern ──────────────────────────────────────────────────────────────

_LINK_RE = re.compile(
    r"(?P<attr>(?:href|src|action|data)=)"
    r"(?P<q>[\"'])"
    r"(?:https://www\.open-std\.org)"
    r"(?P<path>/[^\"'#?]*)?"
    r"(?P<rest>[#?][^\"']*)?"
    r"(?P=q)",
    re.IGNORECASE,
)


# ── module-level worker (required by multiprocessing.Pool for pickling) ────────

def _rewrite_worker(arg: tuple[str, str]) -> str:
    filepath, mirror_dir_str = arg
    path        = Path(filepath).resolve()
    mirror_root = Path(mirror_dir_str).resolve()

    if not path.is_file():
        return f"MISSING   {filepath}"

    def _rel(url_path: str) -> str | None:
        target = (mirror_root / url_path.lstrip("/")).resolve()
        if not target.exists():
            # Extensionless URLs may be stored as name/index.html directories.
            index_variant = target / "index.html"
            if index_variant.exists():
                target = index_variant
            else:
                return None
        try:
            return os.path.relpath(target, path.parent).replace("\\", "/")
        except ValueError:
            return None

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


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Rewrite absolute WG21 links to relative paths in mirrored HTML files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--mirror-dir",
        default=".",
        help="Root directory of the local mirror",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print per-file REWRITTEN/UNCHANGED lines to stdout",
    )
    args = ap.parse_args()

    if sys.stdin.isatty():
        ap.print_help(sys.stderr)
        sys.stderr.write(
            "\nError: no file paths on stdin.\n"
            "Example: find . -name '*.html' | python .github/workflows/assets/rewrite-links.py\n"
        )
        sys.exit(2)

    sys.stderr.write(
        f"rewrite-links: Python {sys.version.split()[0]}, "
        f"{platform.system()}, "
        f"mirror={args.mirror_dir}\n"
    )

    raw_paths = [line.rstrip("\n") for line in sys.stdin if line.strip()]

    seen: set[str] = set()
    paths = [p for p in raw_paths if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]

    if not paths:
        sys.stderr.write("rewrite-links: no HTML files to process.\n")
        return

    n_cores   = multiprocessing.cpu_count()
    n_workers = max(1, n_cores - 1)
    mirror_dir = str(args.mirror_dir)

    sys.stderr.write(
        f"rewrite-links: {len(paths)} file(s), "
        f"{n_workers} worker(s) of {n_cores} cores.\n"
    )

    rewritten_n = unchanged_n = error_n = 0
    work_args = [(p, mirror_dir) for p in paths]

    try:
        with multiprocessing.Pool(processes=n_workers) as pool:
            for status in pool.imap_unordered(_rewrite_worker, work_args, chunksize=1):
                if status.startswith("REWRITTEN"):
                    rewritten_n += 1
                    if args.verbose:
                        print(status)
                elif status.startswith("UNCHANGED"):
                    unchanged_n += 1
                    if args.verbose:
                        print(status)
                else:
                    error_n += 1
                    sys.stderr.write(f"ERROR: {status}\n")
    except Exception as exc:
        sys.stderr.write(f"rewrite-links: pool failed: {exc}\n")
        sys.exit(1)

    sys.stderr.write(
        f"rewrite-links: done - {rewritten_n} rewritten, "
        f"{unchanged_n} unchanged, {error_n} errors.\n"
    )

    if error_n:
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
