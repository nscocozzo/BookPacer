"""Tests for the BookPacer Flask web application."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookpacer.app import create_app


class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_path = os.path.join(self.tmpdir.name, "data.json")
        self.app = create_app(self.data_path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def load(self):
        with open(self.data_path, encoding="utf-8") as fh:
            return json.load(fh)

    def add_book(self, **overrides):
        form = {
            "title": "Dune",
            "author": "Frank Herbert",
            "total_pages": "896",
            "current_page": "100",
            "due_date": "2026-09-20",
        }
        form.update(overrides)
        return self.client.post("/books", data=form, follow_redirects=True)

    def test_index_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"BookPacer", response.data)

    def test_add_book(self):
        response = self.add_book()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dune", response.data)
        book = self.load()["books"][0]
        self.assertEqual(book["title"], "Dune")
        self.assertEqual(book["total_pages"], 896)

    def test_add_book_missing_due_date_flashes_error(self):
        response = self.add_book(due_date="")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid book details", response.data)
        self.assertFalse(os.path.exists(self.data_path))

    def test_add_book_bad_date_flashes_error(self):
        response = self.add_book(due_date="next friday")
        self.assertIn(b"Invalid book details", response.data)

    def test_update_progress(self):
        self.add_book()
        response = self.client.post(
            "/books/0/progress", data={"current_page": "250"}, follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.load()["books"][0]["current_page"], 250)

    def test_update_progress_invalid_book(self):
        response = self.client.post(
            "/books/99/progress", data={"current_page": "1"}, follow_redirects=True
        )
        self.assertIn(b"Book not found", response.data)

    def test_update_progress_not_a_number(self):
        self.add_book()
        response = self.client.post(
            "/books/0/progress", data={"current_page": "abc"}, follow_redirects=True
        )
        self.assertIn(b"must be a number", response.data)

    def test_delete_book(self):
        self.add_book()
        response = self.client.post("/books/0/delete", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Removed", response.data)
        self.assertEqual(self.load()["books"], [])

    def test_pause_book_moves_to_to_be_continued(self):
        self.add_book()
        response = self.client.post("/books/0/pause", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Paused", response.data)
        data = self.load()
        self.assertEqual(data["books"], [])
        self.assertEqual(len(data["to_be_continued"]), 1)
        paused = data["to_be_continued"][0]
        self.assertEqual(paused["title"], "Dune")
        self.assertEqual(paused["author"], "Frank Herbert")
        self.assertEqual(paused["pages_read"], 100)
        self.assertEqual(paused["total_pages"], 896)

    def test_pause_book_replaces_existing_paused_match(self):
        self.add_book(current_page="100")
        self.client.post("/books/0/pause", follow_redirects=True)
        self.add_book(current_page="200")
        self.client.post("/books/0/pause", follow_redirects=True)
        paused = self.load()["to_be_continued"]
        self.assertEqual(len(paused), 1)
        self.assertEqual(paused[0]["pages_read"], 200)

    def test_pause_book_keeps_separate_when_author_differs(self):
        self.add_book(current_page="100")
        self.client.post("/books/0/pause", follow_redirects=True)
        self.add_book(author="Another Author", current_page="220")
        self.client.post("/books/0/pause", follow_redirects=True)
        paused = self.load()["to_be_continued"]
        self.assertEqual(len(paused), 2)

    def test_pause_finished_book_is_rejected(self):
        self.add_book(current_page="896")
        response = self.client.post("/books/0/pause", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"cannot be paused", response.data)
        data = self.load()
        self.assertEqual(len(data["books"]), 1)
        self.assertEqual(data["to_be_continued"], [])

    def test_resume_paused_book_with_new_due_date(self):
        self.add_book(current_page="220")
        self.client.post("/books/0/pause", follow_redirects=True)
        paused = self.load()["to_be_continued"][0]
        self.assertEqual(paused["book"]["due_date"], "2026-09-20")
        response = self.client.post(
            "/continued/0/resume",
            data={"due_date": "2026-10-11"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Resumed", response.data)
        data = self.load()
        self.assertEqual(data["to_be_continued"], [])
        self.assertEqual(len(data["books"]), 1)
        self.assertEqual(data["books"][0]["current_page"], 220)
        self.assertEqual(data["books"][0]["due_date"], "2026-10-11")

    def test_resume_paused_book_requires_valid_due_date(self):
        self.add_book()
        self.client.post("/books/0/pause", follow_redirects=True)
        response = self.client.post(
            "/continued/0/resume",
            data={"due_date": "next week"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"valid due date", response.data)
        data = self.load()
        self.assertEqual(len(data["books"]), 0)
        self.assertEqual(len(data["to_be_continued"]), 1)

    def test_resume_paused_book_rejects_active_title_conflict(self):
        self.add_book(current_page="220")
        self.client.post("/books/0/pause", follow_redirects=True)
        self.add_book(current_page="50")
        response = self.client.post(
            "/continued/0/resume",
            data={"due_date": "2026-10-11"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"already exists", response.data)
        data = self.load()
        self.assertEqual(len(data["books"]), 1)
        self.assertEqual(data["books"][0]["current_page"], 50)
        self.assertEqual(len(data["to_be_continued"]), 1)

    def test_resume_paused_book_allows_same_title_different_author(self):
        self.add_book(current_page="220")
        self.client.post("/books/0/pause", follow_redirects=True)
        self.add_book(author="Another Author", current_page="50")
        response = self.client.post(
            "/continued/0/resume",
            data={"due_date": "2026-10-11"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Resumed", response.data)
        data = self.load()
        self.assertEqual(len(data["books"]), 2)
        self.assertEqual(len(data["to_be_continued"]), 0)

    def test_drop_paused_book(self):
        self.add_book()
        self.client.post("/books/0/pause", follow_redirects=True)
        response = self.client.post("/continued/0/drop", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dropped", response.data)
        self.assertEqual(self.load()["to_be_continued"], [])

    def test_drop_paused_book_invalid_id(self):
        response = self.client.post("/continued/99/drop", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Paused book not found", response.data)

    def test_api_update_progress(self):
        self.add_book()
        response = self.client.post(
            "/api/progress", data={"title": "Dune", "current_page": "150"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dune", response.data)
        self.assertEqual(self.load()["books"][0]["current_page"], 150)

    def test_api_update_progress_unknown_title(self):
        response = self.client.post(
            "/api/progress", data={"title": "Nope", "current_page": "10"}
        )
        self.assertEqual(response.status_code, 404)

    def test_api_update_progress_bad_page(self):
        self.add_book()
        response = self.client.post(
            "/api/progress", data={"title": "Dune", "current_page": "abc"}
        )
        self.assertEqual(response.status_code, 400)

    def test_auth_required_when_password_set(self):
        with mock.patch.dict(os.environ, {"BOOKPACER_PASSWORD": "secret"}):
            app = create_app(self.data_path)
            client = app.test_client()
            response = client.get("/")
            self.assertEqual(response.status_code, 401)
            response = client.get("/", auth=("anyone", "secret"))
            self.assertEqual(response.status_code, 200)

    def test_save_settings(self):
        response = self.client.post(
            "/settings",
            data={"webhook_url": "https://discord.com/api/webhooks/x/y"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.load()["settings"]["webhook_url"],
            "https://discord.com/api/webhooks/x/y",
        )

    def test_remind_now_without_webhook_flashes_error(self):
        response = self.client.post("/remind", follow_redirects=True)
        self.assertIn(b"webhook URL is required", response.data)

    def test_remind_now_sends(self):
        self.client.post(
            "/settings",
            data={"webhook_url": "https://discord.com/api/webhooks/x/y"},
        )
        with mock.patch(
            "bookpacer.pacing.send_discord_reminder", return_value=True
        ) as mocked:
            response = self.client.post("/remind", follow_redirects=True)
        self.assertIn(b"Discord reminder sent", response.data)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
