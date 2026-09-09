"""Core pacing logic for BookPacer.

Computes daily reading pace, imports book data from Fable, sends Discord
webhook reminders, and persists everything in a small JSON file.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any, Dict, List, Optional

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "bookpacer.json",
)


def parse_date(value: str) -> date:
    """Parse an ISO date string (YYYY-MM-DD)."""
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def days_until(due_date: date, today: Optional[date] = None) -> int:
    """Days remaining until the due date (negative when overdue)."""
    today = today or date.today()
    return (due_date - today).days


def pages_per_day(
    current_page: int,
    total_pages: int,
    due_date: date,
    today: Optional[date] = None,
) -> int:
    """Pages to read per day to finish by the due date.

    Reading the computed number of pages on each remaining day (today
    included) finishes the book exactly on the due date. Returns 0 when
    the book is already finished.
    """
    pages_left = max(0, total_pages - current_page)
    if pages_left == 0:
        return 0
    remaining_days = max(1, days_until(due_date, today) + 1)
    return math.ceil(pages_left / remaining_days)


def reading_status(
    current_page: int,
    total_pages: int,
    due_date: date,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Full pacing snapshot for one book."""
    pages_left = max(0, total_pages - current_page)
    days_left = days_until(due_date, today)
    pace = pages_per_day(current_page, total_pages, due_date, today)
    finished = pages_left == 0
    return {
        "pages_left": pages_left,
        "days_left": days_left,
        "pages_per_day": pace,
        "percent_complete": round(100 * current_page / total_pages, 1)
        if total_pages > 0
        else 0.0,
        "is_overdue": days_left < 0 and not finished,
        "is_finished": finished,
    }


def progress_to_page(progress: float, total_pages: int) -> int:
    """Convert a Fable progress percentage to an absolute page number."""
    if total_pages <= 0:
        return 0
    progress = min(100.0, max(0.0, float(progress)))
    return round(total_pages * progress / 100.0)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def load_data(path: Optional[str] = None) -> Dict[str, Any]:
    """Load books and settings from the JSON data file."""
    path = path or os.environ.get("BOOKPACER_DATA") or DEFAULT_DATA_PATH
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = {}
    data.setdefault("books", [])
    data.setdefault("settings", {})
    return data


def save_data(data: Dict[str, Any], path: Optional[str] = None) -> None:
    """Persist books and settings to the JSON data file."""
    path = path or os.environ.get("BOOKPACER_DATA") or DEFAULT_DATA_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def normalize_book(book: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce types and apply defaults to a book record."""
    due_date = book.get("due_date")
    if not due_date:
        raise ValueError("A due date is required.")
    return {
        "title": str(book.get("title", "Untitled")).strip() or "Untitled",
        "author": str(book.get("author", "")).strip(),
        "total_pages": max(0, int(book.get("total_pages") or 0)),
        "current_page": max(0, int(book.get("current_page") or 0)),
        "due_date": parse_date(str(due_date)).isoformat(),
    }


def upsert_book(data: Dict[str, Any], book: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a book, matched case-insensitively by title."""
    book = normalize_book(book)
    for i, existing in enumerate(data["books"]):
        if existing["title"].lower() == book["title"].lower():
            data["books"][i] = book
            return book
    data["books"].append(book)
    return book


# ---------------------------------------------------------------------------
# Fable import
# ---------------------------------------------------------------------------

_PROGRESS_LINE = re.compile(r"^(?P<percent>\d+(?:\.\d+)?) ?%$", re.IGNORECASE)
_PAGES_LINE = re.compile(r"^(?P<pages>[\d,]+) pages?$", re.IGNORECASE)


def _split_book_line(line: str) -> Optional[tuple[str, str]]:
    """Split 'Title by Author' without regex backtracking."""
    title, sep, author = line.rpartition(" by ")
    if not sep or not title.strip() or not author.strip():
        return None
    return title.strip(), author.strip()


def parse_fable_text(text: str) -> List[Dict[str, Any]]:
    """Parse book data pasted from the Fable app or website.

    Recognises blocks in either of these shapes::

        The Midnight Library by Matt Haig
        45%
        304 pages

    or::

        Title: The Midnight Library
        Author: Matt Haig
        Progress: 45%
        Pages: 304

    Blank lines separate entries. Returns a list of dicts with ``title``,
    ``author``, ``progress`` (percent) and ``total_pages`` keys.
    """
    books: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}

    def flush() -> None:
        nonlocal current
        if current.get("title") and (current.get("total_pages") or "progress" in current):
            current.setdefault("author", "")
            books.append(current)
        current = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue

        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if sep and key in ("title", "author", "progress", "pages") and value.strip():
            value = value.strip()
            if key == "title":
                if current.get("title"):
                    flush()
                current["title"] = value
            elif key == "author":
                current["author"] = value
            elif key == "progress":
                num = re.match(r"^(\d+(?:\.\d+)?) ?%?$", value)
                if num:
                    current["progress"] = float(num.group(1))
            elif key == "pages":
                num = re.match(r"^([\d,]+)", value)
                if num:
                    current["total_pages"] = int(num.group(1).replace(",", ""))
            continue

        book_match = _split_book_line(line)
        if book_match:
            if current.get("title"):
                flush()
            current["title"], current["author"] = book_match
            continue

        progress_match = _PROGRESS_LINE.match(line)
        if progress_match:
            current["progress"] = float(progress_match.group(1))
            continue

        pages_match = _PAGES_LINE.match(line)
        if pages_match:
            current["total_pages"] = int(pages_match.group("pages").replace(",", ""))
            continue

    flush()
    return books


