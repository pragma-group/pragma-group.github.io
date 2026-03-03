#!/usr/bin/env python3
"""
inject-pragma-column.py -- Inject/update PRAGMA review column in WG21 mailing tables.

For each yearly index.html in the WG21 papers tree, finds every monthly mailing
table (identified by <a name="mailingYYYY-MM[...]"> anchors) and injects a
"PRAGMA" column at the right edge.  Cell content is drawn from a CSV file
mapping (mailing_id, doc_number) to PRAGMA review outputs.

Idempotent: running the script multiple times produces the same result.
  - First run:   adds the PRAGMA <th> header, updates colspan, appends cells.
  - Later runs:  only replaces the CONTENT of existing PRAGMA cells if the CSV
                 changed.  Whitespace and structure are never touched again.

Two HTML formats are handled transparently:
  - 2022-era: well-formed <th>Disposition</th>, <!-- begin/end --> inside table
  - 2025/2026-era: malformed <th>Disposition<th>, <!-- begin/end --> outside

CSV format
----------
    mailing_id,doc_number,category,output_url
    2026-01,P3826R3,Feature/Networking,
    2026-02,P2583R0,Feature/Coroutines,https://pragma-group.github.io/pragma/...

Fields
------
    mailing_id   YYYY-MM (canonical month, no pre/post label)
    doc_number   Uppercase WG21 number, e.g. P3826R3 or N5034
    category     Phase 0 categorisation text
    output_url   Empty for Phase 0; relative or absolute URL to PRAGMA report

Column behaviour
----------------
    Every mailing table gets a <th class="pragma-col">PRAGMA</th> header.
    Every data row gets <td class="pragma-cell">...</td>:
        - Empty string if no CSV record for that paper.
        - Plain text category if output_url is absent.
        - <a href="output_url">category</a> if output_url is present.

Usage
-----
    # Run from repo root (processes all years):
    python .github/workflows/assets/inject-pragma-column.py

    # Limit to recent years only:
    python .github/workflows/assets/inject-pragma-column.py --years 2024,2025,2026

    # Dry run (show what would change, do not write):
    python .github/workflows/assets/inject-pragma-column.py --dry-run --verbose

Options
-------
    --papers-dir DIR   Path to the papers directory
                       (default: jtc1/sc22/wg21/docs/papers)
    --csv FILE         Path to the PRAGMA outputs CSV file
                       (default: pragma/pragma-outputs.csv)
    --years Y,Y,...    Comma-separated years to process  (default: all)
    --verbose / -v     Print per-file MODIFIED/UNCHANGED to stdout
    --dry-run          Show changes without writing files

Exit codes
----------
    0 - success (even if no files were changed)
    1 - one or more files had errors
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


# ── compiled patterns ──────────────────────────────────────────────────────────

# Monthly mailing anchor — captures the canonical YYYY-MM portion only.
_ANCHOR_RE = re.compile(
    r'<a\s+name="mailing(\d{4}-\d{2})[^"]*"',
    re.IGNORECASE,
)

# Disposition header cell.  Handles both:
#   well-formed  : <th>Disposition</th>
#   malformed    : <th>Disposition<th>   (WG21 HTML quirk — closing slash omitted)
# The alternation consumes the full closing token so no stray ">" is left.
_DISPOSITION_RE = re.compile(
    r'(<th[^>]*>\s*Disposition\s*)(?:</th>|<th[^>]*>)',
    re.IGNORECASE,
)

# colspan row — matches either "8" (original) or "9" (already injected).
_COLSPAN_RE = re.compile(r'(colspan=")[89](")', re.IGNORECASE)

# A complete <tr>...</tr> block (multi-line, non-greedy).
_ROW_RE = re.compile(r'(<tr[^>]*>)(.*?)(</tr>)', re.DOTALL | re.IGNORECASE)

# Document number: first <td><a href="...">DOCNUM</a> in a row body.
_DOC_RE = re.compile(
    r'<td[^>]*>\s*<a\s[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)

# Detects an already-injected PRAGMA header (used to decide inject vs update).
_HAS_PRAGMA_COL_RE = re.compile(
    r'class=["\']pragma-col["\']',
    re.IGNORECASE,
)

# Strip patterns (used only on the first-injection path for safety).
_STRIP_PRAGMA_COL_RE = re.compile(
    r'\s*<th[^>]*class=["\']pragma-col["\'][^>]*>.*?</th>',
    re.IGNORECASE | re.DOTALL,
)
_STRIP_PRAGMA_CELL_RE = re.compile(
    r'<td[^>]*class=["\']pragma-cell["\'][^>]*>.*?</td>',
    re.IGNORECASE | re.DOTALL,
)


# ── CSV loading ────────────────────────────────────────────────────────────────

# Lookup key: (mailing_id, doc_number_uppercase)
# Value: (category, output_url)
CsvLookup = dict[tuple[str, str], tuple[str, str]]


def load_csv(csv_path: Path) -> CsvLookup:
    """Load the PRAGMA outputs CSV into a lookup dict."""
    lookup: CsvLookup = {}
    if not csv_path.exists():
        sys.stderr.write(
            f"INFO: CSV not found at {csv_path}; all PRAGMA cells will be empty.\n"
        )
        return lookup
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            mailing_id = row.get("mailing_id", "").strip()
            doc_number  = row.get("doc_number",  "").strip().upper()
            category    = row.get("category",    "").strip()
            output_url  = row.get("output_url",  "").strip()
            if mailing_id and doc_number:
                lookup[(mailing_id, doc_number)] = (category, output_url)
    return lookup


# ── cell rendering ─────────────────────────────────────────────────────────────

def _cell_content(category: str, output_url: str) -> str:
    if not category:
        return ""
    if output_url:
        return f'<a href="{output_url}">{category}</a>'
    return category


def _build_pragma_cell(category: str, output_url: str) -> str:
    return f'<td class="pragma-cell">{_cell_content(category, output_url)}</td>'


# ── table manipulation ─────────────────────────────────────────────────────────

def _full_inject(table_html: str, mailing_id: str, lookup: CsvLookup) -> str:
    """
    First-time injection: add PRAGMA <th>, update colspan, append PRAGMA <td>
    to every data row.

    Safety: if somehow called on a table that already has PRAGMA columns (e.g.
    from a previous run with a different encoding), strip them first so we never
    double-inject.
    """
    if _HAS_PRAGMA_COL_RE.search(table_html):
        table_html = _STRIP_PRAGMA_COL_RE.sub("", table_html)
        table_html = _STRIP_PRAGMA_CELL_RE.sub("", table_html)
        table_html = _COLSPAN_RE.sub(lambda m: m.group(1) + "8" + m.group(2), table_html)

    # 1. Add PRAGMA <th> right after Disposition header.
    def _replace_disposition(m: re.Match) -> str:
        return f'{m.group(1)}</th><th class="pragma-col">PRAGMA</th>'

    table_html = _DISPOSITION_RE.sub(_replace_disposition, table_html)

    # 2. Bump colspan 8 → 9.
    table_html = _COLSPAN_RE.sub(lambda m: m.group(1) + "9" + m.group(2), table_html)

    # 3. Append PRAGMA <td> to every data row.
    def _append_cell(m: re.Match) -> str:
        row_open  = m.group(1)
        row_body  = m.group(2)
        row_close = m.group(3)

        if re.search(r"<th", row_body, re.IGNORECASE):
            return m.group(0)

        doc_m = _DOC_RE.search(row_body)
        if not doc_m:
            return m.group(0)

        doc_number = doc_m.group(1).strip().upper()
        cat, url   = lookup.get((mailing_id, doc_number), ("", ""))
        return f"{row_open}{row_body}\t\t{_build_pragma_cell(cat, url)}\n\t{row_close}"

    return _ROW_RE.sub(_append_cell, table_html)


def _update_cells(table_html: str, mailing_id: str, lookup: CsvLookup) -> str:
    """
    Subsequent-run update: replace only the CONTENT inside existing PRAGMA cells.
    Structure (whitespace, header, colspan) is never touched.
    """
    def _update_row(m: re.Match) -> str:
        row_open  = m.group(1)
        row_body  = m.group(2)
        row_close = m.group(3)

        if re.search(r"<th", row_body, re.IGNORECASE):
            return m.group(0)

        doc_m = _DOC_RE.search(row_body)
        if not doc_m:
            return m.group(0)

        doc_number = doc_m.group(1).strip().upper()
        cat, url   = lookup.get((mailing_id, doc_number), ("", ""))
        new_content = _cell_content(cat, url)

        new_body = re.sub(
            r'(<td[^>]*class=["\']pragma-cell["\'][^>]*>).*?(</td>)',
            lambda cm: cm.group(1) + new_content + cm.group(2),
            row_body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return f"{row_open}{new_body}{row_close}"

    return _ROW_RE.sub(_update_row, table_html)


def _inject_pragma_column(table_html: str, mailing_id: str, lookup: CsvLookup) -> str:
    """Dispatch to full injection or cell-content update depending on table state."""
    if _HAS_PRAGMA_COL_RE.search(table_html):
        return _update_cells(table_html, mailing_id, lookup)
    return _full_inject(table_html, mailing_id, lookup)


# ── table location ─────────────────────────────────────────────────────────────

def _find_table_end(text: str, start: int) -> int:
    """
    Return position immediately after the </table> closing the <table at *start*.
    Handles nested tables.  Returns -1 if not found.
    """
    depth = 0
    i = start
    lower = text.lower()
    while i < len(lower):
        if lower[i : i + 6] == "<table":
            depth += 1
            i += 6
        elif lower[i : i + 8] == "</table>":
            depth -= 1
            if depth == 0:
                return i + 8
            i += 8
        else:
            i += 1
    return -1


# ── per-file processing ────────────────────────────────────────────────────────

def _process_year_file(
    path: Path,
    lookup: CsvLookup,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Process one yearly index.html.  Returns True if the file was (or would be) modified."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write(f"ERROR reading {path}: {exc}\n")
        return False

    original = text

    # Collect (table_start, table_end, mailing_id) for all mailing sections.
    segments: list[tuple[int, int, str]] = []

    for anchor_m in _ANCHOR_RE.finditer(text):
        mailing_id  = anchor_m.group(1)
        search_from = anchor_m.end()

        table_start = text.lower().find("<table", search_from)
        if table_start == -1:
            sys.stderr.write(
                f"WARNING: no <table found after mailing anchor {mailing_id} in {path}\n"
            )
            continue

        table_end = _find_table_end(text, table_start)
        if table_end == -1:
            sys.stderr.write(
                f"WARNING: unclosed <table for {mailing_id} in {path}\n"
            )
            continue

        segments.append((table_start, table_end, mailing_id))

    if not segments:
        return False

    # Guard against unexpected overlaps (should never happen).
    segments.sort(key=lambda s: s[0])
    for i in range(len(segments) - 1):
        if segments[i][1] > segments[i + 1][0]:
            sys.stderr.write(
                f"WARNING: overlapping table ranges in {path}, skipping file\n"
            )
            return False

    # Process end → beginning so earlier positions remain valid after splicing.
    changed = False
    for table_start, table_end, mailing_id in reversed(segments):
        old_table = text[table_start:table_end]
        new_table = _inject_pragma_column(old_table, mailing_id, lookup)
        if old_table != new_table:
            changed = True
            text = text[:table_start] + new_table + text[table_end:]

    if not changed:
        if verbose:
            print(f"UNCHANGED {path}")
        return False

    if verbose:
        print(f"MODIFIED  {path}")

    if not dry_run:
        try:
            path.write_text(text, encoding="utf-8", errors="replace")
        except OSError as exc:
            sys.stderr.write(f"ERROR writing {path}: {exc}\n")
            return False

    return True


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inject/update PRAGMA review column in WG21 mailing tables.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--papers-dir",
        default="jtc1/sc22/wg21/docs/papers",
        help="Path to the papers directory",
    )
    ap.add_argument(
        "--csv",
        default="pragma/pragma-outputs.csv",
        help="Path to the PRAGMA outputs CSV file",
    )
    ap.add_argument(
        "--years",
        default="",
        help="Comma-separated years to process (default: all)",
    )
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    args = ap.parse_args()

    papers_dir = Path(args.papers_dir)
    csv_path   = Path(args.csv)

    if not papers_dir.is_dir():
        sys.exit(f"Error: papers directory not found: {papers_dir}")

    lookup = load_csv(csv_path)
    sys.stderr.write(f"Loaded {len(lookup)} PRAGMA record(s) from {csv_path}\n")

    year_filter: set[str] = set()
    if args.years:
        year_filter = {y.strip() for y in args.years.split(",") if y.strip()}

    year_dirs = sorted(
        d
        for d in papers_dir.iterdir()
        if d.is_dir() and d.name.isdigit()
        and (not year_filter or d.name in year_filter)
    )

    modified = errors = 0
    for year_dir in year_dirs:
        index = year_dir / "index.html"
        if not index.exists():
            continue
        try:
            if _process_year_file(
                index, lookup, dry_run=args.dry_run, verbose=args.verbose
            ):
                modified += 1
        except Exception as exc:
            sys.stderr.write(f"ERROR processing {index}: {exc}\n")
            errors += 1

    sys.stderr.write(
        f"{'DRY RUN - ' if args.dry_run else ''}"
        f"{modified} file(s) modified, {errors} error(s).\n"
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
