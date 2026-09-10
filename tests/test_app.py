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