def import_fable_text(
    data: Dict[str, Any],
    text: str,
    due_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Import parsed Fable entries into the data store.

    ``due_date`` (YYYY-MM-DD) is applied to new books; existing books
    keep their due date and get their progress refreshed.
    """
    imported = []
    for entry in parse_fable_text(text):
        total_pages = entry.get("total_pages") or 0
        book: Dict[str, Any] = {
            "title": entry["title"],
            "author": entry.get("author", ""),
            "total_pages": total_pages,
            "current_page": progress_to_page(entry.get("progress", 0.0), total_pages),
        }
        existing = next(
            (
                b
                for b in data["books"]
                if b["title"].lower() == book["title"].lower()
            ),
            None,
        )
        if existing:
            if "progress" in entry:
                existing["current_page"] = book["current_page"]
            if total_pages:
                existing["total_pages"] = total_pages
            if entry.get("author"):
                existing["author"] = entry["author"]
            imported.append(existing)
        elif due_date:
            book["due_date"] = due_date
            imported.append(upsert_book(data, book))
    return imported


# ---------------------------------------------------------------------------
# Discord webhook
# ---------------------------------------------------------------------------


def build_embed(book: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Build a Discord embed for a single book."""
    due = parse_date(book["due_date"])
    status = reading_status(book["current_page"], book["total_pages"], due, today)
    if status["is_finished"]:
        description = "✅ Finished! Nice work."
        color = 0x57F287  # green
    elif status["is_overdue"]:
        description = (
            f"⚠️ This book was due {abs(status['days_left'])} day(s) ago — "
            f"{status['pages_left']} pages still left."
        )
        color = 0xED4245  # red
    else:
        target_page = min(
            book["total_pages"], book["current_page"] + status["pages_per_day"]
        )
        description = (
            f"Read **{status['pages_per_day']} pages** tonight "
            f"(up to page {target_page}) to stay on pace."
        )
        color = 0x5865F2  # Discord blurple

    author = book.get("author")
    return {
        "title": f"📖 {book['title']}" + (f" — {author}" if author else ""),
        "description": description,
        "color": color,
        "fields": [
            {
                "name": "Progress",
                "value": (
                    f"{book['current_page']} / {book['total_pages']} pages "
                    f"({status['percent_complete']}%)"
                ),
                "inline": True,
            },
            {
                "name": "Due",
                "value": f"{book['due_date']} ({status['days_left']} day(s) left)",
                "inline": True,
            },
        ],
    }


def build_webhook_payload(
    books: List[Dict[str, Any]], today: Optional[date] = None
) -> Dict[str, Any]:
    """Build the full Discord webhook payload for all tracked books.

    Discord accepts at most 10 embeds per message, so books beyond the
    tenth are summarised in the message content instead.
    """
    today = today or date.today()
    if not books:
        return {
            "username": "BookPacer",
            "content": "📚 No library books are being tracked right now.",
        }
    content = f"📚 **BookPacer daily reading reminder** — {today.isoformat()}"
    shown, extra = books[:10], books[10:]
    if extra:
        titles = ", ".join(b["title"] for b in extra)
        content += f"\nPlus {len(extra)} more book(s): {titles}"
    return {
        "username": "BookPacer",
        "content": content,
        "embeds": [build_embed(b, today) for b in shown],
    }


def send_discord_reminder(
    webhook_url: str,
    books: List[Dict[str, Any]],
    today: Optional[date] = None,
    timeout: int = 15,
) -> bool:
    """POST the daily reminder to a Discord webhook. Returns True on success."""
    if not webhook_url:
        raise ValueError("A Discord webhook URL is required.")
    payload = json.dumps(build_webhook_payload(books, today)).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status in (200, 204)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to send Discord reminder: {exc}") from exc
