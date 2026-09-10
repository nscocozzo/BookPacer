"""CLI utility to import Fable-formatted text into BookPacer.

Usage examples:

    python -m bookpacer.fable_sync --from-file fable.txt --due-date 2026-09-21
    type fable.txt | python -m bookpacer.fable_sync --stdin
"""

from __future__ import annotations

import argparse
import sys

from .pacing import import_fable_text, load_data, save_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bookpacer.fable_sync",
        description=(
            "Import Fable-formatted reading progress into the local BookPacer data file."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--from-file",
        metavar="PATH",
        help="Read Fable text from a UTF-8 file.",
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        help="Read Fable text from standard input.",
    )
    parser.add_argument(
        "--due-date",
        help=(
            "Due date (YYYY-MM-DD) used only for brand new books. "
            "Existing books keep their current due date."
        ),
    )
    parser.add_argument(
        "--data-path",
        help="Optional path to the BookPacer JSON file.",
    )
    return parser


def _read_input_text(args: argparse.Namespace) -> str:
    if args.from_file:
        with open(args.from_file, "r", encoding="utf-8") as fh:
            return fh.read()
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    text = _read_input_text(args)
    if not text.strip():
        print("No input text provided.", file=sys.stderr)
        return 1

    data = load_data(args.data_path)
    imported = import_fable_text(data, text, args.due_date)
    if not imported:
        print(
            "No books imported. Provide parsable Fable text and --due-date for new books.",
            file=sys.stderr,
        )
        return 2

    save_data(data, args.data_path)
    print("Imported/updated %d book(s)." % len(imported))
    for book in imported:
        print("- %s" % book["title"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())