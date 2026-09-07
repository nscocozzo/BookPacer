"""Tests for the BookPacer pacing logic."""

import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookpacer import pacing

TODAY = date(2026, 9, 7)


class PacingMathTests(unittest.TestCase):
    def test_pages_per_day_rounds_up(self):
        # 101 pages left, 10 days (incl. today) -> 11 pages/day
        due = TODAY + timedelta(days=9)
        self.assertEqual(pacing.pages_per_day(0, 101, due, TODAY), 11)

    def test_pages_per_day_even_split(self):
        due = TODAY + timedelta(days=4)
        self.assertEqual(pacing.pages_per_day(100, 200, due, TODAY), 20)

    def test_pages_per_day_due_today(self):
        self.assertEqual(pacing.pages_per_day(50, 100, TODAY, TODAY), 50)

    def test_pages_per_day_overdue_still_positive(self):
        due = TODAY - timedelta(days=3)
        self.assertEqual(pacing.pages_per_day(50, 100, due, TODAY), 50)

    def test_finished_book_needs_zero_pages(self):
        due = TODAY + timedelta(days=5)
        self.assertEqual(pacing.pages_per_day(300, 300, due, TODAY), 0)

    def test_reading_status_overdue(self):
        due = TODAY - timedelta(days=2)
        status = pacing.reading_status(50, 100, due, TODAY)
        self.assertTrue(status["is_overdue"])
        self.assertFalse(status["is_finished"])
        self.assertEqual(status["pages_left"], 50)

    def test_reading_status_finished(self):
        status = pacing.reading_status(300, 300, TODAY + timedelta(days=5), TODAY)
        self.assertTrue(status["is_finished"])
        self.assertEqual(status["pages_per_day"], 0)

    def test_reading_status_percent(self):
        status = pacing.reading_status(75, 300, TODAY + timedelta(days=5), TODAY)
        self.assertEqual(status["percent_complete"], 25.0)

    def test_progress_to_page(self):
        self.assertEqual(pacing.progress_to_page(45, 304), 137)
        self.assertEqual(pacing.progress_to_page(100, 304), 304)
        self.assertEqual(pacing.progress_to_page(150, 304), 304)  # clamped
        self.assertEqual(pacing.progress_to_page(50, 0), 0)


class FableImportTests(unittest.TestCase):
    def test_parse_simple_format(self):
        text = "The Midnight Library by Matt Haig\n45%\n304 pages\n"
        books = pacing.parse_fable_text(text)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "The Midnight Library")
        self.assertEqual(books[0]["author"], "Matt Haig")
        self.assertEqual(books[0]["progress"], 45.0)
        self.assertEqual(books[0]["total_pages"], 304)

    def test_parse_key_value_format(self):
        text = (
            "Title: Project Hail Mary\n"
            "Author: Andy Weir\n"
            "Progress: 60%\n"
            "Pages: 476\n"
        )
        books = pacing.parse_fable_text(text)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "Project Hail Mary")
        self.assertEqual(books[0]["author"], "Andy Weir")
        self.assertEqual(books[0]["progress"], 60.0)
        self.assertEqual(books[0]["total_pages"], 476)

    def test_parse_multiple_books(self):
        text = (
            "The Midnight Library by Matt Haig\n45%\n304 pages\n\n"
            "Dune by Frank Herbert\n10%\n896 pages\n"
        )
        books = pacing.parse_fable_text(text)
        self.assertEqual(len(books), 2)
        self.assertEqual(books[1]["title"], "Dune")

    def test_parse_thousands_separator(self):
        books = pacing.parse_fable_text("Big Book by Someone\n5%\n1,234 pages\n")
        self.assertEqual(books[0]["total_pages"], 1234)

    def test_parse_ignores_junk(self):
        self.assertEqual(pacing.parse_fable_text("hello world\n\n\n"), [])

    def test_import_creates_new_book_with_due_date(self):
        data = {"books": [], "settings": {}}
        imported = pacing.import_fable_text(
            data, "The Midnight Library by Matt Haig\n45%\n304 pages\n", "2026-09-21"
        )
        self.assertEqual(len(imported), 1)
        book = data["books"][0]
        self.assertEqual(book["due_date"], "2026-09-21")
        self.assertEqual(book["current_page"], 137)
        self.assertEqual(book["total_pages"], 304)

    def test_import_skips_new_book_without_due_date(self):
        data = {"books": [], "settings": {}}
        imported = pacing.import_fable_text(
            data, "The Midnight Library by Matt Haig\n45%\n304 pages\n"
        )
        self.assertEqual(imported, [])
        self.assertEqual(data["books"], [])

    def test_import_updates_existing_progress_and_keeps_due_date(self):
        data = {
            "books": [
                {
                    "title": "The Midnight Library",
                    "author": "Matt Haig",
                    "total_pages": 304,
                    "current_page": 10,
                    "due_date": "2026-09-21",
                }
            ],
            "settings": {},
        }
        pacing.import_fable_text(
            data, "The Midnight Library by Matt Haig\n50%\n304 pages\n"
        )
        book = data["books"][0]
        self.assertEqual(book["current_page"], 152)
        self.assertEqual(book["due_date"], "2026-09-21")

    def test_import_without_progress_keeps_existing_page(self):
        data = {
            "books": [
                {
                    "title": "The Midnight Library",
                    "author": "Matt Haig",
                    "total_pages": 304,
                    "current_page": 150,
                    "due_date": "2026-09-21",
                }
            ],
            "settings": {},
        }
        pacing.import_fable_text(data, "The Midnight Library by Matt Haig\n304 pages\n")
        self.assertEqual(data["books"][0]["current_page"], 150)


class StorageTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.json")
            data = {
                "books": [
                    {
                        "title": "Dune",
                        "author": "Frank Herbert",
                        "total_pages": 896,
                        "current_page": 100,
                        "due_date": "2026-09-30",
                    }
                ],
                "settings": {"webhook_url": "https://example.com/hook"},
            }
            pacing.save_data(data, path)
            loaded = pacing.load_data(path)
            self.assertEqual(loaded, data)

    def test_load_missing_file_gives_defaults(self):
        loaded = pacing.load_data("/nonexistent/path.json")
        self.assertEqual(loaded, {"books": [], "settings": {}})

    def test_upsert_replaces_by_title_case_insensitive(self):
        data = {"books": [], "settings": {}}
        pacing.upsert_book(
            data,
            {"title": "Dune", "total_pages": 896, "current_page": 1, "due_date": "2026-09-30"},
        )
        pacing.upsert_book(
            data,
            {"title": "DUNE", "total_pages": 896, "current_page": 200, "due_date": "2026-09-30"},
        )
        self.assertEqual(len(data["books"]), 1)
        self.assertEqual(data["books"][0]["current_page"], 200)

    def test_normalize_book_validates_date(self):
        with self.assertRaises(ValueError):
            pacing.normalize_book({"title": "X", "due_date": "next friday"})


class DiscordTests(unittest.TestCase):
    BOOK = {
        "title": "The Midnight Library",
        "author": "Matt Haig",
        "total_pages": 304,
        "current_page": 137,
        "due_date": "2026-09-16",  # 9 days after TODAY
    }

    def test_payload_mentions_pages_tonight(self):
        payload = pacing.build_webhook_payload([self.BOOK], TODAY)
        embed = payload["embeds"][0]
        # 167 pages left, 10 days incl. today -> 17/day
        self.assertIn("17 pages", embed["description"])
        self.assertIn("The Midnight Library", embed["title"])
        self.assertIn("Matt Haig", embed["title"])

    def test_payload_finished_book(self):
        book = {**self.BOOK, "current_page": 304}
        payload = pacing.build_webhook_payload([book], TODAY)
        self.assertIn("Finished", payload["embeds"][0]["description"])

    def test_payload_overdue_book(self):
        book = {**self.BOOK, "due_date": "2026-09-01"}
        payload = pacing.build_webhook_payload([book], TODAY)
        self.assertIn("due 6 day(s) ago", payload["embeds"][0]["description"])

    def test_payload_no_books(self):
        payload = pacing.build_webhook_payload([], TODAY)
        self.assertIn("No library books", payload["content"])

    def test_payload_caps_embeds_at_discord_limit(self):
        books = [{**self.BOOK, "title": f"Book {i}"} for i in range(12)]
        payload = pacing.build_webhook_payload(books, TODAY)
        self.assertEqual(len(payload["embeds"]), 10)
        self.assertIn("2 more book(s)", payload["content"])
        self.assertIn("Book 11", payload["content"])

    def test_send_requires_webhook(self):
        with self.assertRaises(ValueError):
            pacing.send_discord_reminder("", [self.BOOK], TODAY)

    def test_send_posts_json(self):
        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.object(
            pacing.urllib.request, "urlopen", return_value=FakeResponse()
        ) as mocked:
            ok = pacing.send_discord_reminder(
                "https://discord.com/api/webhooks/x/y", [self.BOOK], TODAY
            )
        self.assertTrue(ok)
        request = mocked.call_args[0][0]
        self.assertEqual(request.get_method(), "POST")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["username"], "BookPacer")
        self.assertEqual(len(body["embeds"]), 1)


if __name__ == "__main__":
    unittest.main()
